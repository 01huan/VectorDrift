"""Force field values, outcomes, and collision geometry.

These are the side-effect-free building blocks used by the flight
simulation in :mod:`vector_drift.physics`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

from . import config

# Huge-but-finite forces (e.g. tan(pi/2) ~= 1.6e16) pass every isfinite() check
# yet tunnel through the target in one step (REACHED) and then crash pygame
# with 1e12-scale screen coordinates. Clamp here so they become DIVERGED.
MAX_FORCE = config.MAX_FORCE


class Outcome(Enum):
    RUNNING = "running"
    REACHED = "reached"
    TIMEOUT = "timeout"
    OUT_OF_BOUNDS = "out_of_bounds"
    DIVERGED = "diverged"
    ABORTED = "aborted"


@dataclass(frozen=True)
class ForceField:
    """Force field in newtons.

    Legacy linear form:
        Fx = a*x + b*y + c
        Fy = d*x + e*y + f

    General form:
        Fx = fx_expr(x, y)
        Fy = fy_expr(x, y)

    An expression may provide evaluate(x, y), or be a callable.
    """

    a: float = 0.0
    b: float = 0.0
    c: float = 0.0
    d: float = 0.0
    e: float = 0.0
    f: float = 0.0

    fx_expr: object = None
    fy_expr: object = None

    @classmethod
    def from_exprs(cls, fx, fy):
        """Build a force field from parsed or callable expressions."""
        return cls(fx_expr=fx, fy_expr=fy)

    @staticmethod
    def _evaluate(expr, x, y):
        if expr is None:
            raise ValueError("Missing force expression")
        try:
            if hasattr(expr, "evaluate"):
                value = expr.evaluate(x, y)
            elif callable(expr):
                value = expr(x, y)
            else:
                raise TypeError(
                    "Force expression must provide evaluate(x, y) "
                    "or be callable"
                )
            value = float(value)
            if not math.isfinite(value):
                raise ArithmeticError("Force is not finite")
            if abs(value) > MAX_FORCE:
                raise ArithmeticError(f"Force magnitude {value:.3g} exceeds limit")
        except (ValueError, TypeError, OverflowError, RecursionError, MemoryError) as exc:
            raise ArithmeticError(f"Invalid force expression result: {exc}")
        return value

    def at(self, x, y):
        """Return (Fx, Fy) at position (x, y)."""
        if self.fx_expr is None and self.fy_expr is None:
            fx = self.a * x + self.b * y + self.c
            fy = self.d * x + self.e * y + self.f
        else:
            fx = self._evaluate(self.fx_expr, x, y)
            fy = self._evaluate(self.fy_expr, x, y)

        if not (math.isfinite(fx) and math.isfinite(fy)):
            raise ArithmeticError("Force field produced a non-finite value")
        if abs(fx) > MAX_FORCE or abs(fy) > MAX_FORCE:
            raise ArithmeticError("Force field produced an excessive value")
        return float(fx), float(fy)

    def invalid_components(self, x, y):
        """Indices (0 = Fx, 1 = Fy) of components with no valid force at (x, y).

        Same rules as at(), so an empty tuple means a flight starting at
        (x, y) gets past its first force evaluation.
        """
        if self.fx_expr is None and self.fy_expr is None:
            values = (self.a * x + self.b * y + self.c,
                      self.d * x + self.e * y + self.f)
            return tuple(i for i, v in enumerate(values)
                         if not math.isfinite(v) or abs(v) > MAX_FORCE)
        bad = []
        for i, expr in enumerate((self.fx_expr, self.fy_expr)):
            try:
                self._evaluate(expr, x, y)
            except ArithmeticError:
                bad.append(i)
        return tuple(bad)


def segment_hits_circle(p0, p1, center, radius):
    """True if segment p0->p1 comes within radius of center."""
    return segment_circle_first_hit(p0, p1, center, radius) is not None


def segment_circle_first_hit(p0, p1, center, radius):
    """Earliest t in [0, 1] where segment p0->p1 touches the circle, else None.

    Solving |p0 + t*(p1-p0) - center|^2 = radius^2 keeps fast ships from
    tunneling through small bumpers (same reason the target uses a segment
    test instead of a point test).
    """
    x0, y0 = p0
    dx, dy = p1[0] - x0, p1[1] - y0
    cx, cy = center[0] - x0, center[1] - y0

    seg_len2 = dx * dx + dy * dy
    dist2 = cx * cx + cy * cy
    if seg_len2 <= 0.0:
        return 0.0 if dist2 <= radius * radius else None

    # Start inside (or exactly on) the disc: contact is right now.
    if dist2 <= radius * radius:
        return 0.0

    a = seg_len2
    b = -(cx * dx + cy * dy)  # = f.d with f = p0 - center (half of b term)
    c = dist2 - radius * radius
    disc = b * b - a * c
    if disc < 0.0:
        return None
    root = math.sqrt(disc)
    for t in ((-b - root) / a, (-b + root) / a):
        if 0.0 <= t <= 1.0:
            return t
    return None


def reflect_velocity(vx, vy, nx, ny, restitution=1.0):
    """Reflect velocity (vx, vy) about unit normal (nx, ny)."""
    try:
        e = float(restitution)
    except (TypeError, ValueError, OverflowError):
        e = 1.0
    if not math.isfinite(e):
        e = 1.0
    vn = vx * nx + vy * ny
    return vx - (1.0 + e) * vn * nx, vy - (1.0 + e) * vn * ny


__all__ = [
    "MAX_FORCE", "Outcome", "ForceField", "segment_hits_circle",
    "segment_circle_first_hit", "reflect_velocity",
]
