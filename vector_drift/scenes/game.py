"""Game screen: set up the force field, launch, watch the flight."""

import logging
import math

import pygame

from .. import config, render, sprites
from ..config import px
from ..desktop import set_cursor
from ..coords import Viewport
from ..data import SHIPS, get_level
from ..expr_parser import diagnose_expression
from ..physics import Flight, ForceField, Outcome
from ..ui import CodeEditor, IconButton, draw_panel_box, draw_text
from .base import Scene

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

OUTCOME_TEXT = {
    Outcome.TIMEOUT: "TIME UP",
    Outcome.OUT_OF_BOUNDS: "OUT OF BOUNDS",
    Outcome.DIVERGED: "DIVERGED",
    Outcome.ABORTED: "ABORTED",
}
# After these outcomes the next launch starts (at rest) where the ship stopped;
# every other miss (abort, out of bounds, diverged) goes back to the level start.
RESUME_OUTCOMES = (Outcome.TIMEOUT,)

START_MARKER_RADIUS_M = 0.45
HISTORY_ALPHA = 110          # earlier legs of the current run
RUN_GREEN = (137, 209, 133)


def R(x, y, w, h):
    """Rect from logical pixels."""
    return pygame.Rect(px(x), px(y), px(w), px(h))


# Left panel layout in logical pixels (scaled with px / R)
PAD = 20
CX = 160                     # panel center line
CONTENT_W = 320 - 2 * PAD
LOGO_Y = 36
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


