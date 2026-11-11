"""Section drawing for GameScene: start/target, props, panning, plot labels."""
import sys as _sys

import pygame

from .. import config, sprites
from ..config import px
from .game_layout import ARRIVED, FLIGHT, START_MARKER_RADIUS_M


def _gm():
    return _sys.modules["vector_drift.scenes.game"]


def draw_text(*a, **k):
    return _gm().draw_text(*a, **k)


class GameSectionRenderMixin:

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
