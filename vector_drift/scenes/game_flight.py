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

from .game_layout import (
    ARRIVED, FLIGHT, HISTORY_ALPHA, OUTCOME_TEXT, PANNING,
    RESPAWN_EVERY_LIFE, RESUME_OUTCOMES, SETUP,
)


class GameFlightMixin:

    def handle_event(self, event):
        if event.type == pygame.MOUSEMOTION:
            self._mouse_pos = event.pos
            self._update_cursor()
        if self.state == PANNING:
            return                      # pan to the next section: no input at all
        if self.hint_popup is not None:
            self._handle_hint_event(event)
            return                      # modal: nothing behind it takes input
        if self.ai_popup and event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.audio.play("click")    # same as its Close button
            self.ai_popup = False
            return
        if self.pause_menu is not None:
            self._handle_pause_event(event)
            return                      # modal: nothing behind it takes input
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            if self.state in (SETUP, FLIGHT):
                self._open_pause()
            return                      # ARRIVED: Esc does nothing
        # The run button sits inside the editor's header, so it gets the event first.
        result = self.run_button.handle_event(event)
        if result == "click":
            if self.state == SETUP:
                self._try_launch()
            elif self.state == FLIGHT:
                self._abort()
            return
        if result == "disabled":
            self.audio.play("error")
            return

        if self.state == FLIGHT and event.type == pygame.KEYDOWN:
            if event.key == pygame.K_b:
                charges = getattr(self.session, "ability_charges", {}) or {}
                if self.flight is not None and charges.get("ability_boost", 0) > 0:
                    if self.flight.boost():
                        charges["ability_boost"] = int(charges.get("ability_boost", 0)) - 1
                        try:
                            self.session.ability_charges = charges
                        except Exception:
                            pass
                        try:
                            self.audio.play("boost")
                        except Exception:
                            pass
                return
            if event.key == pygame.K_v:
                charges = getattr(self.session, "ability_charges", {}) or {}
                if self.flight is not None and charges.get("ability_shield_pulse", 0) > 0:
                    if self.flight.shield_pulse():
                        charges["ability_shield_pulse"] = int(charges.get("ability_shield_pulse", 0)) - 1
                        try:
                            self.session.ability_charges = charges
                        except Exception:
                            pass
                        try:
                            self.audio.play("shield")
                        except Exception:
                            pass
                return
            if event.key == pygame.K_m:
                charges = getattr(self.session, "ability_charges", {}) or {}
                if self.flight is not None and charges.get("ability_magnet", 0) > 0:
                    if self.flight.magnet_pulse():
                        charges["ability_magnet"] = int(charges.get("ability_magnet", 0)) - 1
                        try:
                            self.session.ability_charges = charges
                        except Exception:
                            pass
                        try:
                            self._save_progress()
                        except Exception:
                            pass
                        try:
                            self.audio.play("unbound")
                        except Exception:
                            pass
                return
        if self.state == SETUP:
            if event.type == pygame.KEYDOWN and event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self._try_launch()
                return
            if self.editor.handle_event(event):
                return

        if self.level_button.handle_event(event) == "click":
            self.audio.play("click")
            from .base import back_scene_for_level
            Target = back_scene_for_level(self.session, self)
            self.manager.switch(Target(self.manager))
            return
        if self.prev_ship.handle_event(event) == "click":
            self._switch_ship(-1)
        if self.next_ship.handle_event(event) == "click":
            self._switch_ship(1)

        if self.ai_popup:
            self._position_ai_popup_buttons()
            if self._ai_revealed():
                if self.ai_apply_button.handle_event(event) == "click":
                    self.audio.play("click")
                    self._apply_ai_suggestion()
                    return
            elif self.ai_reveal_button.handle_event(event) == "click":
                self._buy_ai_reveal()
                return
            if self.ai_close_button.handle_event(event) == "click":
                self.audio.play("click")
                self.ai_popup = False
                return
            return  # Modal: swallow other input while the popup is open.

        if self.ai_button.handle_event(event) == "click":
            # Free to open; only the full answer costs (answer page / Reveal).
            if self.hint_mode:
                self._open_hint()
            else:
                self._on_ai_click()
            return

    # ------------------------------------------------------------------ flow
    def _try_launch(self):
        self._replay_frames = []
        self._replay_pickup_events = []
        # Snapshot the level state at launch so replays can reproduce it
        # (pickups already consumed in previous runs, obstacles already
        # destroyed by an earlier shockwave).
        try:
            self._replay_initial_consumed = [tuple(p.center) for p in (self.pickups or []) if getattr(p, "consumed", False)]
        except Exception:
            self._replay_initial_consumed = []
        try:
            self._replay_initial_obstacle_centers = [tuple(getattr(o, "center", ())) for o in (getattr(self.level, "obstacles", ()) or ())]
        except Exception:
            self._replay_initial_obstacle_centers = []
        if not self.valid or not self._ship_unlocked:
            self.audio.play("error")
            return
        if (is_custom_level(self.level.id)
                or self.level.id in getattr(self.session, "custom_level_ids", set())):
            self._replay_level_snapshot = custom_level_to_snapshot(self.full_level)
        else:
            self._replay_level_snapshot = None
        self.attempts += 1
        self.flight = Flight(self.field, self.ship, self.level, start=self.launch_pos,
                             pickups=self.pickups, holes=self.holes)
        charges = getattr(self.session, "ability_charges", {}) or {}
        self.flight.boost_charges = int(charges.get("ability_boost", 0))
        self.flight.shield_pulse_charges = int(charges.get("ability_shield_pulse", 0))
        self._prefetch_arrows()         # drawn ahead in the background, not here
        self.pickup_fx.clear()          # the last flight's texts must not hold back this one's timer
        self.trail.clear()
        self._trail_count = 0
        self._bounces_heard = 0
        self._teleports_heard = 0
        self._replay_teleports = 0
        self.state = FLIGHT
        self._record_replay_frame(self.flight)
        self.banner = None
        self._refresh_buttons()
        self.audio.play("launch")
        self.audio.start_loop("thruster_loop")

    def _abort(self):
        if self.flight and self.flight.running:
            self.flight.abort()
            self._end_flight(self.flight.outcome)

    def _end_flight(self, outcome):
        try:
            from vector_drift.replay import normalize_records
            from vector_drift.account.integration import session_to_profile
            rec = {
                "level_id": self.level.id,
                "ship_id": getattr(self.ship, "id", None),
                "fx_text": self.editor.lines[0].strip() if self.editor.lines else "",
                "fy_text": self.editor.lines[1].strip() if len(self.editor.lines) > 1 else "",
                "outcome": str(outcome),
                "frames": list(self._replay_frames),
                # 隨機關卡必須連同 seed 一起紀錄...
                "seed": self.session.random_seed,
                # Level state at launch: pickups already consumed in previous
                # runs and obstacles already destroyed must not reappear.
                "consumed_pickups": list(getattr(self, "_replay_initial_consumed", []) or []),
                "obstacle_centers": list(getattr(self, "_replay_initial_obstacle_centers", []) or []),
                "level_snapshot": getattr(self, "_replay_level_snapshot", None),
                # Pickup events during this flight (shockwave, unbound, etc.)
                "pickup_events": list(getattr(self, "_replay_pickup_events", []) or []),
                # Which screen this launch flew (multi-section levels); the
                # replay rebuilds that section, not section 1.
                "section_index": self.section_index,
            }
            self.session.replays = normalize_records(list(self.session.replays or []) + [rec], 10)
        except Exception:
            pass
        try:
            from vector_drift.account.integration import save_progress
            save_progress(self.manager.account, self.session)
        except Exception:
            pass
        self.audio.stop_loop("thruster_loop")
        self._sync_trail()
        self.total_time += self.flight.time
        if outcome is Outcome.REACHED and not self.on_last_section:
            self._reach_checkpoint()
            return
        if outcome is Outcome.REACHED:
            self.state = ARRIVED
            self.arrive_timer = config.WIN_DELAY
            self.hint_popup = None
            self._pay_clear_reward()
            best = self.session.records.get(self.level.id)
            if best is None or self.total_time < best:
                self.session.records[self.level.id] = self.total_time
            from vector_drift.account.integration import save_progress

            save_progress(self.manager.account, self.session)
            self.audio.play("win")
            self._refresh_buttons()
            return

        self.lives -= 1
        reason = OUTCOME_TEXT[outcome]
        if self.lives <= 0:
            self.audio.play("game_over")
            self.session.stats = {"reason": reason, "attempts": self.attempts}
            from .fail import FailScene
            self.manager.switch(FailScene(self.manager, self._snapshot()))
            return

        self.audio.play("life_lost")
        noun = "life" if self.lives == 1 else "lives"
        self._respawn_every_life_pickups()
        if outcome in RESUME_OUTCOMES and not self._off_map(self.flight):
            # Keep this leg visible (dimmed) and continue from where the ship stopped.
            self.launch_pos = (self.flight.x, self.flight.y)
            leg = self.trail.bounds
            if leg.w and leg.h:
                self.trail.draw(self.history, (0, 0), HISTORY_ALPHA)
                hb = self.history_bounds
                self.history_bounds = hb.union(leg) if hb.w and hb.h else leg.copy()
            self._history_legs.append((list(self.flight.trail), list(self.flight.trail_breaks)))
            where = f"resume from ({self.launch_pos[0]:.2f}, {self.launch_pos[1]:.2f})"
        else:
            self.launch_pos = self.level.start
            self._clear_history()
            where = "back to start"
        self.trail.clear()
        self.banner = (reason, f"{self.lives} {noun} left · {where}", config.BANNER_DURATION)
        self.flight = None
        self.heading = self._heading_to_target()
        self.state = SETUP
        self._validate()                # launch point moved: re-check the formulas there

    def _clear_history(self):
        """Drop the dimmed earlier legs (pixels and world points)."""
        self.history.fill((0, 0, 0, 0), self.history_bounds)
        self.history_bounds = pygame.Rect(0, 0, 0, 0)
        self._history_legs = []

    def _respawn_every_life_pickups(self):
        """A new life starts: the RESPAWN_EVERY_LIFE pickups (unbound) are back."""
        for p in self.pickups or ():
            if p.kind in RESPAWN_EVERY_LIFE:
                p.consumed = False

    @staticmethod
    def _off_map(flight):
        """True if the ship stopped outside the map (only an unbound ship can)."""
        try:
            return abs(flight.x) > flight.bounds[0] or abs(flight.y) > flight.bounds[1]
        except (AttributeError, TypeError, IndexError):
            return False

    def _reach_checkpoint(self):
        """Reached a checkpoint: +1 life (capped), then pan to the next section.

        Not a win: no Win screen or clear. From now on a lost
        life relaunches from this checkpoint, the next section's start.
        """
        flight = self.flight
        if self.lives < self.level.lives:
            self.lives += 1
        self.audio.play("life")
        self.pan = SectionPan(
            shift=section_shift(self.full_level, self.section_index),
            level=self.level, pickups=self.pickups, holes=self.holes,
            arrival=(flight.x, flight.y))
        self.section_index += 1
        self.level = section_level(self.full_level, self.section_index)
        self._load_section_props()
        self.hint = self._section_hint()
        self.hint_popup = None          # the old section's hint no longer applies
        self.launch_pos = self.level.start
        self.banner = None
        self.flight = None
        self.pickup_fx.clear()
        self.state = PANNING
        self.camera.zoom = 1.0          # the pan is drawn at the map's own scale
        self._refresh_buttons()

    def _finish_pan(self):
        """The camera is on the next section: set it up for the next launch."""
        self.pan = None
        self.trail.clear()
        self._trail_count = 0
        self._clear_history()
        self.heading = self._heading_to_target()
        self.state = SETUP
        self._validate()                # new launch point: re-check the formulas there

    def _snapshot(self):
        screen = self.manager.screen or pygame.display.get_surface()
        return screen.copy() if screen is not None else None

    def _sync_trail(self):
        """Feed new flight points into the smooth trail layer."""
        if self.flight is None:
            return
        pts = self.flight.trail
        start, end = self._trail_count, len(pts)
        if end <= start:
            return
        # A teleport starts a new stroke: lift the pen at each break so the
        # trail is not joined from the black hole to the white hole.
        breaks = [i for i in getattr(self.flight, "trail_breaks", ()) if start <= i < end]
        vp = self.viewport
        bounds = sorted({start, *breaks, end})
        for lo, hi in zip(bounds, bounds[1:]):
            if lo in breaks:
                self.trail.last = None
            try:
                new = [(vp.cx - vp.left + x * vp.scale, vp.cy - vp.top - y * vp.scale)
                       for x, y in pts[lo:hi]]
                self.trail.extend(new)
            except (TypeError, ValueError, OverflowError):
                continue
            except _RENDER_ERRORS as exc:
                log.warning("trail extend contained: %r", exc)
        self._trail_count = end


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
