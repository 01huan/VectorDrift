"""Obstacle (bumper) sprites."""

import math
import random

import pygame

from .. import config
from .common import (SS, OUTLINE, _cached, _paint_cached_prop)
from ..image_assets import ROCK_KEYS, load_image


def _render_bumper(radius):
    d = 2 * radius + 8
    D = d * SS
    c, r = D / 2, radius * SS
    surf = pygame.Surface((D, D), pygame.SRCALPHA)
    pygame.draw.circle(surf, (96, 104, 138), (c, c), r)
    cap = pygame.Surface((D, D), pygame.SRCALPHA)
    pygame.draw.circle(cap, (150, 162, 196), (c, c), r)
    pygame.draw.circle(cap, (0, 0, 0, 0), (c + 0.22 * r, c + 0.26 * r), r * 1.02)
    surf.blit(cap, (0, 0))
    for fx, fy, fr in ((-0.30, -0.20, 0.14), (0.25, 0.10, 0.11), (-0.05, 0.38, 0.09)):
        dot = pygame.Rect(0, 0, 2 * fr * r, 2 * fr * r)
        dot.center = (c + fx * r, c + fy * r)
        pygame.draw.ellipse(surf, (70, 78, 108), dot)
    pygame.draw.circle(surf, OUTLINE, (c, c), r, max(2, round(0.05 * r)))
    for i in range(12):
        a = i * math.pi / 6
        p0 = (c + (r + 2 * SS) * math.cos(a), c + (r + 2 * SS) * math.sin(a))
        p1 = (c + (r + 5 * SS) * math.cos(a), c + (r + 5 * SS) * math.sin(a))
        pygame.draw.line(surf, (255, 190, 90), p0, p1, max(2, round(1.2 * SS)))
    return pygame.transform.smoothscale(surf, (d, d))


OBSTACLE_IMAGES = {"bumper": ROCK_KEYS}


def _obstacle_look(seed, keys):
    rng = random.Random(repr(seed))
    return keys[rng.randrange(len(keys))], rng.uniform(0.0, 360.0)


def _obstacle_picture(kind, radius, seed):
    size = (radius * 2, radius * 2)
    keys = [key for key in OBSTACLE_IMAGES.get(kind, (f"obstacle.{kind}",))
            if load_image(key, size_px=size) is not None]
    if not keys:
        return None
    key, angle = _obstacle_look(seed, keys)
    img = load_image(key, size_px=size)
    return _cached(("obstacle-turned", img, angle),
                   lambda: pygame.transform.rotozoom(img, angle, 1.0))


def draw_obstacle(surface, center, radius, t, kind="bumper", seed=None):
    try:
        img = _obstacle_picture(kind, radius, center if seed is None else seed)
    except (pygame.error, TypeError, ValueError, OverflowError, MemoryError):
        img = None
    if img is not None:
        try:
            surface.blit(img, img.get_rect(center=center))
        except (pygame.error, TypeError, ValueError, OverflowError, MemoryError):
            return
        return

    painter = OBSTACLE_RENDERERS.get(kind, _paint_bumper)
    try:
        painter(surface, center, radius, t)
    except (pygame.error, TypeError, ValueError, OverflowError, MemoryError):
        return


def _paint_bumper(surface, center, radius, t):
    _paint_cached_prop(surface, center, radius, t, "bumper", _render_bumper)


OBSTACLE_RENDERERS = {"bumper": _paint_bumper}
