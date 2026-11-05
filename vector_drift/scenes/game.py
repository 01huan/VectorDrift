"""Game screen: set up the force field, launch, watch the flight."""

import logging
import math
from dataclasses import replace

import pygame

from .. import config, render, sprites
from ..config import px
from ..desktop import set_cursor
from ..coords import Viewport, fit_zoom
from ..data import (SHIPS, default_ship_id, get_level, section_count, section_level,
                    section_shift, ship_unlocked)
from ..expr_parser import diagnose_expression
from ..hints import get_hint
from ..story import get_level_story, level_intro_key, level_win_key, random_fail_line
from ..level_presets import is_dynamic_level
from ..physics import Flight, ForceField, Outcome
from ..pickups import UNBOUND_OUTER_SCALE
from ..image_assets import COIN_BALANCE
from ..ui import (Button, CodeEditor, IconButton, coin_price_parts, draw_coins, draw_icon_row,
                  draw_panel_box, draw_text, icon_surface)
from ..solver import PSOSolver, PSOConfig, Solver, run_solver_async
from ..solver.interface import SolveResult
from .base import Scene
from .dialogue import DialogueBox
from .hint_popup import HintPopup, confirm_text
from .pause_menu import PauseMenu

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

SETUP, FLIGHT, ARRIVED = "setup", "flight", "arrived"
# Multi-section levels: the camera pans from a reached checkpoint to the next
# section. No input is taken until the next section's SETUP.
PANNING = "panning"

OUTCOME_TEXT = {
    Outcome.TIMEOUT: "TIME UP",
    Outcome.OUT_OF_BOUNDS: "OUT OF BOUNDS",
    Outcome.DIVERGED: "DIVERGED",
    Outcome.ABORTED: "ABORTED",
}
# After these outcomes the next launch starts (at rest) where the ship stopped;
# every other miss (abort, out of bounds, diverged) goes back to the level start.
# So does a time-up off the map (an unbound ship): see GameScene._end_flight.
RESUME_OUTCOMES = (Outcome.TIMEOUT,)
# Pickups that come back at the start of every life (the rest stay taken).
RESPAWN_EVERY_LIFE = ("unbound",)

START_MARKER_RADIUS_M = 0.45
CHECKPOINT_LIFE_POP_S = 0.45  # the taken checkpoint life grows and fades out this long
HISTORY_ALPHA = 110          # earlier legs of the current run
CAMERA_EASE_S = 0.1          # zoom time constant: about 0.3 s to settle
CAMERA_MARGIN_M = 1.0        # room kept between an off-map ship and the plot edge
UNBOUND_EDGE = (190, 130, 255)   # dashed map edge while Unbound is active
# Zooms the field arrows are drawn at for the zoomed-out view (1 down to the
# outer edge's 0.5, evenly spaced in ratio); in between, the next one down
# is stretched, so by at most 0.5 ** (-1/3) ~ 1.26.
ZOOM_LEVELS = tuple(UNBOUND_OUTER_SCALE ** (-i / 3) for i in range(4))
RUN_GREEN = (137, 209, 133)


def R(x, y, w, h):
    """Rect from logical pixels."""
    return pygame.Rect(px(x), px(y), px(w), px(h))


# Left panel layout in logical pixels (scaled with px / R)
PAD = 20
CX = 160                     # panel center line
CONTENT_W = 320 - 2 * PAD
LOGO_Y = 36
LOGO_W = 220                 # logo width; its height follows the picture (~69)
LEVEL_ROW_Y = 82
SHIP_LABEL_Y = 124
SHIP_BOX = R(CX - 55, 140, 110, 110)
SHIP_NAME_Y = 270
SHIP_MASS_Y = 292
STATUS_Y = 330
EDITOR_Y = 354
TELEMETRY_ROW_H = 20
LEGEND_LABEL_Y = 636
LEGEND_Y = 662


def ease_in_out(p):
    """Smoothstep 0 -> 1 for the section pan (slow start, slow stop)."""
    p = max(0.0, min(1.0, p))
    return p * p * (3.0 - 2.0 * p)


def pan_offsets(shift, progress):
    """(old, new) section offsets in m at eased pan ``progress`` 0 -> 1.

    Sections are drawn in their own coordinates plus an offset. The section
    being left moves from (0, 0) to -shift; the next one comes in from
    +shift and settles at (0, 0), so the shared checkpoint stays aligned.
    """
    sx, sy = shift
    return (-sx * progress, -sy * progress), (sx * (1.0 - progress), sy * (1.0 - progress))


def fmt_pair(x, y, unit):
    try:
        fx, fy = float(x), float(y)
    except (TypeError, ValueError, OverflowError):
        return f"— {unit}"
    if not (math.isfinite(fx) and math.isfinite(fy)):
        return f"— {unit}"
    return f"({fx:.2f}, {fy:.2f}) {unit}"


def fmt_clock(seconds):
    """Seconds as SS:CC (seconds and hundredths), e.g. 7.34 -> '07:34'."""
    cs = max(0, int(round(seconds * 100)))
    return f"{cs // 100:02d}:{cs % 100:02d}"


class SectionPan:
    """The camera pan from a reached checkpoint to the next section.

    ``shift`` is section_shift (m): where the new section's origin sits in
    the old section's coordinates. ``level`` / ``pickups`` / ``holes`` are
    the old section as it was left; ``arrival`` is where the ship touched
    the checkpoint (old section coordinates); ``t`` is seconds elapsed.
    """

    def __init__(self, shift, level, pickups, holes, arrival):
        self.shift = shift
        self.level = level
        self.pickups = pickups
        self.holes = holes
        self.arrival = arrival
        self.t = 0.0

    @property
    def progress(self):
        """Eased 0 -> 1 over config.CHECKPOINT_PAN_DURATION."""
        duration = config.CHECKPOINT_PAN_DURATION
        return ease_in_out(self.t / duration if duration > 0 else 1.0)


