"""Shared helpers and constants for the sprites package."""

import logging
import math

import pygame

from .. import config
from .. import image_assets
from .. import render

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


_ROTATED_CACHE: dict = {}
_ROTATED_CACHE_MAX = 128


def _rotated(img, angle, tag):
    """``pygame.transform.rotozoom(img, angle, 1.0)`` memoized by (tag, rounded angle).

    For per-frame rotating sprites (ship, hole, start marker): a bounded cache
    avoids re-rotating the same image + angle every frame.  ``tag`` must
    separate sprites that rotate differently (e.g. different sizes).
    """
    key = (tag, round(angle, 2))
    rot = _ROTATED_CACHE.get(key)
    if rot is None:
        if len(_ROTATED_CACHE) >= _ROTATED_CACHE_MAX:
            _ROTATED_CACHE.clear()
        rot = pygame.transform.rotozoom(img, angle, 1.0)
        _ROTATED_CACHE[key] = rot
    return rot


def _poly(surface, pts, fill, outline_w):
    """Filled polygon with a rounded-corner outline."""
    pygame.draw.polygon(surface, fill, pts)
    if outline_w > 0:
        pygame.draw.polygon(surface, OUTLINE, pts, outline_w)
        for p in pts:
            pygame.draw.circle(surface, OUTLINE, p, outline_w / 2)


def _shade(color, f):
    return tuple(max(0, min(255, round(c * f))) for c in color)


def blink_value(t, freq, base=0.5, span=0.5):
    """A gentle 0..1 pulse: ``base + span * sin(t * freq)``."""
    return base + span * math.sin(t * freq)


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
        pulse = blink_value(t, pulse_freq)
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
