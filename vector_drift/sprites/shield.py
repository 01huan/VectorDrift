"""Shield sprites."""

import math

import pygame

from .common import SS, _cached

SHIELD = (120, 220, 255)


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
