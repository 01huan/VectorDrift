"""Layout constants and small presentation helpers for the game scene.

These values are pure data / pure functions extracted from ``scenes/game.py`` so
the scene class stays focused on behaviour while the geometry and presentation
formatting remain easy to tweak and test independently.
"""

from __future__ import annotations

import math

import pygame

from .. import config
from ..config import px
from ..physics import Outcome


# Scene stage names.
SETUP, FLIGHT, ARRIVED = "setup", "flight", "arrived"
# Multi-section levels: the camera pans from a reached checkpoint to the next
# section. No input is taken until the next section's SETUP.
PANNING = "panning"

OUTCOME_TEXT = {
    Outcome.TIMEOUT: "TIME UP",
    Outcome.OUT_OF_BOUNDS: "OUT OF BOUNDS",
    Outcome.DIVERGED: "DIVERGED",
    Outcome.ABORTED: "ABORTED",
}
# After these outcomes the next launch starts (at rest) where the ship stopped;
# every other miss (abort, out of bounds, diverged) goes back to the level start.
# So does a time-up off the map (an unbound ship): see GameScene._end_flight.
RESUME_OUTCOMES = (Outcome.TIMEOUT,)
# Pickups that come back at the start of every life (the rest stay taken).
RESPAWN_EVERY_LIFE = ("unbound",)

START_MARKER_RADIUS_M = 0.45
CHECKPOINT_LIFE_POP_S = 0.45  # the taken checkpoint life grows and fades out this long
HISTORY_ALPHA = 110          # earlier legs of the current run
CAMERA_EASE_S = 0.1          # zoom time constant: about 0.3 s to settle
CAMERA_MARGIN_M = 1.0        # room kept between an off-map ship and the plot edge
UNBOUND_EDGE = (190, 130, 255)   # dashed map edge while Unbound is active
# Field arrows for the zoomed-out view are drawn at zoom levels 2 ** (-i / 3)
# (i = 0, 1, 2, ...: three per halving, no end); in between, the next level
# out is stretched, so by at most 2 ** (1/3) ~ 1.26. A background worker
# draws them ahead: the first ones while the formulas are edited, the next
# ones out during the flight. Only the latest few are kept.
ZOOM_LEVELS_PER_HALVING = 3
ZOOM_LEVELS_AT_LAUNCH = 4        # zoom 1 down to 0.5: drawn ahead while editing
ZOOM_LEVELS_KEPT = 6
# Zoomed far out the ship is still drawn at least this share of its usual size.
SHIP_MIN_SCALE = 0.5


def zoom_level(zoom):
    """Index i of the arrow zoom level 2 ** (-i / 3) just below ``zoom`` (0 at zoom 1)."""
    return max(0, math.ceil(-ZOOM_LEVELS_PER_HALVING * math.log2(zoom) - 1e-9))


def level_zoom(i):
    return 2.0 ** (-i / ZOOM_LEVELS_PER_HALVING)


RUN_GREEN = (137, 209, 133)


def R(x, y, w, h):
    """Rect from logical pixels."""
    return pygame.Rect(px(x), px(y), px(w), px(h))


# Left panel layout in logical pixels (scaled with px / R)
PAD = 20
CX = 160                     # panel center line
CONTENT_W = 320 - 2 * PAD
LOGO_Y = 36
LOGO_W = 220                 # logo width; its height follows the picture (~69)
LEVEL_ROW_Y = 82
SHIP_LABEL_Y = 124
SHIP_BOX = R(CX - 55, 140, 110, 110)
SHIP_NAME_Y = 270
SHIP_MASS_Y = 292
STATUS_Y = 330
EDITOR_Y = 354
TELEMETRY_ROW_H = 20
LEGEND_LABEL_Y = 636
LEGEND_Y = 662


def ease_in_out(p):
    """Smoothstep 0 -> 1 for the section pan (slow start, slow stop)."""
    p = max(0.0, min(1.0, p))
    return p * p * (3.0 - 2.0 * p)


def pan_offsets(shift, progress):
    """(old, new) section offsets in m at eased pan ``progress`` 0 -> 1.

    Sections are drawn in their own coordinates plus an offset. The section
    being left moves from (0, 0) to -shift; the next one comes in from
    +shift and settles at (0, 0), so the shared checkpoint stays aligned.
    """
    sx, sy = shift
    return (-sx * progress, -sy * progress), (sx * (1.0 - progress), sy * (1.0 - progress))


def fmt_pair(x, y, unit):
    try:
        fx, fy = float(x), float(y)
    except (TypeError, ValueError, OverflowError):
        return f"— {unit}"
    if not (math.isfinite(fx) and math.isfinite(fy)):
        return f"— {unit}"
    return f"({fx:.2f}, {fy:.2f}) {unit}"


def fmt_clock(seconds):
    """Seconds as SS:CC (seconds and hundredths), e.g. 7.34 -> '07:34'."""
    cs = max(0, int(round(seconds * 100)))
    return f"{cs // 100:02d}:{cs % 100:02d}"


__all__ = [
    "SETUP", "FLIGHT", "ARRIVED", "PANNING",
    "OUTCOME_TEXT", "RESUME_OUTCOMES", "RESPAWN_EVERY_LIFE",
    "START_MARKER_RADIUS_M", "CHECKPOINT_LIFE_POP_S", "HISTORY_ALPHA",
    "CAMERA_EASE_S", "CAMERA_MARGIN_M", "UNBOUND_EDGE",
    "ZOOM_LEVELS_PER_HALVING", "ZOOM_LEVELS_AT_LAUNCH", "ZOOM_LEVELS_KEPT",
    "SHIP_MIN_SCALE", "RUN_GREEN", "PAD", "CX", "CONTENT_W", "LOGO_Y", "LOGO_W",
    "LEVEL_ROW_Y", "SHIP_LABEL_Y", "SHIP_BOX", "SHIP_NAME_Y", "SHIP_MASS_Y",
    "STATUS_Y", "EDITOR_Y", "TELEMETRY_ROW_H", "LEGEND_LABEL_Y", "LEGEND_Y",
    "zoom_level", "level_zoom", "R", "ease_in_out", "pan_offsets", "fmt_pair", "fmt_clock",
]
