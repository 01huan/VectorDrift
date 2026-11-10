"""Replay record helpers: frame access, teleport detection, trail strokes."""

import math

from .. import config

START_MARKER_RADIUS_M = 0.45
# Records saved before frames carried "warp" still break the trail where the
# ship jumps much farther in one frame than its speed allows (a teleport).
JUMP_SLACK_M = 0.5


def _get(frame, key):
    if isinstance(frame, dict):
        return frame.get(key, 0.0)
    return getattr(frame, key, 0.0)


def _is_jump(a, b):
    """Did the ship get from frame a to frame b without flying there?"""
    try:
        dist = math.hypot(float(_get(b, "x")) - float(_get(a, "x")), float(_get(b, "y")) - float(_get(a, "y")))
        speed = max(math.hypot(float(_get(a, "vx")), float(_get(a, "vy"))),
                    math.hypot(float(_get(b, "vx")), float(_get(b, "vy"))))
        dt = max(float(_get(b, "t")) - float(_get(a, "t")), 1.0 / config.FPS)
    except (TypeError, ValueError, OverflowError):
        return False
    return dist > JUMP_SLACK_M + 3.0 * speed * dt


def trail_strokes(frames):
    """Split frames into trail strokes: a teleport (warp) starts a new one."""
    strokes = []
    for frame in frames:
        warp = frame.get("warp") is True if isinstance(frame, dict) else getattr(frame, "warp", False)
        if not strokes or warp or _is_jump(strokes[-1][-1], frame):
            strokes.append([frame])
        else:
            strokes[-1].append(frame)
    return strokes
