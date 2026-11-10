"""Shared helpers and constants for the sprites package."""

import logging
import math
import random

import pygame

from .. import config
from .. import image_assets
from .. import render
from ..render import soft_glow

log = logging.getLogger(__name__)

SS = 4                      # supersampling factor for cached art
OUTLINE = config.OUTLINE
GLASS = (110, 210, 255)
NOZZLE = (88, 96, 124)

_cache = {}


def _cached(key, build):
    if key not in _cache:
        _cache[key] = build()
    return _cache[key]


def _poly(surface, pts, fill, outline_w):
    """Filled polygon with a rounded-corner outline."""
    pygame.draw.polygon(surface, fill, pts)
    if outline_w > 0:
        pygame.draw.polygon(surface, OUTLINE, pts, outline_w)
        for p in pts:
            pygame.draw.circle(surface, OUTLINE, p, outline_w / 2)


def _shade(color, f):
    return tuple(max(0, min(255, round(c * f))) for c in color)


def _paint_cached_prop(surface, center, radius, t, cache_key, render_fn,
                       alpha_base=215, alpha_range=40, pulse_freq=3.0):
    """Shared boilerplate for cached prop painters (bumper, shockwave, ...).

    Parses/validates inputs, culls off-screen, fetches a cached rendered
    surface, applies a gentle alpha pulse, and blits. Never raises.
    """
    try:
        cx, cy = float(center[0]), float(center[1])
        radius = float(radius)
    except (TypeError, ValueError, OverflowError):
        return
    if not (math.isfinite(cx) and math.isfinite(cy) and math.isfinite(radius)):
        return
    if radius <= 1:
        return
    try:
        sw, sh = surface.get_size()
    except (pygame.error, TypeError, ValueError):
        return
    cull = config.MAX_PX_CULL
    if cx < -cull or cx > sw + cull or cy < -cull or cy > sh + cull:
        return
    radius = round(radius)
    try:
        # Copy before set_alpha so the shared cache surface isn't mutated
        # (all same-radius props would otherwise be forced to one alpha).
        img = _cached((cache_key, radius), lambda: render_fn(radius))
        pulse = 0.5 + 0.5 * math.sin(t * pulse_freq)
        img = img.copy()
        img.set_alpha(round(alpha_base + alpha_range * pulse))
        surface.blit(img, img.get_rect(center=(cx, cy)))
    except (pygame.error, TypeError, ValueError, OverflowError, MemoryError):
        return


def load_image(*a, **k):
    import vector_drift.sprites as _pkg
    fn = getattr(_pkg, "load_image", None)
    if callable(fn) and fn is not load_image:
        return fn(*a, **k)
    return image_assets.load_image(*a, **k)


def source_size(*a, **k):
    import vector_drift.sprites as _pkg
    fn = getattr(_pkg, "source_size", None)
    if callable(fn) and fn is not source_size:
        return fn(*a, **k)
    return image_assets.source_size(*a, **k)


def draw_smooth_arrow(*a, **k):
    import vector_drift.sprites as _pkg
    fn = getattr(_pkg, "draw_smooth_arrow", None)
    if callable(fn) and fn is not draw_smooth_arrow:
        return fn(*a, **k)
    return render.draw_smooth_arrow(*a, **k)
