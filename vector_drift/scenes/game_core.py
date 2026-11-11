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
    CONTENT_W, CX, EDITOR_Y, FLIGHT, LEVEL_ROW_Y, PAD, R, RUN_GREEN,
    SETUP, TELEMETRY_ROW_H,
)


class GameCoreMixin:

    def __init__(self, manager, source=None, origin=None, level_source=None,
                 play_source=None, **kwargs):
        super().__init__(manager)
        _src = source or origin or level_source or play_source
        if _src is not None:
            self.level_source = _src
            self.session.level_source = _src
        self.pause_menu = None          # Esc menu; while open the level is paused
        if is_dynamic_level(self.session.level_id) or is_custom_level(self.session.level_id) \
                or self.session.level_id in getattr(self.session, "custom_level_ids", set()):
            # Same seed for the whole run: random layout (random maps) and the
            # offline AI solver both key off it, so it stays stable across
            # retry/replay even for custom maps.
            if self.session.random_seed is None:
                import random as _random
                self.session.random_seed = _random.SystemRandom().randint(0, 2 ** 31 - 1)
            if is_dynamic_level(self.session.level_id):
                self.full_level = get_level(self.session.level_id, seed=self.session.random_seed)
            else:
                self.full_level = get_level(self.session.level_id)
        else:
            self.full_level = get_level(self.session.level_id)
        # Multi-section levels: self.level is always the CURRENT section as an
        # ordinary one-screen LevelSpec (section_level), so physics, hints,
        # pickups and drawing work unchanged. One-screen levels: the level itself.
        self.section_index = 0
        self.level = section_level(self.full_level, 0)
        self.pan = None                 # SectionPan while state == PANNING
        # Every skin in order; the ones this level has not unlocked are shown
        # (grey, "LvN+") but cannot fly. Retry / Replay keep the session's
        # pick; the level select clears it, so a level starts on its newest ship.
        self.owned_ships = list(SHIPS)
        ship_id = self.session.ship_id
        if ship_id not in SHIPS or not ship_unlocked(SHIPS[ship_id], session=self.session):
            ship_id = default_ship_id(self.level.id, session=self.session)
        self.ship_index = self.owned_ships.index(ship_id)
        self.ship = SHIPS[ship_id]
        self.flyable_ship = self.ship           # what flies (and fills the lives row)

        # viewport: the map at zoom 1, for the cached layers and trail pixels.
        # camera: what the plot is drawn through; it zooms out while an
        # unbound ship is off the map (_update_camera).
        self.viewport = Viewport()
        self.camera = Viewport()
        self._space = render.make_plot_space(self.viewport)
        self.background = render.make_plot_background(self.viewport, space=self._space)
        self.labels = render.make_plot_labels(self.viewport)
        plot_size = (self.viewport.width, self.viewport.height)
        self.trail = sprites.TrailLayer(plot_size)
        self.history = pygame.Surface(plot_size, pygame.SRCALPHA)
        self.history_bounds = pygame.Rect(0, 0, 0, 0)
        self._history_legs = []         # the same earlier legs as world points (zoomed drawing)
        self._overlay = None            # plot-sized scratch layer for zoomed drawing
        self._space_screen = None       # the stars in the display's format (zoomed drawing)
        self._mips, self._mips_key = {}, None       # arrow layers by zoom level
        self._arrows, self._arrows_key = None, None # arrow layer at the current zoom
        self._arrows_smooth = True      # False: a fast stretch, redone smoothly once still
        self._arrows_level = 0          # the zoom level the current arrows were stretched from
        self._layer_builder = None      # background worker for arrow layers (Unbound levels)
        self._arrows_surface = None     # reused target of the arrow stretch
        self._trail_count = 0
        self._plot_base = None          # background + arrows + labels, pre-composited
        self._plot_key = None
        self._field_version = 0

        self.lives = self.level.lives
        self.attempts = 0
        self.total_time = 0.0
        self._replay_frames = []
        self.state = SETUP
        self.flight = None
        self._load_section_props()
        self.money = self.session.money
        self.launch_pos = self.level.start
        self.banner = None              # (title, subtitle, time_left)
        self.arrive_timer = 0.0
        self.t = 0.0
        self.heading = self._heading_to_target()
        self._mouse_pos = (-1, -1)
        # What taking a pickup looks like (presentation only, see pickup_effects).
        self.pickup_fx = pfx.PickupEffects()
        self._coins_rect = None         # where the coin count was last drawn (fly target)

        # Widgets
        self.level_button = IconButton(R(CX + 16, LEVEL_ROW_Y - 18, 36, 36), "grid", style="circle")
        self.prev_ship = IconButton(R(CX - 112, 181, 26, 38), "chev_left")
        self.next_ship = IconButton(R(CX + 86, 181, 26, 38), "chev_right")
        self.editor = CodeEditor((px(PAD), px(EDITOR_Y)), px(CONTENT_W), title="Vector_field",
                                 footer_title="TELEMETRY", footer_rows_h=4 * TELEMETRY_ROW_H + 8,
                                 on_change=self._on_text_change)
        header = self.editor.header_rect
        self.run_button = IconButton((header.right - px(30), header.y + px(3), px(24), px(22)), "play",
                                     color=RUN_GREEN)

        # Inventory icon in the upper-right corner of the plot.
        self.inventory_button = IconButton((config.WINDOW_W - px(44), px(65), px(32), px(32)),
                                            "inventory", style="circle", color=config.TEXT)
        self.inventory_open = False
        self.inventory_popup = self.inventory_open

        self.field = ForceField()
        self.field_layer = None
        self.max_force = 0.0
        self.valid = True
        # Undo history follows the formulas: a Retry keeps both, while entering
        # from level select or Replay clears the text and with it the history.
        saved = self.session.editor_history
        self.editor.set_lines([self.session.fx_text, self.session.fy_text], record=False)
        if saved is not None and saved[:2] == (self.level.id, tuple(self.editor.lines)):
            self.editor.history = saved[2]
        self._remember_editor_history()

        # --- Hint (fixed levels) / AI Solver (random + custom levels) ---------
        # Fixed levels show hand-written hints (hints.toml) in place of the AI
        # Solver and never start it. Random levels and custom levels use the AI
        # Solver instead: opening it is free, revealing the full answer costs
        # config.AI_SOLVER_COST coins once per map/level this launch.
        # Revealing the answer costs its price once per launch; that price is the
        # only cost. Clears still count toward best times, clear rewards, and coins.
        self.hint_mode = not (is_dynamic_level(self.level.id)
                              or is_custom_level(self.level.id)
                              or self.level.id in getattr(self.session, "custom_level_ids", set()))
        self.hint = self._section_hint()
        self.hint_popup = None
        self.solution_used = False
        self._run_coins = []            # (coin key, amount) paid out this run, before any reveal
        self._clear_reward = 0          # coins the clear paid (shown on Mission Complete)

        # --- AI assistant (offline solver, random levels) -------------------
        # Depends on the Solver interface, not a concrete model.  Swapping the
        # backend (PSO -> regression -> NN -> GP -> RL) only requires replacing
        # self.ai_solver; no UI or event code changes needed.
        self.ai_solver: Solver | None = None if self.hint_mode else PSOSolver(PSOConfig(early_stop_on_success=False))
        self.ai_job = None
        self.ai_result: SolveResult | None = None
        self.ai_status = "idle"        # idle | solving | ready | error
        self.ai_message = ""
        self.ai_popup = False
        self.ai_button = Button((px(PAD), px(690), px(CONTENT_W), px(28)),
                                "Hint" if self.hint_mode else "AI Solver", style="plain", font_size=15)
        self.ai_apply_button = Button((0, 0, px(100), px(40)), "Apply",
                                      style="primary", font_size=15)
        self.ai_close_button = Button((0, 0, px(100), px(40)), "Close",
                                      style="plain", font_size=15)
        self.ai_reveal_button = Button((0, 0, px(160), px(40)), "Reveal",
                                       style="primary", font_size=15)
        self.ai_reveal_button.price = config.AI_SOLVER_COST
        self.ai_job_state_key = None
        self.ai_best_by_state = {}
        self._last_state_key = None
        if not self.hint_mode:
            self._kick_ai_for_state()

    def _load_section_props(self):
        """Pickups and black/white holes of the current section (self.level).

        One PickupState per spec for the WHOLE run of this section (all
        lives): consumed pickups and shockwave-cleared obstacles persist like
        level state until all lives are spent. No config = no pickups.
        Exception: the RESPAWN_EVERY_LIFE kinds (unbound) come back at the
        start of every life (_respawn_every_life_pickups).
        """
        from ..pickups import PickupState
        specs = getattr(self.level, "pickups", ()) or ()
        self.pickups = [PickupState.from_spec(s) for s in specs]
        self._has_unbound = any(p.kind == "unbound" for p in self.pickups)
        self._hide_collected_coins()
        self.holes = list(level_holes(self.level))

    @property
    def section_total(self):
        return section_count(self.full_level)

    @property
    def on_last_section(self):
        return self.section_index >= self.section_total - 1

    def _heading_to_target(self):
        tx = self.level.target_center[0] - self.launch_pos[0]
        ty = self.level.target_center[1] - self.launch_pos[1]
        return math.atan2(ty, tx)

    # ------------------------------------------------------------------ input
    def _on_text_change(self, editor):
        self.session.fx_text, self.session.fy_text = editor.lines
        self._remember_editor_history()
        self._validate()

    def _remember_editor_history(self):
        self.session.editor_history = (self.level.id, tuple(self.editor.lines), self.editor.history)

    def _validate(self):
        """Re-check both formulas against the current launch point."""
        editor = self.editor
        fx_text, fy_text = editor.lines

        fx, fx_err, fx_pos = diagnose_expression(fx_text)
        fy, fy_err, fy_pos = diagnose_expression(fy_text)

        editor.set_errors([
            (fx_err, fx_pos) if fx_err else None,
            (fy_err, fy_pos) if fy_err else None,
        ])

        self.valid = fx is not None and fy is not None

        if self.valid:
            field = ForceField.from_exprs(fx, fy)

            if field != self.field or self.field_layer is None:
                try:
                    layer, max_force = render.make_field_layer(
                        self.viewport, field
                    )
                except _PHYSICS_ERRORS + _RENDER_ERRORS as exc:
                    # The expression is syntactically valid, but may fail
                    # at some coordinates during preview sampling.
                    log.warning("field preview contained: %r", exc)
                    editor.set_errors([(str(exc), 0), None])
                    self.valid = False
                else:
                    # Update the preview only after rendering succeeds.
                    self.field = field
                    self.field_layer = layer
                    self.max_force = max_force
                    self._field_version += 1

        if self.valid:
            self._check_launch_point()
        self._refresh_buttons()

    def _check_launch_point(self):
        """Block a launch whose force is undefined where the ship sits.

        A formula can be valid yet undefined at the launch point (log(x) at
        x = -7): the flight would diverge on its first step and cost a life,
        so flag the offending line in PROBLEMS instead.
        """
        x, y = self.launch_pos
        bad = self.field.invalid_components(x, y)
        if not bad:
            return
        msg = f"Undefined at launch point ({x:.2f}, {y:.2f})"
        self.editor.set_errors([(msg, 0) if i in bad else None
                                for i in range(self.editor.n)])
        self.valid = False

    def _refresh_buttons(self):
        if self.state == FLIGHT:
            self.run_button.icon, self.run_button.color = "stop", config.DANGER
            self.run_button.enabled = True
        else:
            self.run_button.icon, self.run_button.color = "play", RUN_GREEN
            self.run_button.enabled = self.state == SETUP and self.valid and self._ship_unlocked
        setup = self.state == SETUP
        self.level_button.enabled = setup
        self.prev_ship.enabled = setup and self.ship_index > 0
        self.next_ship.enabled = setup and self.ship_index < len(self.owned_ships) - 1
        self.editor.enabled = setup
        self._update_cursor()

    @property
    def _ship_unlocked(self):
        return ship_unlocked(self.ship, session=self.session)

    def _switch_ship(self, step):
        """Show the previous / next skin; no wrap-around at either end."""
        index = max(0, min(len(self.owned_ships) - 1, self.ship_index + step))
        if index == self.ship_index:
            return
        self.ship_index = index
        self.session.ship_id = self.owned_ships[index]
        self.ship = SHIPS[self.session.ship_id]
        if self._ship_unlocked:
            self.flyable_ship = self.ship
        self.audio.play("click")
        self._refresh_buttons()

    def _update_cursor(self):
        over_text = self.pause_menu is None and self.editor.is_text_area(self._mouse_pos)
        set_cursor("text" if over_text else "arrow")


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
