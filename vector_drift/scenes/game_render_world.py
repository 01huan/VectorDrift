"""World rendering for GameScene: plot base, zoomed view, arrows, trails."""
import logging
import math

import pygame

from .. import config, render, sprites
from ..config import px
from ..background import BackgroundBuilder
from ..coords import Viewport
from .game_layout import (
    ARRIVED, CHECKPOINT_LIFE_POP_S, FLIGHT, HISTORY_ALPHA, PANNING, SETUP,
    SHIP_MIN_SCALE, UNBOUND_EDGE, ZOOM_LEVELS_AT_LAUNCH, ZOOM_LEVELS_KEPT,
    level_zoom, pan_offsets, zoom_level,
)

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


class GameWorldRenderMixin:

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
                if self.flight is not None and getattr(self.flight, "phase_remaining", 0.0) > 0.0:
                    sprites.draw_phase(surface, ship_pos, 0.65 * self._ship_length_px(), self.t)
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