class GameScene(Scene):
    music = "level"

    def __init__(self, manager):
        super().__init__(manager)
        self.pause_menu = None          # Esc menu; while open the level is paused
        if is_dynamic_level(self.session.level_id):
            # Same seed for the whole run: retry/replay keep one layout.
            if self.session.random_seed is None:
                import random as _random
                self.session.random_seed = _random.SystemRandom().randint(0, 2 ** 31 - 1)
            self.full_level = get_level(self.session.level_id, seed=self.session.random_seed)
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
        self._mips, self._mips_key = [], None       # arrow layers at ZOOM_LEVELS
        self._arrows, self._arrows_key = None, None # arrow layer at the current zoom
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

        # --- Hint (fixed levels) ----------------------------------------------
        # Fixed levels show hand-written hints (hints.toml) in place of the AI
        # Solver and never start it. The answer page marks this run as
        # "solution used": the win is flagged and not recorded as a best.
        self.hint_mode = not is_dynamic_level(self.level.id)
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

        # --- Story (fixed levels, story.toml) ---------------------------------
        # Poland's intro lines play the first time a level opens, the win line
        # the first time it is cleared, a fail line on every life lost.
        self.story = None if is_dynamic_level(self.level.id) else get_level_story(self.level.id)
        self.planet = self.story.planet if self.story else None
        self.dialogue = None
        self._dialogue_seen_key = None      # story_seen key to record when the box closes
        self._win_pending = False           # WinScene waits for the win line
        if self.story is not None:
            self._say(self.story.intro, level_intro_key(self.level.id))

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
        self._hide_collected_coins()
        self.holes = list(getattr(self.level, "holes", ()) or ())
        for alias in ("portals", "wormholes"):
            self.holes = self.holes or list(getattr(self.level, alias, ()) or ())

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

    def handle_event(self, event):
        if event.type == pygame.MOUSEMOTION:
            self._mouse_pos = event.pos
            self._update_cursor()
        if self.state == PANNING:
            return                      # pan to the next section: no input at all
        if self.dialogue is not None:
            self.dialogue.handle_event(event)
            if self.dialogue.done:
                self._close_dialogue()
            return                      # modal: nothing behind it takes input
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

        if self.state == SETUP:
            if event.type == pygame.KEYDOWN and event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self._try_launch()
                return
            if self.editor.handle_event(event):
                return

        if self.level_button.handle_event(event) == "click":
            self.audio.play("click")
            from .levels import LevelSelectScene
            self.manager.switch(LevelSelectScene(self.manager))
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
        self.attempts += 1
        self.flight = Flight(self.field, self.ship, self.level, start=self.launch_pos,
                             pickups=self.pickups, holes=self.holes)
        if any(p.kind == "unbound" for p in self.pickups or ()):
            self._arrow_mips()          # ready before the camera can zoom out
        self.trail.clear()
        self._trail_count = 0
        self._bounces_heard = 0
        self._teleports_heard = 0
        self._replay_teleports = 0
        self.state = FLIGHT
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
            if not self.solution_used and (best is None or self.total_time < best):
                self.session.records[self.level.id] = self.total_time
            # Sync progress to cloud when authenticated.
            account = self.manager.account
            if account is not None and account.is_authenticated() and account.current_user is not None:
                try:
                    from vector_drift.account.integration import session_to_profile
                    profile = session_to_profile(self.session, account.current_user.id)
                    self.session.sync_status = "syncing"
                    def _on_saved():
                        self.session.sync_status = "idle"
                    def _on_save_error(exc):
                        self.session.sync_status = "error"
                        self.session.last_sync_error = str(exc)
                    account.save_profile_async(profile, on_success=_on_saved, on_error=_on_save_error)
                except Exception:
                    pass
            else:
                try:
                    from vector_drift.account.integration import save_guest_profile
                    save_guest_profile(self.session)
                except Exception:
                    pass
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
        if self.story is not None:
            self._say((random_fail_line(),))
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

        Not a win: no Win screen, story line or clear. From now on a lost
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

    def _play_flight_sounds(self):
        """Bounce off a rock / pass through a black hole since the last frame."""
        flight = self.flight
        bounces = getattr(flight, "bounces", 0)
        if bounces > self._bounces_heard:
            self._bounces_heard = bounces
            self.audio.play("bounce")
        teleports = getattr(flight, "teleports", 0)
        if teleports > self._teleports_heard:
            self._teleports_heard = teleports
            self.audio.play("warp")

    def _drain_pickup_events(self):
        """Sync scene state and play sounds for new pickup events (once each).

        The Flight has already applied every effect to itself (see
        Flight._apply_pickup_events). Shockwave destroys obstacles: mirror
        flight.obstacle_specs back into the frozen level (dataclasses.replace
        -> new tuple) so rendering and the next launch both see the
        survivors. The other kinds only play their sound here.
        """
        from dataclasses import replace

        events = self.flight.pickup_events
        if not events:
            return
        for event in events:
            if event.get("kind") == "shockwave":
                destroyed = event.get("destroyed") or ()
                if destroyed:
                    # shockwave_effect already rewrote flight.obstacle_specs to
                    # survivors; just mirror the same list into the frozen
                    # level so rendering / next launch see the survivors.
                    self.flight.obstacle_specs = tuple(
                        o for o in self.flight.obstacle_specs
                        if o not in destroyed
                    )
                    self.level = replace(
                        self.level, obstacles=self.flight.obstacle_specs
                    )
                try:
                    self.audio.play("shockwave")
                except Exception:  # noqa: BLE001 - sfx slot is optional
                    log.debug("shockwave sfx skipped", exc_info=True)
            elif event.get("kind") == "extratime":
                # Flight._apply_pickup_events already extended the flight.
                try:
                    self.audio.play("extratime")
                except Exception:  # noqa: BLE001 - sfx slot is optional
                    log.debug("extratime sfx skipped", exc_info=True)
            elif event.get("kind") == "shield":
                # Flight._apply_pickup_events already started the effect.
                try:
                    self.audio.play("shield")
                except Exception:  # noqa: BLE001 - sfx slot is optional
                    log.debug("shield sfx skipped", exc_info=True)
            elif event.get("kind") == "life":
                # Restore one life if not already full.
                if self.lives < self.level.lives:
                    self.lives += 1
                try:
                    self.audio.play("life")
                except Exception:  # noqa: BLE001 - sfx slot is optional
                    log.debug("life sfx skipped", exc_info=True)
            elif event.get("kind") == "money":
                # Each coin pays once: once ever on a fixed level, once per
                # map on a random level.  After a reveal coins pay nothing
                # and stay collectable for a later run.
                key = self._coin_key(event.get("center"))
                collected = self._collected_coins()
                if not self.solution_used and key not in collected:
                    collected.add(key)
                    amount = event.get("amount", 1)
                    self.session.money.add(amount)
                    self.money = self.session.money
                    self._run_coins.append((key, amount))
                    self._save_profile_if_signed_in()
                try:
                    self.audio.play("money")
                except Exception:  # noqa: BLE001 - sfx slot is optional
                    log.debug("money sfx skipped", exc_info=True)
            elif event.get("kind") == "unbound":
                # Flight._apply_pickup_events already opened the map edge.
                try:
                    self.audio.play("unbound")
                except Exception:  # noqa: BLE001 - sfx slot is optional
                    log.debug("unbound sfx skipped", exc_info=True)
            elif event.get("kind") == "shield_used":
                # The protection broke on a bumper (the ship still passes it).
                try:
                    self.audio.play("shield_break")
                except Exception:  # noqa: BLE001 - sfx slot is optional
                    log.debug("shield_break sfx skipped", exc_info=True)
        self.flight.pickup_events = []
        # self.pickups holds the SAME PickupState objects the Flight just
        # consumed (passed by reference), so no re-sync is needed: used
        # pickups stay gone for the rest of this run's lives.

    def _safe_end_flight(self, outcome, banner=None):
        """End-of-flight bookkeeping that never raises out of update()."""
        try:
            self._end_flight(outcome)
        except _PHYSICS_ERRORS as exc:
            # State may be half-updated (lives/trail); log and force a
            # consistent SETUP so the next launch starts clean.
            log.warning("end-flight %s contained: %r", outcome, exc)
            self.flight = None
            self.launch_pos = self.level.start
            self.state = SETUP
            self._refresh_buttons()
        except Exception:  # noqa: BLE001 - last-resort guard: frame loop must live
            log.exception("unexpected end-flight failure")
            self.flight = None
            self.launch_pos = self.level.start
            self.state = SETUP
            try:
                self._refresh_buttons()
            except _RENDER_ERRORS:
                pass

        if banner is not None:
            try:
                title, sub = banner
                self.banner = (title, sub, config.BANNER_DURATION)
            except _RENDER_ERRORS as exc:
                log.warning("banner update contained: %r", exc)

    # ------------------------------------------------------------------ update
    def update(self, dt):
        self.t += dt
        if not self.hint_mode:
            self._update_ai()
            self._note_ai_answer_shown()
        try:
            self.editor.update(dt)
        except _RENDER_ERRORS as exc:
            log.warning("editor update contained: %r", exc)
        except Exception:  # noqa: BLE001 - last-resort guard: frame loop must live
            log.exception("unexpected editor failure")
        if self.dialogue is not None:
            self.dialogue.update(dt)
        if self.pause_menu is None:     # paused: flight, banner and arrival wait
            self._update_flight(dt)
            self._update_camera(dt)

    def _camera_target(self):
        """(zoom the camera eases toward, most it may lag behind while zooming out).

        Out while an unbound ship is off the map, else 1. The second value is
        the zoom that still keeps the whole ship on screen.
        """
        flight = self.flight
        if flight is None or not getattr(flight, "unbound", False) or self.state not in (FLIGHT, ARRIVED):
            return 1.0, 1.0
        pos = (flight.x, flight.y)
        return (fit_zoom(pos, flight.bounds, flight.outer_bounds, margin=CAMERA_MARGIN_M),
                fit_zoom(pos, flight.bounds, flight.outer_bounds, margin=0.5 * self.ship.length))

    def _update_camera(self, dt):
        """Ease the camera zoom toward its target (smooth out and back in).

        Zooming out never falls behind a fast ship: it stays on screen.
        """
        target, keep_ship = self._camera_target()
        zoom = self.camera.zoom
        if zoom == target:
            return
        zoom += (target - zoom) * (1.0 - math.exp(-dt / CAMERA_EASE_S))
        zoom = min(zoom, keep_ship)
        self.camera.zoom = target if abs(target - zoom) < 1e-3 else zoom

    def _update_ai(self):
        """Random levels: restart the solver on a new state, poll the running job."""
        key = self._state_key()
        if key != self._last_state_key:
            self._last_state_key = key
            self._kick_ai_for_state()
        # Poll the offline solver job on the main thread (never blocks PyGame).
        if self.ai_job is not None and not self.ai_job.running:
            job_key = self.ai_job_state_key
            current_key = self._state_key()
            if self.ai_job.error is not None:
                if job_key == current_key:
                    self.ai_status = "error"
                    self.ai_message = f"Solver Error: {self.ai_job.error}"
            else:
                if job_key == current_key:
                    self.ai_best_by_state[job_key] = self.ai_job.result
                    self.ai_result = self.ai_job.result
                    self.ai_status = "ready"
                    self.ai_message = (self.ai_job.result.message
                                       if self.ai_job.result is not None else "")
            self.ai_job = None
            self.ai_job_state_key = None

    def _update_flight(self, dt):
        if self.banner:
            title, sub, left = self.banner
            self.banner = (title, sub, left - dt) if left > dt else None

        if self.state == FLIGHT:
            try:
                outcome = self.flight.advance(dt)
            except _PHYSICS_ERRORS as exc:
                log.warning("flight advance (%s) -> DIVERGED: %r", type(exc).__name__, exc)
                outcome = Outcome.DIVERGED
                self.flight.outcome = Outcome.DIVERGED
            except Exception:  # noqa: BLE001 - internal bug vs DIVERGED must be loud
                log.exception("unexpected flight failure; forcing DIVERGED")
                outcome = Outcome.DIVERGED
                try:
                    self.flight.outcome = Outcome.DIVERGED
                except _RENDER_ERRORS:
                    pass
            try:
                self._sync_trail()
            except _RENDER_ERRORS as exc:
                log.warning("trail sync contained: %r", exc)
            except Exception:  # noqa: BLE001 - last-resort guard: frame loop must live
                log.exception("unexpected trail-sync failure")
            self._play_flight_sounds()
            try:
                self._drain_pickup_events()
            except _RENDER_ERRORS as exc:
                log.warning("pickup sync contained: %r", exc)
            except Exception:  # noqa: BLE001 - last-resort guard: frame loop must live
                log.exception("unexpected pickup-sync failure")
            try:
                x, y, vx, vy, fx, fy = self._ship_state()
                frame = {
                    "t": float(getattr(self.flight, "time", 0.0)),
                    "x": float(x), "y": float(y),
                    "vx": float(vx), "vy": float(vy),
                    "fx": float(fx), "fy": float(fy),
                }
                teleports = getattr(self.flight, "teleports", 0)
                if teleports > self._replay_teleports:
                    frame["warp"] = True        # the replay trail breaks here
                    self._replay_teleports = teleports
                self._replay_frames.append(frame)
            except Exception:
                pass
            if outcome is not Outcome.RUNNING:
                self._safe_end_flight(outcome)
        elif self.state == PANNING:
            self.pan.t += dt
            if self.pan.t >= config.CHECKPOINT_PAN_DURATION:
                self._finish_pan()
        elif self.state == ARRIVED:
            self.arrive_timer -= dt
            if self.arrive_timer <= 0 and self.dialogue is None and not self._win_pending:
                key = level_win_key(self.level.id)
                if self.story is not None and key not in self.session.story_seen:
                    self._win_pending = True
                    self._say(self.story.win, key)
                    return
            if self.arrive_timer <= 0 and self.dialogue is None:
                self.session.stats = {
                    "time": self.flight.time,
                    "total_time": self.total_time,
                    "attempts": self.attempts,
                    "lives_left": self.lives,
                    "max_lives": self.level.lives,
                    "fx": self.editor.lines[0].strip() or "0",
                    "fy": self.editor.lines[1].strip() or "0",
                    "solution_used": self.solution_used,
                    "clear_reward": self._clear_reward,
                    "coins_earned": (sum(amount for _key, amount in self._run_coins)
                                     + self._clear_reward),
                }
                from .win import WinScene
                self.manager.switch(WinScene(self.manager, self._snapshot()))

    # ------------------------------------------------------------------ draw
    def draw(self, surface):
        surface.fill(config.BG)
        self._draw_plot(surface)
        self._draw_panel(surface)
        if self.ai_popup:
            self._draw_ai_popup(surface)
        if self.hint_popup is not None:
            self.hint_popup.answer_price = self._answer_price()
            self.hint_popup.available = self._available_coins()
            self.hint_popup.draw(surface)
        if self.dialogue is not None:
            self.dialogue.draw(surface)
        self._draw_coins(surface)
        if self.pause_menu is not None:
            self.pause_menu.draw(surface)

    def _draw_coins(self, surface):
        """Available balance, top-right of the plot, above every other layer."""
        draw_coins(surface, int(self.session.money), (config.WINDOW_W - px(14), px(12)), 16,
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

    # ------------------------------------------------------------------ Story
    def _say(self, lines, seen_key=None):
        """Open the dialogue box; ``seen_key`` is recorded once it closes."""
        if seen_key is not None and seen_key in self.session.story_seen:
            return
        self.dialogue = DialogueBox(lines, self.viewport.rect, self.audio)
        self._dialogue_seen_key = seen_key

    def _close_dialogue(self):
        self.dialogue = None
        key, self._dialogue_seen_key = self._dialogue_seen_key, None
        if key is not None:
            self.session.story_seen.add(key)
            from vector_drift.account.integration import save_progress
            save_progress(self.manager.account, self.session)
            
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
        popup.confirm_text = confirm_text(price, len(self._run_coins))
        popup.confirm_price = coin_price_parts(price, available) if price else None
        popup.confirming = True

    def _show_hint_answer(self, price=0):
        """Open the answer page: a reveal, paid with ``price`` coins."""
        self._reveal_solution()
        if price:
            self.session.money.spend(price)
            self.money = self.session.money
            self.session.paid_answer_levels.add(self.level.id)
            self._save_profile_if_signed_in()
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
        """Balance once this run's coins are taken back: what a reveal can spend."""
        return int(self.session.money) - sum(amount for _key, amount in self._run_coins)

    def _reveal_solution(self):
        """A full answer is shown (Hint answer page or AI Solver reveal).

        This run's coins are taken back and become collectable again, and the
        run is marked "solution used" so a clear won't set a best time.
        """
        collected = self._collected_coins()
        for key, amount in self._run_coins:
            self.session.money.spend(amount)
            collected.discard(key)
        self._run_coins = []
        self.money = self.session.money
        self.solution_used = True
        self._save_profile_if_signed_in()

    def _pay_clear_reward(self):
        """Reaching the target pays once per fixed level (saved) or random map.

        A run that used a solution pays nothing and leaves the reward for a
        later clean clear.
        """
        self._clear_reward = 0
        if self.solution_used:
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

    def _save_profile_if_signed_in(self) -> None:
        """Upload the current session to Supabase when signed in.

        Called right after ``session.money`` (or other profile data) changes
        so progress is not lost when the player quits the level without
        clearing it.  Guests are intentionally left untouched.
        """
        from vector_drift.account.integration import save_profile_if_authenticated

        save_profile_if_authenticated(self.manager.account, self.session)

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
        self._save_profile_if_signed_in()

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

    def _ship_state(self):
        """Return (x, y, vx, vy, fx, fy) for the ship right now.

        Diverged force reads as (nan, nan) so callers can distinguish
        "no valid force" from (0, 0); draw/telemetry paths sanitize it to
        zeros / "—" for display.
        """
        if self.flight is not None:
            f = self.flight
            fx, fy = f.force
            return f.x, f.y, f.vx, f.vy, fx, fy
        x, y = self.launch_pos
        try:
            fx, fy = self.field.at(x, y)
        except (ArithmeticError, ValueError, TypeError, OverflowError,
                RecursionError, MemoryError):
            fx = fy = float("nan")
        return x, y, 0.0, 0.0, fx, fy

    def _plot_base_surface(self):
        """Background + arrow field + tick labels as one opaque surface (cached)."""
        dim = not self.valid and self.state == SETUP
        key = (self._field_version, dim)
        if key != self._plot_key:
            base = self.background.copy()
            if self.field_layer is not None:
                self.field_layer.set_alpha(70 if dim else 255)
                base.blit(self.field_layer, (0, 0))
                self.field_layer.set_alpha(255)
            base.blit(self.labels, (0, 0))
            self._plot_base = base.convert() if pygame.display.get_surface() else base
            self._plot_key = key
        return self._plot_base

    # ------------------------------------------------------------------ zoomed view
    def _scratch_layer(self):
        """The plot-sized transparent scratch layer, cleared."""
        size = (self.viewport.width, self.viewport.height)
        if self._overlay is None or self._overlay.get_size() != size:
            self._overlay = pygame.Surface(size, pygame.SRCALPHA)
        self._overlay.fill((0, 0, 0, 0))
        return self._overlay

    def _arrow_mips(self):
        """Arrow layers drawn at ZOOM_LEVELS, each covering what that zoom shows (cached).

        The zoom-1 one is the map's own field layer. All share its length per
        newton (arrows for larger forces off the map are capped at the
        longest length), so the arrows keep their size as the camera zooms.
        """
        if self.field_layer is None:
            return []
        key = self._field_version
        if key != self._mips_key:
            mips = []
            for zoom in ZOOM_LEVELS:
                if zoom == 1.0:
                    mips.append((zoom, self.field_layer))
                    continue
                try:
                    layer, _ = render.make_field_layer(Viewport(zoom=zoom), self.field,
                                                       max_mag=self.max_force)
                except _PHYSICS_ERRORS + _RENDER_ERRORS as exc:
                    log.warning("zoomed field layer contained: %r", exc)
                    continue
                mips.append((zoom, layer))
            self._mips, self._mips_key = mips, key
        return self._mips

    def _zoomed_arrows(self):
        """The arrow layer at the camera's zoom: the nearest prepared one, stretched.

        Stretching from the next zoom down is at most ZOOM_LEVELS' ratio
        (about 1.26), so arrows stay sharp. Cached while the zoom holds still.
        """
        zoom = self.camera.zoom
        dim = not self.valid and self.state == SETUP
        key = (self._field_version, dim, zoom)
        if key == self._arrows_key:
            return self._arrows
        arrows = None
        below = [(z, layer) for z, layer in self._arrow_mips() if z <= zoom + 1e-9]
        if below:
            base_zoom, layer = max(below, key=lambda m: m[0])
            w, h = layer.get_size()
            part = pygame.Rect(0, 0, round(w * base_zoom / zoom), round(h * base_zoom / zoom))
            part.center = (w // 2, h // 2)
            part = part.clip(layer.get_rect())
            if part.size != (w, h) and part.w and part.h:
                arrows = pygame.transform.smoothscale(layer.subsurface(part), (w, h))
            elif part.size == (w, h):
                arrows = layer.copy() if dim else layer     # never change the shared layer
            if arrows is not None and dim:
                arrows.set_alpha(70)
        self._arrows, self._arrows_key = arrows, key
        return arrows

    def _draw_zoomed_base(self, surface, plot):
        """Stars, grid, arrows and tick labels at the camera's zoom.

        The stars stay put (far backdrop); the grid and labels are drawn at
        the zoomed scale, the arrows come from _zoomed_arrows. Drawn straight
        onto the screen: the zoom changes nearly every frame, so a cached
        composite would only cost a copy.
        """
        if self._space_screen is None:
            self._space_screen = (self._space.convert() if pygame.display.get_surface()
                                  else self._space)
        surface.blit(self._space_screen, plot.topleft)
        layer = self._scratch_layer()
        render.draw_grid(layer, self.camera)
        surface.blit(layer, plot.topleft)
        arrows = self._zoomed_arrows()
        if arrows is not None:
            surface.blit(arrows, plot.topleft)
        render.draw_plot_labels(surface.subsurface(plot), self.camera)

    def _draw_world_trails(self, surface, plot, current):
        """The earlier legs (dimmed), or with ``current`` this flight's trail, at the camera's zoom.

        Used while zoomed: the trail layers hold zoom-1 pixels, so these are
        drawn from the world points instead (same width and colour).
        """
        cam = self.camera
        if current:
            legs = [] if self.flight is None else [
                (self.flight.trail, getattr(self.flight, "trail_breaks", ()))]
            target, color = surface.subsurface(plot), config.TRAIL
        else:
            legs = self._history_legs
            target, color = self._scratch_layer(), (*config.TRAIL, HISTORY_ALPHA)
        if not legs:
            return
        width = max(1, round(2.4 * config.UI_SCALE))
        cull = config.MAX_PX_CULL
        for pts, breaks in legs:
            cut = sorted({0, *breaks, len(pts)})
            for lo, hi in zip(cut, cut[1:]):
                if hi - lo < 2:
                    continue
                try:
                    line = [(min(max(sx - plot.x, -cull), plot.w + cull),
                             min(max(sy - plot.y, -cull), plot.h + cull))
                            for sx, sy in (cam.to_screen(x, y) for x, y in pts[lo:hi])]
                    pygame.draw.lines(target, color, False, line, width)
                except (TypeError, ValueError, OverflowError) as exc:
                    log.debug("zoomed trail skipped: %r", exc)
        if not current:
            surface.blit(target, plot.topleft)

    def _draw_unbound_edge(self, surface):
        """While Unbound is active the map edge is a dashed line: it is open."""
        flight = self.flight
        if flight is None or not getattr(flight, "unbound", False):
            return
        hx, hy = flight.bounds
        left, top = self.camera.to_screen(-hx, hy)
        right, bottom = self.camera.to_screen(hx, -hy)
        width = max(2, px(2))
        inset = width / 2           # at zoom 1 the edge is the plot's own edge
        render.draw_dashed_rect(surface, (left + inset, top + inset,
                                          right - left - 2 * inset, bottom - top - 2 * inset),
                                UNBOUND_EDGE, width, dash=px(10), gap=px(7))

    def _draw_plot(self, surface):
        vp = self.camera
        zoomed = vp.zoom != 1.0
        plot = pygame.Rect(vp.rect)
        try:
            if zoomed:
                self._draw_zoomed_base(surface, plot)
            else:
                surface.blit(self._plot_base_surface(), plot.topleft)
        except _RENDER_ERRORS as exc:
            log.warning("plot base blit contained: %r", exc)

        prev_clip = surface.get_clip()
        try:
            surface.set_clip(plot)
        except _RENDER_ERRORS as exc:
            log.warning("set_clip contained: %r", exc)

        try:
            pan = self.pan if self.state == PANNING else None
            if pan is not None:
                old_offset, offset = pan_offsets(pan.shift, pan.progress)
                self._draw_panning_out(surface, plot, pan, old_offset)
                old_px = self._offset_px(old_offset)
            else:
                offset = (0.0, 0.0)
                hb = self.history_bounds
                if zoomed:
                    self._draw_world_trails(surface, plot, current=False)
                elif hb.w and hb.h:
                    surface.blit(self.history, (plot.x + hb.x, plot.y + hb.y), hb)
                self._draw_unbound_edge(surface)

            flash = 0.0
            if self.state == ARRIVED:
                flash = max(0.0, self.arrive_timer / config.WIN_DELAY)
            self._draw_section(surface, self.level, self.pickups, self.holes, offset,
                               index=self.section_index, launch=self.launch_pos, flash=flash)

            if pan is not None and pan.t < CHECKPOINT_LIFE_POP_S:
                # The checkpoint's life was just taken: it pops off the checkpoint.
                start = self.level.start
                sprites.draw_checkpoint_life(
                    surface, vp.to_screen(start[0] + offset[0], start[1] + offset[1]),
                    vp.length(self._checkpoint_radius(self.section_index)), self.t,
                    self.flyable_ship, fade=pan.t / CHECKPOINT_LIFE_POP_S)
            if pan is not None:
                # The leg that reached the checkpoint leaves with the old section.
                self.trail.draw(surface, (plot.x + old_px[0], plot.y + old_px[1]))
                self._draw_panning_ship(surface, pan, old_offset)
                return                  # (no labels or banner while panning)
            if self.flight is not None:
                if zoomed:
                    self._draw_world_trails(surface, plot, current=True)
                else:
                    self.trail.draw(surface, plot.topleft)

            x, y, vx, vy, fx, fy = self._ship_state()
            for v in (x, y, vx, vy, fx, fy):
                if not isinstance(v, (int, float)) or not math.isfinite(v):
                    vx = vy = fx = fy = 0.0
                    break
            if math.hypot(vx, vy) > 1e-6:
                try:
                    self.heading = math.atan2(vy, vx)
                except (ValueError, OverflowError):
                    pass
            elif math.hypot(fx, fy) > 1e-9:
                try:
                    self.heading = math.atan2(fy, fx)
                except (ValueError, OverflowError):
                    pass
            try:
                ship_pos = vp.to_screen(x, y)
            except (TypeError, ValueError, OverflowError):
                ship_pos = None
            if ship_pos is not None:
                if self.state in (FLIGHT, ARRIVED):
                    # draw_vector/draw_ship are themselves total (never raise
                    # for bad numbers), so no try/except needed here.
                    sprites.draw_vector(surface, ship_pos, (vx, vy), config.VELOCITY_VEC)
                    sprites.draw_vector(surface, ship_pos, (fx, fy), config.FORCE_VEC)
                sprites.draw_ship(surface, ship_pos, self.heading, vp.length(self.ship.length), self.ship)
                if self.flight is not None and self.flight.shield_remaining > 0.0:
                    sprites.draw_shield(surface, ship_pos, vp.length(0.6 * self.ship.length), self.t)
        finally:
            try:
                surface.set_clip(prev_clip)
            except _RENDER_ERRORS as exc:
                log.warning("restore clip contained: %r", exc)
        try:
            self._draw_plot_labels(surface, plot)
            if self.banner:
                self._draw_banner(surface, plot)
        except _RENDER_ERRORS as exc:
            log.warning("plot overlay contained: %r", exc)

    # ------------------------------------------------------------------ sections
    def _offset_px(self, offset):
        """A world offset (m) as a screen offset (px); y points down on screen."""
        scale = self.viewport.scale
        return (offset[0] * scale, -offset[1] * scale)

    def _checkpoint_radius(self, index):
        """Radius (m) of the checkpoint section ``index`` starts on (index >= 1)."""
        return self.full_level.sections[index - 1].target_radius

    def _draw_section(self, surface, level, pickups, holes, offset, index, launch=None, flash=0.0,
                      target=True):
        """One section's start, target and props, shifted by ``offset`` (m).

        ``index`` is the section's number (0-based): from the second section
        on its start is the checkpoint just reached, and every target but the
        last section's is a checkpoint. ``launch`` is where the next launch
        starts (None: no launch pad, for the section the camera is leaving).
        ``target=False`` skips the target (while panning, the section being
        left shares its checkpoint with the next section's start).
        """
        vp = self.camera
        ox, oy = offset

        def at(x, y):
            return vp.to_screen(x + ox, y + oy)

        start = tuple(level.start)
        if index > 0:
            sprites.draw_checkpoint(surface, at(*start), vp.length(self._checkpoint_radius(index)),
                                    self.t, self.flyable_ship)
        if launch is not None:
            launch = tuple(launch)
            if index == 0 and launch != start:
                # Faint marker at the original start ("back to start" target).
                pygame.draw.circle(surface, config.TEXT_FAINT, at(*start), px(3))
            if index == 0 or launch != start:
                sprites.draw_start_marker(surface, at(*launch), vp.length(START_MARKER_RADIUS_M), self.t)
        elif index == 0:
            sprites.draw_start_marker(surface, at(*start), vp.length(START_MARKER_RADIUS_M), self.t)

        if target:
            center, radius = at(*level.target_center), vp.length(level.target_radius)
            if index < self.section_total - 1:
                sprites.draw_checkpoint(surface, center, radius, self.t, self.flyable_ship)
                # Not reached yet: it still holds the life it gives.
                sprites.draw_checkpoint_life(surface, center, radius, self.t, self.flyable_ship)
            else:
                sprites.draw_target(surface, center, radius, self.t, flash, planet=self.planet)

        for obstacle in getattr(level, "obstacles", ()) or ():
            sprites.draw_obstacle(surface, at(*obstacle.center),
                                  vp.length(obstacle.radius), self.t,
                                  kind=getattr(obstacle, "kind", "bumper"),
                                  seed=(obstacle.center, obstacle.radius))

        for pickup in pickups or ():
            if pickup.consumed:
                continue
            sprites.draw_pickup(surface, at(*pickup.center),
                                vp.length(pickup.radius), self.t, kind=pickup.kind)

        for i, hole in enumerate(holes or (), start=1):
            try:
                bc = hole.black_center if hasattr(hole, "black_center") else hole[0]
                wc = hole.white_center if hasattr(hole, "white_center") else hole[1]
                r = getattr(hole, "radius", 0.5)
                sprites.draw_hole(surface, at(*bc), vp.length(r), self.t, kind="black", pair_index=i)
                sprites.draw_hole(surface, at(*wc), vp.length(r), self.t, kind="white", pair_index=i)
                # Pair marker so players can see which black hole maps to which white hole.
                # The white-hole picture is white in the middle, so its number is dark.
                for center, color in ((bc, config.TEXT), (wc, config.OUTLINE)):
                    draw_text(surface, str(i), at(*center), 12, color, kind="bold", anchor="center")
            except Exception:
                pass

    def _draw_panning_out(self, surface, plot, pan, offset):
        """The section the camera is leaving (its checkpoint is drawn by the new one)."""
        hb = self.history_bounds
        if hb.w and hb.h:
            dx, dy = self._offset_px(offset)
            surface.blit(self.history, (plot.x + hb.x + dx, plot.y + hb.y + dy), hb)
        self._draw_section(surface, pan.level, pan.pickups, pan.holes, offset,
                           index=self.section_index - 1, target=False)

    def _draw_panning_ship(self, surface, pan, offset):
        """The ship glides from where it touched the checkpoint onto its center."""
        vp = self.camera
        p = pan.progress
        (ax, ay), (tx, ty) = pan.arrival, pan.level.target_center
        x, y = ax + (tx - ax) * p, ay + (ty - ay) * p
        sprites.draw_ship(surface, vp.to_screen(x + offset[0], y + offset[1]), self.heading,
                          vp.length(self.ship.length), self.ship)

    def _draw_plot_labels(self, surface, plot):
        x, y = plot.x + px(14), plot.y + px(12)
        if self.state in (FLIGHT, ARRIVED):
            draw_text(surface, "FIELD LOCKED", (x, y), 13, config.ACCENT, kind="bold")
            ly = plot.bottom - px(28)
            draw_text(surface, "→ force", (x, ly), 14, config.FORCE_VEC, kind="bold")
            draw_text(surface, "→ velocity", (x + px(80), ly), 14, config.VELOCITY_VEC, kind="bold")
        elif not self.valid:
            draw_text(surface, "Showing last valid field", (x, y), 13, config.WARNING, kind="bold")

    def _draw_banner(self, surface, plot):
        title, sub, left = self.banner
        alpha = min(1.0, left / 0.5)
        layer = pygame.Surface((plot.width, px(120)), pygame.SRCALPHA)
        box = pygame.Rect(0, px(10), px(500), px(100))
        box.centerx = plot.width // 2
        pygame.draw.rect(layer, (8, 12, 26, 200), box, border_radius=px(6))
        pygame.draw.rect(layer, (*config.WARNING, 220), box, max(1, px(1)), border_radius=px(6))
        draw_text(layer, title, (plot.width // 2, px(50)), 38, config.WARNING, kind="bold", anchor="center")
        draw_text(layer, sub, (plot.width // 2, px(88)), 16, config.TEXT, anchor="center")
        layer.set_alpha(round(255 * alpha))
        surface.blit(layer, (plot.x, plot.y + px(70)))

    # ------------------------------------------------------------------ left panel
    def _draw_panel(self, surface):
        panel = pygame.Rect(0, 0, config.PANEL_W, config.WINDOW_H)
        pygame.draw.rect(surface, config.PANEL_BG, panel)
        pygame.draw.line(surface, config.PANEL_EDGE, panel.topright, panel.bottomright, max(2, px(2)))
        cx = px(CX)

        if not sprites.draw_logo(surface, (cx, px(LOGO_Y)), px(LOGO_W)):
            draw_text(surface, "VECTOR DRIFT", (cx, px(LOGO_Y)), 26, config.TEXT, kind="bold", anchor="center")

        # Level row: "LV1" + level-select button
        draw_text(surface, f"LV{self.level.id}", (px(CX - 26), px(LEVEL_ROW_Y)), 22, config.TEXT,
                  kind="bold", anchor="center")
        self.level_button.draw(surface)

        # Current ship
        draw_text(surface, "Current ship", (cx, px(SHIP_LABEL_Y)), 15, config.TEXT_DIM, anchor="center")
        draw_panel_box(surface, SHIP_BOX, fill=config.BG)
        unlocked = self._ship_unlocked
        sprites.draw_ship(surface, SHIP_BOX.center, math.pi / 4 + 0.12 * math.sin(self.t * 1.3),
                          px(76), self.ship, grey=not unlocked)
        if not unlocked:
            lock = icon_surface("lock", px(22), config.TEXT_DIM)
            surface.blit(lock, lock.get_rect(bottomright=(SHIP_BOX.right - px(6), SHIP_BOX.bottom - px(6))))
        self.prev_ship.draw(surface)
        self.next_ship.draw(surface)
        draw_text(surface, self.ship.name, (cx, px(SHIP_NAME_Y)), 18,
                  config.TEXT if unlocked else config.TEXT_DIM, kind="bold", anchor="center")
        if unlocked:
            draw_text(surface, f"Mass: {self.ship.mass:g} kg", (cx, px(SHIP_MASS_Y)), 15, config.TEXT_DIM,
                      anchor="center")
        else:
            draw_text(surface, f"Lv{self.ship.unlock_level}+", (cx, px(SHIP_MASS_Y)), 15, config.WARNING,
                      kind="bold", anchor="center")

        # Lives + clock (the lives show the ship that would fly, not a locked one on display)
        icon_step = px(18)
        first = px(CX - 52) - icon_step * (self.level.lives - 1) // 2
        for i in range(self.level.lives):
            sprites.draw_ship_icon(surface, (first + i * icon_step, px(STATUS_Y)), px(18),
                                   self.flyable_ship, alive=i < self.lives)
        time_left = self.flight.time_left if self.flight is not None else self.level.time_limit
        time_color = config.WARNING if self.state == FLIGHT and time_left < 1.0 else config.TEXT
        draw_text(surface, fmt_clock(time_left), (px(CX + 62), px(STATUS_Y)), 24, time_color,
                  kind="mono", anchor="center")

        # Vector_field / PROBLEMS / TELEMETRY panel
        self.editor.draw(surface)
        self.run_button.draw(surface)
        self._draw_telemetry(surface, self.editor.footer_body)

        # Longest arrow legend
        draw_text(surface, "Longest arrow", (cx, px(LEGEND_LABEL_Y)), 14, config.TEXT_DIM, anchor="center")
        render.draw_legend(surface, (cx, px(LEGEND_Y)), self.max_force)

        if self.hint_mode:
            # Hint button (fixed levels): usable any time before the win.
            self.ai_button.enabled = self.hint is not None and self.state != ARRIVED
            self.ai_button.label = "Hint"
        else:
            # AI assistant button (offline solver): always open, solving is free.
            self.ai_button.enabled = True
            self.ai_button.label = ("AI Solver" if self.ai_status != "error"
                                    else "AI Solver (Failed)")
        self.ai_button.draw(surface)

    def _draw_telemetry(self, surface, area):
        in_flight = self.flight is not None
        x, y, vx, vy, fx, fy = self._ship_state()
        rows = [
            ("Position", fmt_pair(x, y, "m"), config.TEXT),
            ("Velocity", fmt_pair(vx, vy, "m/s"), config.VELOCITY_VEC),
            ("Speed", f"{math.hypot(vx, vy):.2f} m/s", config.VELOCITY_VEC),
            ("Force", fmt_pair(fx, fy, "N"), config.FORCE_VEC),
        ]
        for i, (label, value, color) in enumerate(rows):
            ry = area.y + px(TELEMETRY_ROW_H * i + TELEMETRY_ROW_H // 2 + 2)
            draw_text(surface, label, (area.x + px(12), ry), 13, config.TEXT_DIM, anchor="midleft")
            if not in_flight:
                value, color = "—", config.TEXT_FAINT
            draw_text(surface, value, (area.right - px(12), ry), 13, color, kind="mono", anchor="midright")
