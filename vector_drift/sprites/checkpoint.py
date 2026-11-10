"""Checkpoint sprites."""

import math

import pygame

from .. import config
from .common import _cached
from .common import load_image
from ..render import soft_glow
from .ship import draw_ship, ship_icon_surface

CHECKPOINT_FILL = (246, 248, 252)
CHECKPOINT_SIDE = 1.6        # square side over the checkpoint radius (fits inside its disc)
CHECKPOINT_SHIP = 0.78       # ship length over the square side


def _paint_checkpoint_square(surface, center, radius, t, ship):
    side = max(4, round(CHECKPOINT_SIDE * radius))
    box = pygame.Rect(0, 0, side, side)
    box.center = (round(center[0]), round(center[1]))
    from .common import OUTLINE
    pygame.draw.rect(surface, CHECKPOINT_FILL, box, border_radius=max(1, side // 10))
    pygame.draw.rect(surface, OUTLINE, box, max(1, side // 28), border_radius=max(1, side // 10))
    if ship is not None:
        draw_ship(surface, box.center, math.pi / 4, CHECKPOINT_SHIP * side, ship)


CHECKPOINT_RENDERERS = {"square": _paint_checkpoint_square}


def draw_checkpoint(surface, center, radius, t, ship=None, kind="square"):
    try:
        cx, cy = float(center[0]), float(center[1])
        radius = float(radius)
    except (TypeError, ValueError, OverflowError):
        return
    if not (math.isfinite(cx) and math.isfinite(cy) and math.isfinite(radius)) or radius <= 1:
        return
    try:
        sw, sh = surface.get_size()
    except (pygame.error, TypeError, ValueError):
        return
    cull = config.MAX_PX_CULL
    if cx < -cull or cx > sw + cull or cy < -cull or cy > sh + cull:
        return
    size = round(2 * radius)
    img = load_image("target.checkpoint", size_px=(size, size))
    try:
        if img is not None:
            surface.blit(img, img.get_rect(center=(cx, cy)))
            return
        painter = CHECKPOINT_RENDERERS.get(kind, _paint_checkpoint_square)
        painter(surface, (cx, cy), radius, t, ship)
    except (pygame.error, TypeError, ValueError, OverflowError, MemoryError):
        return


CHECKPOINT_LIFE_GLOW = (170, 255, 210)   # minty "healing" glow behind the life ship
CHECKPOINT_LIFE_SIZE = 0.8      # life ship length over the checkpoint radius
CHECKPOINT_LIFE_LIFT = 0.12     # floats this far (x radius) above center, inside the portal ring


def draw_checkpoint_life(surface, center, radius, t, ship, fade=0.0):
    try:
        cx, cy = float(center[0]), float(center[1])
        radius, fade = float(radius), max(0.0, float(fade))
    except (TypeError, ValueError, OverflowError):
        return
    if (fade >= 1.0 or ship is None or radius <= 1
            or not (math.isfinite(cx) and math.isfinite(cy) and math.isfinite(radius))):
        return
    cull = config.MAX_PX_CULL
    try:
        sw, sh = surface.get_size()
    except (pygame.error, TypeError, ValueError):
        return
    if cx < -cull or cx > sw + cull or cy < -cull or cy > sh + cull:
        return
    r = round(radius)
    try:
        glow = _cached(("checkpoint-life-glow", r), lambda: soft_glow(
            0.6 * r, CHECKPOINT_LIFE_GLOW, max_alpha=255, extent=2.0, power=1.3).premul_alpha())
        icon = ship_icon_surface(ship, max(6, round(CHECKPOINT_LIFE_SIZE * r)))
        pulse = 0.5 + 0.5 * math.sin(t * 3.0)
        scale = 1.0 + 0.6 * fade
        bob = 0.05 * r * math.sin(t * 2.4)
        pos = (cx, cy - (CHECKPOINT_LIFE_LIFT + 0.5 * fade) * r + bob)

        light = glow.copy() if scale == 1.0 else pygame.transform.smoothscale(
            glow, (round(glow.get_width() * scale), round(glow.get_height() * scale)))
        k = round(255 * (0.55 + 0.45 * pulse) * (1.0 - fade))
        light.fill((k, k, k, 255), special_flags=pygame.BLEND_RGBA_MULT)
        surface.blit(light, light.get_rect(center=pos), special_flags=pygame.BLEND_RGB_ADD)

        if fade > 0.0:
            icon = pygame.transform.rotozoom(icon, 0, scale)
            icon.set_alpha(round(255 * (1.0 - fade)))
        surface.blit(icon, icon.get_rect(center=pos))
    except (pygame.error, TypeError, ValueError, OverflowError, MemoryError):
        return
