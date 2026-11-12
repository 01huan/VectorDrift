"""Shield and phase sprites."""

import math

import pygame

from .. import config
from .common import SS, _cached

SHIELD = (120, 220, 255)
PHASE = (150, 240, 220)


def _render_shield(radius):
    d = 2 * radius + 4
    D = d * SS
    c, r = D / 2, radius * SS
    surf = pygame.Surface((D, D), pygame.SRCALPHA)
    pygame.draw.circle(surf, (*SHIELD, 55), (c, c), r)                                # bubble
    pygame.draw.circle(surf, (*SHIELD, 210), (c, c), r, max(2, round(0.09 * r)))     # rim
    pygame.draw.circle(surf, (255, 255, 255, 140), (c - 0.45 * r, c - 0.45 * r), 0.12 * r)  # glint
    return pygame.transform.smoothscale(surf, (d, d))


def draw_shield(surface, center, radius, t):
    radius = max(4, round(radius))
    img = _cached(("shield", radius), lambda: _render_shield(radius)).copy()
    img.set_alpha(round(170 + 85 * (0.5 + 0.5 * math.sin(t * 5.0))))
    try:
        surface.blit(img, img.get_rect(center=center))
    except (pygame.error, TypeError, ValueError, OverflowError):
        pass


def _render_phase(radius):
    d = 2 * radius + 4
    surf = pygame.Surface((d, d), pygame.SRCALPHA)
    c = d / 2
    width = max(2, round(radius * 0.09))
    dashes = 10
    step = 2 * math.pi / dashes
    for i in range(dashes):
        a0 = i * step
        a1 = a0 + step * 0.62
        pts = [(c + radius * math.cos(a), c + radius * math.sin(a))
               for a in (a0, (a0 + a1) / 2, a1)]
        pygame.draw.lines(surf, (*PHASE, 220), False, pts, width)
    return surf


def draw_phase(surface, center, radius, t):
    try:
        cx, cy = float(center[0]), float(center[1])
        radius = float(radius)
    except (TypeError, ValueError, OverflowError):
        return
    if not (math.isfinite(cx) and math.isfinite(cy) and math.isfinite(radius)):
        return
    if radius <= 2:
        return
    try:
        sw, sh = surface.get_size()
    except (pygame.error, TypeError, ValueError):
        return
    cull = config.MAX_PX_CULL
    if cx < -cull or cx > sw + cull or cy < -cull or cy > sh + cull:
        return
    radius = max(6, round(radius))
    img = _cached(("phase", radius), lambda: _render_phase(radius)).copy()
    img.set_alpha(round(150 + 80 * (0.5 + 0.5 * math.sin(t * 6.0))))
    try:
        rotated = pygame.transform.rotozoom(img, (t * 90.0) % 360.0, 1.0)
        surface.blit(rotated, rotated.get_rect(center=(round(cx), round(cy))))
    except (pygame.error, TypeError, ValueError, OverflowError, MemoryError):
        pass
