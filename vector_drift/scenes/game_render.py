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

from .game_layout import *


class GameRenderMixin:

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

    @staticmethod
    def _build_arrow_layer(job):
        """Draw the arrows for one zoom level (runs on the background worker too)."""
        field, max_force, i = job
        view = Viewport(zoom=level_zoom(i))
        layer, _ = render.make_field_layer(view, field, max_mag=max_force,
                                           spacing=render.arrow_spacing(view.scale))
        return layer

    def _keep_arrow_layer(self, i, layer):
        """Cache a level's layer; the ZOOM_LEVELS_KEPT most recently used stay."""
        if layer is not None and pygame.display.get_surface() is not None:
            layer = layer.convert_alpha()               # display format: faster to stretch
        self._mips[i] = layer
        while len(self._mips) > ZOOM_LEVELS_KEPT:
            gone = next(iter(self._mips))
            self._mips.pop(gone)
            if self._layer_builder is not None:
                version = self._field_version
                self._layer_builder.forget(lambda key: key == (version, gone))

    def _collect_arrow_layers(self):
        """Take the layers the background worker has finished for the current field."""
        if self._mips_key != self._field_version:
            self._mips, self._mips_key = {}, self._field_version
            if self._layer_builder is not None:
                version = self._field_version
                self._layer_builder.forget(lambda key: key[0] != version)
        if self._layer_builder is None:
            return
        for (version, i), layer in self._layer_builder.take_done().items():
            if version == self._field_version and layer is not None and i not in self._mips:
                self._keep_arrow_layer(i, layer)

    def _prefetch_arrows(self):
        """Have the background worker draw the arrow levels the camera may need next.

        Only on levels with Unbound. While setting up: the first zoom-out
        levels (down to 0.5); in flight: the levels around the camera's zoom,
        mostly the next two farther out.
        """
        if not self._has_unbound or self.field_layer is None or not self.valid:
            return
        if self._layer_builder is None:
            self._layer_builder = BackgroundBuilder(self._build_arrow_layer)
        self._collect_arrow_layers()
        current = zoom_level(self.camera.zoom)
        wanted = list(range(1, ZOOM_LEVELS_AT_LAUNCH))
        if self.state in (FLIGHT, ARRIVED):
            wanted += [current, current + 1, current + 2, current - 1]
        for i in dict.fromkeys(wanted):
            if i >= 1 and i not in self._mips:
                self._layer_builder.request((self._field_version, i),
                                            (self.field, self.max_force, i))

    def _arrow_layer(self, i, wait=True):
        """Arrows drawn at zoom level ``i`` (level_zoom), covering what that zoom shows.

        Level 0 is the map's own field layer. Every level keeps its length per
        newton relative to the arrow spacing, which doubles once arrows would
        crowd (render.arrow_spacing); arrows for forces above the map's
        largest are capped at the longest length. Normally drawn ahead by the
        background worker (_prefetch_arrows); if it is not ready, ``wait``
        draws it here, else None. None too if it cannot be drawn.
        """
        if self.field_layer is None:
            return None
        if i == 0:
            return self.field_layer
        self._collect_arrow_layers()
        if i in self._mips:
            self._mips[i] = self._mips.pop(i)           # most recently used last
            return self._mips[i]
        if not wait:
            return None
        try:
            layer = self._build_arrow_layer((self.field, self.max_force, i))
        except _PHYSICS_ERRORS + _RENDER_ERRORS as exc:
            log.warning("zoomed field layer contained: %r", exc)
            layer = None
        self._keep_arrow_layer(i, layer)
        return layer

    def _arrows_target(self, size):
        """The surface stretched arrows are drawn into, made once (display format)."""
        target = self._arrows_surface
        if target is None or target.get_size() != size:
            target = pygame.Surface(size, pygame.SRCALPHA)
            if pygame.display.get_surface() is not None:
                target = target.convert_alpha()
            self._arrows_surface = target
        return target

    def _zoomed_arrows(self):
        """The arrow layer at the camera's zoom: the next level out, stretched.

        Stretching is at most 2 ** (1/3) ~ 1.26. While the zoom keeps
        changing it is a fast (nearest-pixel) stretch, slightly jagged; the
        first frame the zoom holds still it is redone smoothly, then cached.
        If that level is not drawn yet, a ready level farther out stands in
        (stretched more) until it is; only with none ready is it drawn here.
        """
        zoom = self.camera.zoom
        dim = not self.valid and self.state == SETUP
        key = (self._field_version, dim, zoom)
        want = zoom_level(zoom)
        if key == self._arrows_key and self._arrows_smooth and self._arrows_level == want:
            return self._arrows
        smooth = key == self._arrows_key            # same zoom as last frame: settled
        i, layer = want, self._arrow_layer(want, wait=False)
        if layer is None:
            farther = [j for j in self._mips if j > want and self._mips[j] is not None]
            if farther:
                i = min(farther)
                layer = self._arrow_layer(i)
            else:
                layer = self._arrow_layer(want)
        arrows = None
        exact = True
        if layer is not None:
            base_zoom = level_zoom(i)
            w, h = layer.get_size()
            part = pygame.Rect(0, 0, round(w * base_zoom / zoom), round(h * base_zoom / zoom))
            part.center = (w // 2, h // 2)
            part = part.clip(layer.get_rect())
            if part.size != (w, h) and part.w and part.h:
                # Into one reused surface: making a new plot-sized one every
                # frame cost more than the stretch itself.
                arrows = self._arrows_target((w, h))
                stretch = pygame.transform.smoothscale if smooth else pygame.transform.scale
                stretch(layer.subsurface(part), (w, h), arrows)
                arrows.set_alpha(70 if dim else 255)
                exact = smooth
            elif part.size == (w, h):
                arrows = layer
                if dim:                                 # never change the shared layer
                    arrows = layer.copy()
                    arrows.set_alpha(70)
        self._arrows, self._arrows_key, self._arrows_smooth = arrows, key, exact
        self._arrows_level = i
        return arrows

    def _draw_zoomed_base(self, surface, plot):
        """Stars, grid, arrows and tick labels at the camera's zoom.

        The stars stay put (far backdrop); the grid and labels are drawn at
        the zoomed scale, the arrows come from _zoomed_arrows. Drawn straight
        onto the screen: the zoom changes nearly every frame, so a cached
        composite would only cost a copy; the grid goes on line by line
        (render.blit_grid) instead of through a plot-sized layer.
        """
        if self._space_screen is None:
            self._space_screen = (self._space.convert() if pygame.display.get_surface()
                                  else self._space)
        surface.blit(self._space_screen, plot.topleft)
        on_plot = surface.subsurface(plot)
        render.blit_grid(on_plot, self.camera)      # no plot-sized layer to fill and blend
        arrows = self._zoomed_arrows()
        if arrows is not None:
            surface.blit(arrows, plot.topleft)
        render.draw_plot_labels(on_plot, self.camera)

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
            if not legs:
                return                              # (no layer to clear for nothing)
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

    def _ship_length_px(self):
        """The ship's drawn length: to scale, but never under SHIP_MIN_SCALE of usual."""
        length = self.ship.length
        return max(self.camera.length(length), SHIP_MIN_SCALE * self.viewport.length(length))

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
            if pan is None:
                self._draw_pickup_fx(surface)

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
                sprites.draw_ship(surface, ship_pos, self.heading, self._ship_length_px(), self.ship)
                if self.flight is not None and self.flight.shield_remaining > 0.0:
                    sprites.draw_shield(surface, ship_pos, 0.6 * self._ship_length_px(), self.t)
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
                sprites.draw_target(surface, center, radius, self.t, flash)

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
            # A life pickup's newly lit icon jumps.
            size = round(px(18) * self.pickup_fx.pop_scale(pfx.LIFE, i))
            sprites.draw_ship_icon(surface, (first + i * icon_step, px(STATUS_Y)), size,
                                   self.flyable_ship, alive=i < self.lives)
        time_left = self._shown_time_left()
        time_color = config.WARNING if self.state == FLIGHT and time_left < 1.0 else config.TEXT
        if self.pickup_fx.popping(pfx.TIMER):
            time_color = pfx.EXTRATIME_COLOR        # extratime arrived: green flash
        draw_text(surface, fmt_clock(time_left), (px(CX + 62), px(STATUS_Y)),
                  round(24 * self.pickup_fx.pop_scale(pfx.TIMER)), time_color,
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
