"""Flight simulation: linear force field + semi-implicit Euler integration."""

import math
from dataclasses import dataclass
from enum import Enum

from . import config


class Outcome(Enum):
    RUNNING = "running"
    REACHED = "reached"
    TIMEOUT = "timeout"
    OUT_OF_BOUNDS = "out_of_bounds"
    DIVERGED = "diverged"
    ABORTED = "aborted"


@dataclass(frozen=True)
class ForceField:
    """F(x, y) = (a x + b y + c, d x + e y + f), in newtons."""
    a: float = 0.0
    b: float = 0.0
    c: float = 0.0
    d: float = 0.0
    e: float = 0.0
    f: float = 0.0

    @classmethod
    def from_exprs(cls, fx, fy):
        return cls(fx.x, fx.y, fx.c, fy.x, fy.y, fy.c)

    def at(self, x, y):
        return (self.a * x + self.b * y + self.c,
                self.d * x + self.e * y + self.f)


def segment_hits_circle(p0, p1, center, radius):
    """True if the segment p0->p1 comes within `radius` of `center`."""
    x0, y0 = p0
    dx, dy = p1[0] - x0, p1[1] - y0
    cx, cy = center[0] - x0, center[1] - y0
    seg_len2 = dx * dx + dy * dy
    if seg_len2 > 0.0:
        t = max(0.0, min(1.0, (cx * dx + cy * dy) / seg_len2))
    else:
        t = 0.0
    px, py = dx * t - cx, dy * t - cy
    return px * px + py * py <= radius * radius


class Flight:
    """One launch of the ship (always from rest). Advance with `advance(frame_dt)` or `step()`.

    `start` defaults to the level's start; pass another point to resume an
    interrupted run from where it stopped.
    """

    def __init__(self, field, ship, level, start=None,
                 bounds=(config.WORLD_HALF_W, config.WORLD_HALF_H),
                 dt=config.DT):
        self.field = field
        self.mass = ship.mass
        self.hit_radius = level.target_radius + ship.hull_radius
        self.target = level.target_center
        self.bounds = bounds
        self.dt = dt
        self.max_steps = round(level.time_limit / dt)

        self.x, self.y = level.start if start is None else start
        self.vx = self.vy = 0.0
        self.steps = 0
        self.outcome = Outcome.RUNNING
        self.trail = [(self.x, self.y)]
        self._accumulator = 0.0

    # -- derived values ---------------------------------------------------
    @property
    def time(self):
        return self.steps * self.dt

    @property
    def time_left(self):
        return max(0.0, (self.max_steps - self.steps) * self.dt)

    @property
    def force(self):
        return self.field.at(self.x, self.y)

    @property
    def running(self):
        return self.outcome is Outcome.RUNNING

    # -- simulation -------------------------------------------------------
    def step(self):
        if not self.running:
            return self.outcome

        fx, fy = self.field.at(self.x, self.y)
        # Semi-implicit Euler: update velocity first, then position.
        self.vx += fx / self.mass * self.dt
        self.vy += fy / self.mass * self.dt
        nx = self.x + self.vx * self.dt
        ny = self.y + self.vy * self.dt

        p0 = (self.x, self.y)
        self.steps += 1

        if not (math.isfinite(nx) and math.isfinite(ny)
                and math.isfinite(self.vx) and math.isfinite(self.vy)):
            self.outcome = Outcome.DIVERGED
            return self.outcome

        self.x, self.y = nx, ny
        self.trail.append((nx, ny))

        if segment_hits_circle(p0, (nx, ny), self.target, self.hit_radius):
            self.outcome = Outcome.REACHED
        elif abs(nx) > self.bounds[0] or abs(ny) > self.bounds[1]:
            self.outcome = Outcome.OUT_OF_BOUNDS
        elif self.steps >= self.max_steps:
            self.outcome = Outcome.TIMEOUT
        return self.outcome

    def advance(self, frame_dt):
        """Run as many fixed steps as fit into the elapsed frame time."""
        if not self.running:
            return self.outcome
        self._accumulator += min(frame_dt, config.MAX_FRAME_DT)
        while self._accumulator >= self.dt and self.running:
            self._accumulator -= self.dt
            self.step()
        return self.outcome

    def abort(self):
        if self.running:
            self.outcome = Outcome.ABORTED
