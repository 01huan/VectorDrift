"""Split from scenes/game.py to keep files manageable."""
import logging
import math
from dataclasses import replace

import pygame

from .. import config, render, sprites
from ..config import px
from ..desktop import set_cursor
from ..background import BackgroundBuilder
from ..coords import Viewport, fit_zoom
from ..data import (SHIPS, custom_level_to_snapshot, default_ship_id, get_level,
                    is_custom_level, level_holes, section_count, section_level, section_shift,
                    ship_unlocked)
from ..expr_parser import diagnose_expression
from ..hints import get_hint
from ..level_presets import is_dynamic_level
from ..physics import Flight, ForceField, Outcome
from ..pickups import EXTRATIME_DURATION, extratime_bonus_steps
from ..image_assets import COIN_BALANCE
from ..ui import (Button, CodeEditor, IconButton, coin_price_parts, draw_coins, draw_icon_row,
                  draw_panel_box, draw_text, icon_surface)
from ..solver import PSOSolver, PSOConfig, Solver, run_solver_async
from ..solver.interface import SolveResult
from .base import Scene
from .hint_popup import HintPopup, confirm_text
from .pause_menu import PauseMenu
from . import pickup_effects as pfx
from .game_section_pan import SectionPan
log = logging.getLogger(__name__)

# Physics-expected failures (bad user expression, overflow, huge-finite clamp).
# Anything outside this tuple is an internal bug: still contained as DIVERGED
# so the frame loop never dies, but logged at exception level for debugging.
_PHYSICS_ERRORS = (
    ArithmeticError, ValueError, TypeError, OverflowError,
    RecursionError, MemoryError,
)
# Rendering never raises for bad numbers; only these pygame/data errors are
# contained (never bare `Exception`, so real bugs stay visible in logs).
_RENDER_ERRORS = (
    pygame.error, ValueError, TypeError, OverflowError, MemoryError,
)

from .game_layout import ARRIVED, FLIGHT, SETUP