class GameScene(Scene):
    def __init__(self, manager):
        super().__init__(manager)
        if self.session.level_id == config.RANDOM_LEVEL_ID:
            # Same seed for the whole run: retry/replay keep one layout.
            if self.session.random_seed is None:
                import random as _random
                self.session.random_seed = _random.SystemRandom().randint(0, 2 ** 31 - 1)
            self.level = get_level(self.session.level_id, seed=self.session.random_seed)
        else:
            self.level = get_level(self.session.level_id)
        self.owned_ships = list(SHIPS)          # all ships the player may pick (shop comes later)
        ship_id = self.session.ship_id or self.level.ship_id
        self.ship_index = self.owned_ships.index(ship_id)
        self.ship = SHIPS[ship_id]

        self.viewport = Viewport()
        self.background = render.make_plot_background(self.viewport)
        self.labels = render.make_plot_labels(self.viewport)
        plot_size = (self.viewport.width, self.viewport.height)
        self.trail = sprites.TrailLayer(plot_size)
        self.history = pygame.Surface(plot_size, pygame.SRCALPHA)
        self.history_bounds = pygame.Rect(0, 0, 0, 0)
        self._trail_count = 0
        self._plot_base = None          # background + arrows + labels, pre-composited
        self._plot_key = None
        self._field_version = 0

        self.lives = self.level.lives
        self.attempts = 0
        self.total_time = 0.0
        self.state = SETUP
        self.flight = None
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
        self.editor.set_lines([self.session.fx_text, self.session.fy_text])

    def _heading_to_target(self):
        tx = self.level.target_center[0] - self.launch_pos[0]
        ty = self.level.target_center[1] - self.launch_pos[1]
        return math.atan2(ty, tx)

    # ------------------------------------------------------------------ input
    def _on_text_change(self, editor):
        fx_text, fy_text = editor.lines
        self.session.fx_text, self.session.fy_text = fx_text, fy_text

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

        self._refresh_buttons()

    def _refresh_buttons(self):
        if self.state == FLIGHT:
            self.run_button.icon, self.run_button.color = "stop", config.DANGER
            self.run_button.enabled = True
        else:
            self.run_button.icon, self.run_button.color = "play", RUN_GREEN
            self.run_button.enabled = self.state == SETUP and self.valid
        setup = self.state == SETUP
        self.level_button.enabled = setup
        self.prev_ship.enabled = self.next_ship.enabled = setup and len(self.owned_ships) > 1
        self.editor.enabled = setup
        self._update_cursor()

    def _switch_ship(self, step):
        self.ship_index = (self.ship_index + step) % len(self.owned_ships)
        self.session.ship_id = self.owned_ships[self.ship_index]
        self.ship = SHIPS[self.session.ship_id]
        self.audio.play("click")

    def _update_cursor(self):
        set_cursor("text" if self.editor.is_text_area(self._mouse_pos) else "arrow")

    def handle_event(self, event):
        if event.type == pygame.MOUSEMOTION:
            self._mouse_pos = event.pos
            self._update_cursor()
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
        elif self.state == FLIGHT:
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self._abort()
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

    # ------------------------------------------------------------------ flow
    def _try_launch(self):
        if not self.valid:
            self.audio.play("error")
            return
        self.attempts += 1
        self.flight = Flight(self.field, self.ship, self.level, start=self.launch_pos)
        self.trail.clear()
        self._trail_count = 0
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
        self.audio.stop_loop("thruster_loop")
        self._sync_trail()
        self.total_time += self.flight.time
        if outcome is Outcome.REACHED:
            self.state = ARRIVED
            self.arrive_timer = config.WIN_DELAY
            best = self.session.records.get(self.level.id)
            if best is None or self.total_time < best:
                self.session.records[self.level.id] = self.total_time
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
        if outcome in RESUME_OUTCOMES:
            # Keep this leg visible (dimmed) and continue from where the ship stopped.
            self.launch_pos = (self.flight.x, self.flight.y)
            leg = self.trail.bounds
            if leg.w and leg.h:
                self.trail.draw(self.history, (0, 0), HISTORY_ALPHA)
                hb = self.history_bounds
                self.history_bounds = hb.union(leg) if hb.w and hb.h else leg.copy()
            where = f"resume from ({self.launch_pos[0]:.2f}, {self.launch_pos[1]:.2f})"
        else:
            self.launch_pos = self.level.start
            self.history.fill((0, 0, 0, 0), self.history_bounds)
            self.history_bounds = pygame.Rect(0, 0, 0, 0)
            where = "back to start"
        self.trail.clear()
        self.banner = (reason, f"{self.lives} {noun} left · {where}", config.BANNER_DURATION)
        self.flight = None
        self.heading = self._heading_to_target()
        self.state = SETUP
        self._refresh_buttons()

    def _snapshot(self):
        screen = self.manager.screen or pygame.display.get_surface()
        return screen.copy() if screen is not None else None

    def _sync_trail(self):
        """Feed new flight points into the smooth trail layer."""
        if self.flight is None:
            return
        pts = self.flight.trail
        if len(pts) <= self._trail_count:
            return
        vp = self.viewport
        try:
            new = [(vp.cx - vp.left + x * vp.scale, vp.cy - vp.top - y * vp.scale)
                   for x, y in pts[self._trail_count:]]
        except (TypeError, ValueError, OverflowError):
            self._trail_count = len(pts)
            return
        try:
            self.trail.extend(new)
        except _RENDER_ERRORS as exc:
            log.warning("trail extend contained: %r", exc)
        self._trail_count = len(pts)

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
        try:
            self.editor.update(dt)
        except _RENDER_ERRORS as exc:
            log.warning("editor update contained: %r", exc)
        except Exception:  # noqa: BLE001 - last-resort guard: frame loop must live
            log.exception("unexpected editor failure")
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
            if outcome is not Outcome.RUNNING:
                self._safe_end_flight(outcome)
        elif self.state == ARRIVED:
            self.arrive_timer -= dt
            if self.arrive_timer <= 0:
                self.session.stats = {
                    "time": self.flight.time,
                    "total_time": self.total_time,
                    "attempts": self.attempts,
                    "lives_left": self.lives,
                    "max_lives": self.level.lives,
                    "fx": self.editor.lines[0].strip() or "0",
                    "fy": self.editor.lines[1].strip() or "0",
                }
                from .win import WinScene
                self.manager.switch(WinScene(self.manager, self._snapshot()))

    # ------------------------------------------------------------------ draw
    def draw(self, surface):
        surface.fill(config.BG)
        self._draw_plot(surface)
        self._draw_panel(surface)

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

    def _draw_plot(self, surface):
        vp = self.viewport
        plot = pygame.Rect(vp.rect)
        try:
            surface.blit(self._plot_base_surface(), plot.topleft)
        except _RENDER_ERRORS as exc:
            log.warning("plot base blit contained: %r", exc)

        prev_clip = surface.get_clip()
        try:
            surface.set_clip(plot)
        except _RENDER_ERRORS as exc:
            log.warning("set_clip contained: %r", exc)

        try:
            hb = self.history_bounds
            if hb.w and hb.h:
                surface.blit(self.history, (plot.x + hb.x, plot.y + hb.y), hb)
            if self.launch_pos != self.level.start:
                # Faint marker at the original start ("back to start" target).
                pygame.draw.circle(surface, config.TEXT_FAINT, vp.to_screen(*self.level.start), px(3))
            launch = vp.to_screen(*self.launch_pos)
            sprites.draw_start_marker(surface, launch, vp.length(START_MARKER_RADIUS_M), self.t)

            flash = 0.0
            if self.state == ARRIVED:
                flash = max(0.0, self.arrive_timer / config.WIN_DELAY)
            sprites.draw_target(surface, vp.to_screen(*self.level.target_center),
                                vp.length(self.level.target_radius), self.t, flash)

            for obstacle in getattr(self.level, "obstacles", ()) or ():
                sprites.draw_obstacle(surface, vp.to_screen(*obstacle.center),
                                      vp.length(obstacle.radius), self.t)

            if self.flight is not None:
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

        draw_text(surface, "VECTOR DRIFT", (cx, px(LOGO_Y)), 26, config.TEXT, kind="bold", anchor="center")

        # Level row: "LV1" + level-select button
        draw_text(surface, f"LV{self.level.id}", (px(CX - 26), px(LEVEL_ROW_Y)), 22, config.TEXT,
                  kind="bold", anchor="center")
        self.level_button.draw(surface)

        # Current ship
        draw_text(surface, "Current ship", (cx, px(SHIP_LABEL_Y)), 15, config.TEXT_DIM, anchor="center")
        draw_panel_box(surface, SHIP_BOX, fill=config.BG)
        sprites.draw_ship(surface, SHIP_BOX.center, math.pi / 4 + 0.12 * math.sin(self.t * 1.3),
                          px(76), self.ship)
        self.prev_ship.draw(surface)
        self.next_ship.draw(surface)
        draw_text(surface, self.ship.name, (cx, px(SHIP_NAME_Y)), 18, config.TEXT, kind="bold", anchor="center")
        draw_text(surface, f"Mass: {self.ship.mass:g} kg", (cx, px(SHIP_MASS_Y)), 15, config.TEXT_DIM,
                  anchor="center")

        # Lives + clock
        icon_step = px(18)
        first = px(CX - 52) - icon_step * (self.level.lives - 1) // 2
        for i in range(self.level.lives):
            sprites.draw_ship_icon(surface, (first + i * icon_step, px(STATUS_Y)), px(18), self.ship,
                                   alive=i < self.lives)
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
