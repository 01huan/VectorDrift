"""Image asset management for Vector Drift.

Centralised PNG loading under ``assets/images/``.  Every slot has an
:class:`AssetSpec` describing the logical display size (in base logical pixels,
the same coordinate system used by ``config.px``), anchor and scale mode.

Images are loaded *lazily*, scaled once with ``config.UI_SCALE``, and cached.
Missing files or load failures silently return ``None`` so callers can fall
back to the existing pygame code-drawn art.  Nothing is loaded at import time,
so headless test environments and runs without any PNG assets keep working.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import pygame

from . import config
from .config import px

log = logging.getLogger(__name__)

IMAGES_DIR = config.ASSETS_DIR / "images"


# ---------------------------------------------------------------------------
# Asset specification
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AssetSpec:
    """Describes one image slot.

    ``display_w`` / ``display_h`` are in *logical* pixels.  The real pixel size
    is computed exactly once at load time via :func:`config.px`.
    """

    key: str
    path: Path               # relative to assets/images
    display_w: float | None = None   # logical px; None = keep source size
    display_h: float | None = None
    anchor: str = "center"
    scale_mode: str = "fit"          # "fit" | "stretch" | "tile"


# ---------------------------------------------------------------------------
# Slot registry (key -> AssetSpec)
# ---------------------------------------------------------------------------

_SPECS: dict[str, AssetSpec] = {}


def register(spec: AssetSpec) -> None:
    _SPECS[spec.key] = spec


def get_spec(key: str) -> AssetSpec | None:
    return _SPECS.get(key)


# Ships (key = f"ship.{ship_id}")
for _n in range(1, 7):
    register(AssetSpec(f"ship.ship{_n:02d}", Path(f"ships/ship{_n:02d}.png"), display_w=76, display_h=76))
# Targets / destination
register(AssetSpec("target.planet", Path("targets/planet.png"), display_w=120, display_h=120))

# Obstacles: every bumper shows one of these rock pictures, picked at random
# per bumper (sprites.draw_obstacle). To add a look, add obstacles/rock03.png
# and widen the range.
ROCK_KEYS = tuple(f"obstacle.rock{n:02d}" for n in range(1, 3))
for _key in ROCK_KEYS:
    register(AssetSpec(_key, Path(f"obstacles/{_key.split('.', 1)[1]}.png"), display_w=64, display_h=64))

# Pickups (key = f"pickup.{kind}")
register(AssetSpec("pickup.bomb", Path("pickups/bomb.png"), display_w=40, display_h=40))
register(AssetSpec("pickup.add_time", Path("pickups/add_time.png"), display_w=40, display_h=40))
register(AssetSpec("pickup.penetrate", Path("pickups/penetrate.png"), display_w=40, display_h=40))
# UI
register(AssetSpec("ui.start_marker", Path("ui/start_marker.png"), display_w=36, display_h=36))

# Background (tiled full-screen backdrop)
register(AssetSpec("background.space", Path("background/space.png"), scale_mode="tile"))


# ---------------------------------------------------------------------------
# Lazy loading + cache
# ---------------------------------------------------------------------------

# key -> the PNG as read from disk; None = missing or unreadable (never retried).
_sources: dict[str, pygame.Surface | None] = {}
# (key, width, height) -> that image scaled once to exactly that real-pixel size.
_cache: dict[tuple[str, int, int], pygame.Surface] = {}


def clear_cache() -> None:
    """Forget every loaded and scaled image (e.g. between tests)."""
    _sources.clear()
    _cache.clear()


def _load_source(key: str) -> pygame.Surface | None:
    """The image for ``key`` as read from disk, or ``None``; read at most once."""
    if key in _sources:
        return _sources[key]
    surf = None
    spec = get_spec(key)
    if spec is None:
        log.warning("no image spec for key %r", key)
    else:
        path = IMAGES_DIR / spec.path
        if not path.exists():
            log.debug("image missing: %s", path)
        else:
            try:
                surf = pygame.image.load(str(path)).convert_alpha()
            except (pygame.error, FileNotFoundError, OSError, ValueError) as exc:
                log.warning("failed to load image %s: %r", path, exc)
    _sources[key] = surf
    return surf


def load_image(key: str, size_px: tuple[int, int] | None = None) -> pygame.Surface | None:
    """Load and cache an image for ``key`` at the requested size.

    ``size_px`` is the desired *real* pixel size (already scaled by UI_SCALE).
    If omitted, the spec's logical display size is converted via
    :func:`config.px`.  Each distinct final size is scaled once and cached
    under ``(key, width, height)``.  Returns ``None`` when the file is missing
    or cannot be loaded, so callers can fall back to code-drawn art.
    """
    source = _load_source(key)
    if source is None:
        return None

    # Determine target real-pixel size.
    spec = get_spec(key)
    if size_px is not None:
        target_w, target_h = size_px
    elif spec.display_w is not None and spec.display_h is not None:
        target_w = px(spec.display_w)
        target_h = px(spec.display_h)
    else:
        target_w, target_h = source.get_size()
    try:
        size = (max(1, int(target_w)), max(1, int(target_h)))
    except (TypeError, ValueError, OverflowError) as exc:
        log.warning("bad size %r for image %r: %r", (target_w, target_h), key, exc)
        return source

    cache_key = (key, *size)
    if cache_key in _cache:
        return _cache[cache_key]

    # Scale once per size, cache the result.  Never re-scale per frame.
    surf = source
    try:
        if size != source.get_size():
            surf = pygame.transform.smoothscale(source, size)
    except (pygame.error, ValueError, OverflowError) as exc:
        log.warning("failed to scale image %r to %s: %r", key, size, exc)

    _cache[cache_key] = surf
    return surf