class GameUIMixin:

    def draw(self, surface):
        surface.fill(config.BG)
        self._draw_plot(surface)
        self._draw_panel(surface)
        self._draw_fly_texts(surface)
        if self.ai_popup:
            self._draw_ai_popup(surface)
        if self.hint_popup is not None:
            self.hint_popup.answer_price = self._answer_price()
            self.hint_popup.available = self._available_coins()
            self.hint_popup.draw(surface)
        self._draw_coins(surface)
        if self.pause_menu is not None:
            self.pause_menu.draw(surface)

    def _draw_coins(self, surface):
        """Available balance, top-right of the plot, above every other layer.

        A coin just taken shows once its "+N" arrives; then the count jumps.
        """
        size = round(16 * self.pickup_fx.pop_scale(pfx.COINS))
        self._coins_rect = draw_coins(surface, self._shown_money(),
                                      (config.WINDOW_W - px(14), px(12)), size,
                                      config.WARNING, icon=COIN_BALANCE, anchor="topright")

    # ------------------------------------------------------------------ Pause menu
    def _open_pause(self):
        self.pause_menu = PauseMenu(in_flight=self.state == FLIGHT,
                                    music_on=getattr(self.audio, "music_on", True),
                                    sfx_on=getattr(self.audio, "sfx_on", True))
        if self.state == FLIGHT:
            self.audio.stop_loop("thruster_loop")
        set_cursor("arrow")

    def _close_pause(self):
        self.pause_menu = None
        if self.state == FLIGHT:
            self.audio.start_loop("thruster_loop")
        self._update_cursor()

    def _handle_pause_event(self, event):
        action = self.pause_menu.handle_event(event)
        if action is None:
            return
        if action in ("toggle_music", "toggle_sfx"):
            # Flip the switch first so turning Sound off is silent and on clicks.
            toggle = getattr(self.audio, action, None)     # SoundBank.toggle_music / toggle_sfx
            if toggle is not None:
                toggle()
            self.pause_menu.set_audio(getattr(self.audio, "music_on", True),
                                      getattr(self.audio, "sfx_on", True))
            self.audio.play("click")
            return
        self.audio.play("click")
        if action == "resume":
            self._close_pause()
        elif action == "abort":
            self.pause_menu = None
            self._abort()
        elif action == "restart":
            # Like Retry on the fail screen: same level, ship and seed, formulas kept.
            self.manager.switch(GameScene(self.manager))
        elif action == "levels":
            from .levels import LevelSelectScene
            self.manager.switch(LevelSelectScene(self.manager))
        elif action == "menu":
            from .menu import MenuScene
            self.manager.switch(MenuScene(self.manager))
        elif action == "quit":
            self.manager.quit()

    # ------------------------------------------------------------------ Hint
    def _section_hint(self):
        """The hint for the section on screen (one per section on multi-section levels)."""
        return get_hint(self.level.id, self.section_index) if self.hint_mode else None

    def _open_hint(self):
        if self.hint is None or self.state == ARRIVED:
            return
        self.audio.play("click")
        self.hint_popup = HintPopup(self.hint)

    def _handle_hint_event(self, event):
        popup = self.hint_popup
        action = popup.handle_event(event)
        if action is None:
            return
        self.audio.play("click")
        if action == "next":
            if popup.page + 1 < popup.answer_page:
                popup.page += 1
            else:
                self._request_hint_answer()
        elif action == "prev":
            popup.message = None
            popup.page = max(0, popup.page - 1)
        elif action == "confirm":
            popup.confirming = False
            price = self._answer_price()
            if price > self._available_coins():
                self._request_hint_answer()     # balance changed: explain instead
                return
            if not price:
                self.session.hint_answer_confirmed = True
            self._show_hint_answer(price)
        elif action == "cancel":
            popup.confirming = False
        elif action == "close":
            self.hint_popup = None
        else:                                   # ("apply", index)
            answer = self.hint.answers[action[1]]
            self.editor.set_lines([answer.fx, answer.fy])
            self._on_text_change(self.editor)
            self.hint_popup = None

    def _answer_price(self):
        """Coins the answer page costs now: 0 on free levels or once paid."""
        lid = self.level.id
        if lid in config.FREE_ANSWER_LEVELS or lid in self.session.paid_answer_levels:
            return 0
        return config.HINT_ANSWER_COST

    def _request_hint_answer(self):
        """Player asked for the answer page: show it, ask first, or explain why not."""
        popup = self.hint_popup
        price = self._answer_price()
        free_level = self.level.id in config.FREE_ANSWER_LEVELS
        if not price and (not free_level or self.session.hint_answer_confirmed):
            self._show_hint_answer()            # already paid, or free and confirmed
            return
        available = self._available_coins()
        if price > available:
            popup.message = coin_price_parts(price, available, "Need", config.WARNING)
            return
        popup.message = None
        popup.confirm_text = confirm_text(price)
        popup.confirm_price = coin_price_parts(price, available) if price else None
        popup.confirming = True

    def _show_hint_answer(self, price=0):
        """Open the answer page: a reveal, paid with ``price`` coins."""
        self._reveal_solution()
        if price:
            self.session.money.spend(price)
            self.money = self.session.money
            self.session.paid_answer_levels.add(self.level.id)
            self._save_progress()
        self.hint_popup.page = self.hint_popup.answer_page
        self._reset_level()

    def _reset_level(self):
        """Back to the current section as it started (start, pickups, rocks); lives stay.

        On a multi-section level only this section resets: its start is the
        checkpoint just reached, and sections already passed stay passed.
        A flight in progress just stops: it costs no life.
        """
        if self.state == FLIGHT:
            self.audio.stop_loop("thruster_loop")
            self.flight = None
            self.state = SETUP
        self.level = section_level(self.full_level, self.section_index)
        self._load_section_props()
        self.launch_pos = self.level.start
        self.camera.zoom = 1.0
        self.trail.clear()
        self._trail_count = 0
        self._clear_history()
        self.pickup_fx.clear()
        self.banner = None
        self.heading = self._heading_to_target()
        self._validate()

    # ------------------------------------------------------------------ Coins
    def _coin_key(self, center):
        """A coin's identity: its level on fixed levels, its map on random ones."""
        if is_dynamic_level(self.level.id):
            return (self.level.id, self.session.random_seed, tuple(center))
        return (self.level.id, tuple(center))

    def _collected_coins(self):
        """Keys of coins already paid out (fixed: saved; random: this launch)."""
        if is_dynamic_level(self.level.id):
            return self.session.collected_random_coins
        return self.session.collected_money_pickups

    def _available_coins(self):
        """Balance the player can spend on a reveal: the full current balance.

        Revealing an answer costs its price; coins collected during the run are
        not taken back, so everything the player holds is available.
        """
        return int(self.session.money)

    def _reveal_solution(self):
        """A full answer is shown (Hint answer page or AI Solver reveal).

        The answer price is paid separately by the caller. Coins collected during
        the run are kept: best time, clear reward, and run coins all still count
        on a clear. The run is flagged so the UI can note that an answer was used.
        """
        self.money = self.session.money
        self.solution_used = True
        self._save_progress()

    def _pay_clear_reward(self):
        """Reaching the target pays once per fixed level (saved) or random map.

        The clear reward is paid regardless of whether an answer was revealed;
        revealing an answer only costs its price.
        """
        self._clear_reward = 0
        if self.level.id in getattr(self.session, "custom_level_ids", set()):
            return
        if is_dynamic_level(self.level.id):
            paid, key = self.session.clear_rewarded_maps, (self.level.id, self.session.random_seed)
        else:
            paid, key = self.session.clear_rewarded_levels, self.level.id
        if key in paid:
            return
        paid.add(key)
        self._clear_reward = config.CLEAR_REWARD
        self.session.money.add(self._clear_reward)
        self.money = self.session.money

    def _save_progress(self) -> None:
        """Persist the current session locally and sync to Supabase if signed in.

        Called right after ``session.money`` (or other profile data) changes
        so progress is not lost when the player quits the level without
        clearing it.
        """
        from vector_drift.account.integration import save_progress

        save_progress(self.manager.account, self.session)

    def _hide_collected_coins(self):
        collected = self._collected_coins()
        for p in self.pickups:
            if p.kind == "money" and self._coin_key(p.center) in collected:
                p.consumed = True

    # ------------------------------------------------------------------ AI assistant
    def _position_ai_popup_buttons(self):
        """Center Apply (or Reveal) and Close under the standard popup card."""
        card = pygame.Rect(0, 0, px(560), px(320))
        card.center = (config.WINDOW_W // 2, config.WINDOW_H // 2)
        bw, bh, gap = px(110), px(40), px(14)
        first_w = bw if self._ai_revealed() else px(160)
        x0 = card.centerx - (first_w + gap + bw) // 2
        by = card.bottom - px(56)
        self.ai_apply_button.rect = pygame.Rect(x0, by, bw, bh)
        self.ai_reveal_button.rect = pygame.Rect(x0, by, px(160), bh)
        self.ai_reveal_button.enabled = self._available_coins() >= config.AI_SOLVER_COST
        self.ai_reveal_button.price_short = not self.ai_reveal_button.enabled
        self.ai_close_button.rect = pygame.Rect(x0 + first_w + gap, by, bw, bh)

    def _solver_map_key(self):
        """The unit an AI Solver reveal is paid for: this random map."""
        return (self.level.id, self.session.random_seed)

    def _ai_revealed(self):
        return self._solver_map_key() in self.session.revealed_solver_maps

    def _buy_ai_reveal(self):
        """Pay for this map's AI answers; paying is the reveal."""
        cost = config.AI_SOLVER_COST
        if self._available_coins() < cost:
            self.audio.play("error")
            return
        self.audio.play("click")
        self._reveal_solution()
        self.session.money.spend(cost)
        self.money = self.session.money
        self.session.revealed_solver_maps.add(self._solver_map_key())
        self._save_progress()

    def _note_ai_answer_shown(self):
        """A paid map's answer on screen counts as using the solution."""
        if (self.ai_popup and not self.solution_used and self._ai_revealed()
                and self.ai_result is not None and self.ai_result.best is not None):
            self._reveal_solution()

    def _state_key(self):
        obstacles = tuple(getattr(self.level, "obstacles", ()) or ())
        pickups = tuple(p.consumed for p in getattr(self, "pickups", ()) or ())
        return (self.level.id, self.session.random_seed, self.launch_pos,
                self.lives, getattr(self.session, "ship_id", None), obstacles, pickups)

    def _kick_ai_for_state(self):
        key = self._state_key()
        self._last_state_key = key
        if key in self.ai_best_by_state:
            self.ai_result = self.ai_best_by_state[key]
            self.ai_status = "ready"
            return
        if self.ai_job is not None and self.ai_job.running and self.ai_job_state_key == key:
            return
        if self.ai_job is not None and self.ai_job.running:
            try:
                self.ai_job.cancel()
            except Exception:
                pass
        self.ai_status = "solving"
        self.ai_message = "Solving (offline PSO, no network needed)"
        self.ai_popup = False
        self.ai_result = None
        seed = self.session.random_seed
        self.ai_job_state_key = key
        # Solve from the *current* launch point: after a TIMEOUT resume the
        # ship sits at the stopped position, not the level start, so the
        # cached formulas must be re-derived from here.
        solve_level = self.level
        if tuple(self.level.start) != tuple(self.launch_pos):
            solve_level = replace(self.level, start=tuple(self.launch_pos))
        self.ai_job = run_solver_async(
            self.ai_solver,
            solve_level,
            rng_seed=seed,
            progress_callback=lambda r: setattr(self, "ai_result", r),
        )

    def on_exit(self):
        """Leaving the level: stop the thruster sound and the background solve."""
        self.audio.stop_loop("thruster_loop")
        self.pickup_fx.clear()
        if self._layer_builder is not None:
            self._layer_builder.stop()
        job, self.ai_job = self.ai_job, None
        if job is not None and job.running:
            try:
                job.stop()
            except Exception:
                pass

    def _on_ai_click(self):
        """User tapped the AI button: return best verified solution or wait."""
        key = self._state_key()
        if key in self.ai_best_by_state:
            self.ai_result = self.ai_best_by_state[key]
            self.ai_status = "ready"
        elif self.ai_job is not None and self.ai_job.running and self.ai_job_state_key == key:
            if getattr(self.ai_job, "result", None) is not None:
                self.ai_result = self.ai_job.result
            self.ai_status = "solving"
        else:
            self._kick_ai_for_state()
        self.ai_popup = True
        self._position_ai_popup_buttons()
        self._note_ai_answer_shown()

    def _apply_ai_suggestion(self):
        """Write the best candidate formula into the Fx/Fy editor."""
        if self.ai_result is None or self.ai_result.best is None:
            return
        best = self.ai_result.best
        self.editor.set_lines([best.fx_text, best.fy_text])
        self._on_text_change(self.editor)
        self.ai_popup = False
        try:
            self.audio.play("click")
        except Exception:  # noqa: BLE001 - audio is optional
            pass

    def _draw_ai_popup(self, surface):
        """Dimmed snapshot + centered result card with Apply/Close buttons."""
        # Dimmed snapshot of the current frame.
        shade = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        shade.fill((5, 8, 18, 200))
        surface.blit(shade, (0, 0))

        card = pygame.Rect(0, 0, px(560), px(320))
        card.center = (config.WINDOW_W // 2, config.WINDOW_H // 2)
        pygame.draw.rect(surface, config.PANEL_BG, card, border_radius=px(6))
        pygame.draw.rect(surface, config.ACCENT, card,
                         width=max(1, px(1)), border_radius=px(6))
        draw_text(surface, "AI Assistant", (card.centerx, card.y + px(22)), 30,
                  config.TEXT, kind="bold", anchor="center")

        best = self.ai_result.best if self.ai_result else None
        revealed = self._ai_revealed()
        y = card.y + px(74)
        rows = []
        if self.ai_status == "solving" and best is None:
            rows.append(("S", "Solving… (offline PSO, no network needed)"))
        elif best is not None:
            rows.append(("Status", "Solution found" if self.ai_result.best_score >= 1.5
                         else "No feasible solution found"))
            rows.append(("Template", best.template))
            if revealed:                    # Fx / Fy stay hidden until this map is paid
                rows.append(("Fx", best.fx_text))
                rows.append(("Fy", best.fy_text))
            rows.append(("Score", f"{self.ai_result.best_score:.3f}"))
        else:
            rows.append(("Status", self.ai_message or "Ready"))

        for label, value in rows:
            draw_text(surface, label, (card.x + px(24), y), 15,
                      config.TEXT_DIM, anchor="topleft")
            draw_text(surface, value, (card.right - px(24), y), 15,
                      config.TEXT, kind="mono", anchor="topright")
            y += px(30)

        self._position_ai_popup_buttons()
        if revealed:
            self.ai_apply_button.enabled = best is not None
            self.ai_apply_button.draw(surface)
        else:
            cost, available = config.AI_SOLVER_COST, self._available_coins()
            if available < cost:
                draw_icon_row(surface, coin_price_parts(cost, available, "Need", config.WARNING),
                              (card.centerx, self.ai_reveal_button.rect.y - px(14)), 15,
                              anchor="midbottom")
            self.ai_reveal_button.draw(surface)
        self.ai_close_button.draw(surface)


import sys as _sys
def _gm():
    return _sys.modules["vector_drift.scenes.game"]
def PSOConfig(*a, **k):
    return _gm().PSOConfig(*a, **k)
def draw_coins(*a, **k):
    return _gm().draw_coins(*a, **k)
def draw_icon_row(*a, **k):
    return _gm().draw_icon_row(*a, **k)
def draw_text(*a, **k):
    return _gm().draw_text(*a, **k)
def get_hint(*a, **k):
    return _gm().get_hint(*a, **k)
def get_level(*a, **k):
    return _gm().get_level(*a, **k)
def run_solver_async(*a, **k):
    return _gm().run_solver_async(*a, **k)


def GameScene(*a, **k):
    return _gm().GameScene(*a, **k)
