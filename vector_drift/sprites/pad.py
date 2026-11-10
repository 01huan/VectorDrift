"""Launch pad / start marker sprites."""

import math

import pygame

from .. import config
from .common import _cached
from .common import load_image


def _render_pad(radius):
    size = 2 * radius + round(8 * config.UI_SCALE)
    from .common import SS
    big = pygame.Surface((size * SS, size * SS), pygame.SRCALPHA)
    c, r = size * SS / 2, radius * SS
    thick = 1.4 * config.UI_SCALE * SS
    dashes = 12
    for i in range(dashes):
        a0 = i * 2 * math.pi / dashes
        for s in range(13):
            a = a0 + (math.pi / dashes) * s / 12
            pygame.draw.circle(big, (180, 196, 232, 220), (c + r * math.cos(a), c + r * math.sin(a)), thick)
    pygame.draw.circle(big, (180, 196, 232, 200), (c, c), 2.2 * config.UI_SCALE * SS)
    return pygame.transform.smoothscale(big, (size, size))


def draw_start_marker(surface, center, radius, t):
    img = load_image("ui.start_marker", size_px=(radius * 2, radius * 2))
    if img is not None:
        try:
            rotated = pygame.transform.rotozoom(img, -math.degrees(t * 0.4), 1.0)
            surface.blit(rotated, rotated.get_rect(center=center))
        except (pygame.error, TypeError, ValueError, OverflowError, MemoryError):
            return
        return

    pad = _cached(("pad", round(radius)), lambda: _render_pad(round(radius)))
    try:
        rotated = pygame.transform.rotozoom(pad, -math.degrees(t * 0.4), 1.0)
        surface.blit(rotated, rotated.get_rect(center=center))
    except (pygame.error, TypeError, ValueError, OverflowError, MemoryError):
        return
