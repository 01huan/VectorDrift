"""Shared preview machinery for a force function.

Both the Function Lab and the community Function detail view draw the same
thing: the vector field the two formulas produce, and the path a probe
particle would take through it.  The heavy lifting (parsing, the arrow
layer, the semi-implicit Euler integration) lives here so the two screens
stay in step.

The module imports pygame (the field layer is a surface), but never the
scenes; the callers stay in charge of the layout.
"""

from __future__ import annotations

import math
from typing import Optional, Sequence, Tuple

import pygame

from . import config, render
from .config import px
from .coords import Viewport
from .expr_parser import diagnose_expression
from .physics import ForceField

# The probe: a 1 kg particle released on the map, integrated like the ship.
PROBE_MASS = 1.0
PROBE_STEPS = 900                   # 7.5 s at the game's 1/120 s step
PROBE_LIMIT_M = 30.0               # stop when it is this far out
DEFAULT_PROBE_START = (-6.0, 0.0)  # where the ship usually starts


def parse_formulas(fx_text: str, fy_text: str):
    """Diagnose both formulas.

    Returns ``(field, errors)`` where ``field`` is a :class:`ForceField`
    when both formulas are valid and ``errors`` is a list of
    ``(message, position)`` entries (``None`` entries for valid lines).
    """
    fx, fx_err, fx_pos = diagnose_expression(fx_text)
    fy, fy_err, fy_pos = diagnose_expression(fy_text)
    errors = [
        (fx_err, fx_pos) if fx_err else None,
        (fy_err, fy_pos) if fy_err else None,
    ]
    if fx is None or fy is None:
        return None, errors
    try:
        field = ForceField.from_exprs(fx, fy)
    except (ArithmeticError, ValueError, TypeError, OverflowError,
            RecursionError, MemoryError):
        return None, [("Cannot be used to build the field", 0), None]
    return field, errors


def build_field_layer(viewport: Viewport, field, spacing: float = 1.0) -> Optional[tuple]:
    """The arrow layer for ``field`` (and the largest |F| shown).

    Returns ``None`` when the field cannot be drawn (a pole in the grid),
    mirroring the Function Lab's behaviour.
    """
    if field is None:
        return None
    try:
        layer, max_force = render.make_field_layer(viewport, field, spacing=spacing)
    except (ArithmeticError, ValueError, TypeError, OverflowError,
            RecursionError, MemoryError, pygame.error):
        return None
    return layer, max_force


def trace_probe(field, start: Tuple[float, float] = DEFAULT_PROBE_START,
                steps: int = PROBE_STEPS, limit_m: float = PROBE_LIMIT_M,
                mass: float = PROBE_MASS) -> list:
    """Trace a probe particle through the field (semi-implicit Euler)."""
    if field is None:
        return []
    x, y = start
    vx = vy = 0.0
    dt = config.DT
    points = []
    for _ in range(steps):
        try:
            fx, fy = field.at(x, y)
        except (ArithmeticError, ValueError, TypeError, OverflowError,
                RecursionError, MemoryError):
            break
        if not (math.isfinite(fx) and math.isfinite(fy)):
            break
        vx += (fx / mass) * dt
        vy += (fy / mass) * dt
        x += vx * dt
        y += vy * dt
        if not (math.isfinite(x) and math.isfinite(y)):
            break
        points.append((x, y))
        if abs(x) > limit_m or abs(y) > limit_m:
            break
    return points


def make_preview(fx_text: str, fy_text: str, rect, *,
                 probe_start: Tuple[float, float] = DEFAULT_PROBE_START):
    """Everything a preview needs, in one call.

    Returns ``(viewport, field, layer, max_force, probe)``; ``layer`` and
    ``probe`` are empty when the field cannot be shown.  ``rect`` is a real
    pixel rect on the screen; the viewport is fitted to it.
    """
    field, _errors = parse_formulas(fx_text, fy_text)
    scale = min(rect.w / 20.0, rect.h / 15.0)
    viewport = Viewport(rect=pygame.Rect(rect), scale=scale)
    # A small thumbnail needs coarser arrows; the lab-size preview keeps the
    # map's usual spacing.
    spacing = 2.5 if min(rect.w, rect.h) < 80 * config.UI_SCALE else 1.0
    built = (build_field_layer(viewport, field, spacing=spacing) if field is not None else None)
    if built is not None:
        layer, max_force = built
    else:
        layer, max_force = None, 0.0
    probe = trace_probe(field, probe_start) if layer is not None else []
    background = render.make_plot_background(viewport)
    return {
        "viewport": viewport,
        "field": field,
        "background": background,
        "layer": layer,
        "max_force": max_force,
        "probe": probe,
    }


def draw_preview(surface, preview, rect) -> None:
    """Draw a built preview into ``rect`` (called from draw())."""
    viewport = preview["viewport"]
    surface.blit(preview["background"], (viewport.left, viewport.top))
    if preview["layer"] is not None:
        surface.blit(preview["layer"], (viewport.left, viewport.top))
    probe = preview["probe"]
    if probe:
        points = [viewport.to_screen(x, y) for x, y in probe]
        previous_clip = surface.get_clip()
        surface.set_clip(pygame.Rect(rect))
        try:
            if len(points) > 1:
                pygame.draw.lines(surface, config.TRAIL, False, points, max(1, px(2)))
            pygame.draw.circle(surface, config.SUCCESS, points[0], max(2, px(4)))
            pygame.draw.circle(surface, config.ACCENT, points[-1], max(2, px(4)))
        finally:
            surface.set_clip(previous_clip)
    pygame.draw.rect(surface, config.PANEL_EDGE, pygame.Rect(rect),
                     max(1, px(1)), border_radius=px(4))
