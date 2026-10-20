"""Flight simulation with extensible force fields and semi-implicit Euler."""

import math
from dataclasses import dataclass
from enum import Enum

from . import config

# --- safety limits -----------------------------------------------------------
# Huge-but-finite forces (e.g. tan(pi/2) ~= 1.6e16) pass every isfinite() check
# yet tunnel through the target in one step (REACHED) and then crash pygame
# with 1e12-scale screen coordinates. Clamp here so they become DIVERGED.
# Canonical values live in config.py; aliases stay for backward compat.
MAX_FORCE = config.MAX_FORCE
# Single-step displacement guard (backstop for tunneling REACHED). Must allow
# legit fast crossings (Fx=1e5 moves ~14 m in one step) but catch 1e12-scale
# jumps that would fake a hit and crash the renderer.
MAX_STEP_M = config.MAX_STEP_M


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
        """Build a force field from parsed expressions.

        LinearExpr instances retain the legacy coefficient representation.
        General Expression instances use their evaluate(x, y) method.
        """
        linear_x = all(hasattr(fx, name) for name in ("x", "y", "c"))
        linear_y = all(hasattr(fy, name) for name in ("x", "y", "c"))

        if linear_x and linear_y:
            return cls(
                a=fx.x,
                b=fx.y,
                c=fx.c,
                d=fy.x,
                e=fy.y,
                f=fy.c,
            )

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
            
            # 添加更严格的类型检查
            if isinstance(value, (int, float)):
                value = float(value)
            else:
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


class Flight:
    """One launch of the ship, initially at rest.

    Advance with advance(frame_dt) or step().
    `start` defaults to the level start; pass another point to resume.
    """

    def __init__(
        self,
        field,
        ship,
        level,
        start=None,
        bounds=(config.WORLD_HALF_W, config.WORLD_HALF_H),
        dt=config.DT,
        pickups=None,
    ):
        if not math.isfinite(dt) or dt <= 0:
            raise ValueError("dt must be a finite positive number")

        if not math.isfinite(ship.mass) or ship.mass <= 0:
            raise ValueError("Ship mass must be a finite positive number")

        self.field = field
        self.mass = ship.mass
        self.hull_radius = ship.hull_radius
        self.hit_radius = level.target_radius + ship.hull_radius
        self.target = level.target_center
        # (center, radius incl. hull, restitution) — precomputed so step() stays cheap.
        # obstacle_specs is kept (mutable list) so pickup effects (bomb) can
        # remove obstacles mid-flight; obstacles is rebuilt alongside it.
        self.obstacle_specs = list(getattr(level, "obstacles", ()) or ())
        self.obstacles = tuple(
            ((o.center[0], o.center[1]), o.radius + ship.hull_radius, o.restitution)
            for o in self.obstacle_specs
        )
        # Runtime pickups (consumed flag lives on PickupState, never on spec).
        # Shared by reference when the caller passes them (GameScene passes
        # its run-level list so consumed pickups persist across lives);
        # otherwise built fresh from level.pickups. No config = no pickups.
        from .pickups import PickupState
        if pickups is None:
            specs = getattr(level, "pickups", ()) or ()
            self.pickups = tuple(PickupState.from_spec(s) for s in specs)
        else:
            self.pickups = tuple(pickups)
        self.pickup_events = []  # event dicts from triggered pickups (scene/tests)
        self.bounds = bounds
        self.dt = dt
        self.max_steps = round(level.time_limit / dt)

        self.x, self.y = level.start if start is None else start
        self.vx = self.vy = 0.0
        self.bounces = 0
        self.steps = 0
        self.outcome = Outcome.RUNNING
        self.trail = [(self.x, self.y)]
        self._accumulator = 0.0

    @property
    def time(self):
        return self.steps * self.dt

    @property
    def time_left(self):
        return max(0.0, (self.max_steps - self.steps) * self.dt)

    @property
    def force(self):
        try:
            return self.field.at(self.x, self.y)
        except (ArithmeticError, ValueError, TypeError, OverflowError,
                RecursionError, MemoryError):
            return (math.nan, math.nan)

    @property
    def running(self):
        return self.outcome is Outcome.RUNNING

    def step(self):
        if not self.running:
            return self.outcome

        try:
            fx, fy = self.field.at(self.x, self.y)

            # Semi-implicit Euler: update velocity before position.
            vx = self.vx + fx / self.mass * self.dt
            vy = self.vy + fy / self.mass * self.dt

            nx = self.x + vx * self.dt
            ny = self.y + vy * self.dt

        except (ArithmeticError, ValueError, TypeError, OverflowError,
                RecursionError, MemoryError):
            self.steps += 1
            self.outcome = Outcome.DIVERGED
            return self.outcome

        self.steps += 1

        if not all(math.isfinite(v) for v in (nx, ny, vx, vy)):
            self.outcome = Outcome.DIVERGED
            return self.outcome

        # Tunneling guard: a single step must not jump across the world.
        # Huge-but-finite F (tan(pi/2)) would otherwise fake a REACHED hit.
        if math.hypot(nx - self.x, ny - self.y) > MAX_STEP_M:
            self.outcome = Outcome.DIVERGED
            return self.outcome

        p0 = (self.x, self.y)

        self.vx, self.vy = vx, vy
        self.x, self.y = nx, ny
        self._bounce_along_path(p0)
        # Pickups use the same segment test (no tunneling); one shared call
        # handles every kind — no per-kind branches in the loop.
        from .pickups import check_pickups_segment
        self.pickup_events.extend(
            check_pickups_segment(self.pickups, p0, (self.x, self.y),
                                  self.hull_radius, ctx=self)
        )

        if segment_hits_circle(
            p0, (self.x, self.y), self.target, self.hit_radius
        ):
            self.outcome = Outcome.REACHED
        elif abs(self.x) > self.bounds[0] or abs(self.y) > self.bounds[1]:
            self.outcome = Outcome.OUT_OF_BOUNDS
        elif self.steps >= self.max_steps:
            self.outcome = Outcome.TIMEOUT

        return self.outcome

    def _bounce_along_path(self, p0):
        """Reflect off bumpers hit along this step's path (closest first)."""
        if not self.obstacles:
            self.trail.append((self.x, self.y))
            return
        start = p0
        end = (self.x, self.y)
        for _ in range(max(1, len(self.obstacles) * 2)):
            earliest = None  # (t, center, radius, restitution)
            for center, radius, restitution in self.obstacles:
                t = segment_circle_first_hit(start, end, center, radius)
                if t is not None and (earliest is None or t < earliest[0]):
                    earliest = (t, center, radius, restitution)
            if earliest is None:
                break
            t, center, radius, restitution = earliest
            hx = start[0] + (end[0] - start[0]) * t
            hy = start[1] + (end[1] - start[1]) * t
            nx, ny = hx - center[0], hy - center[1]
            dist = math.hypot(nx, ny)
            if dist < 1e-9:
                # Dead-center hit: fall back to incoming direction.
                nx, ny = -self.vx, -self.vy
                dist = math.hypot(nx, ny)
                if dist < 1e-9:
                    nx, ny, dist = 1.0, 0.0, 1.0
            nx, ny = nx / dist, ny / dist
            self.vx, self.vy = reflect_velocity(self.vx, self.vy, nx, ny,
                                                restitution)
            # Nudge off the surface so the next test starts outside.
            hx, hy = hx + nx * 1e-6, hy + ny * 1e-6
            # Remaining leg re-emitted from the contact point.
            frac = 1.0 - t
            end = (hx + self.vx * self.dt * frac, hy + self.vy * self.dt * frac)
            start = (hx, hy)
            self.bounces += 1
            self.trail.append((hx, hy))
        self.x, self.y = end
        self.trail.append((self.x, self.y))

    def advance(self, frame_dt):
        """Run fixed simulation steps fitting into elapsed frame time."""
        if not self.running:
            return self.outcome

        if not math.isfinite(frame_dt) or frame_dt < 0:
            raise ValueError("frame_dt must be a finite non-negative number")

        self._accumulator += min(frame_dt, config.MAX_FRAME_DT)

        while self._accumulator >= self.dt and self.running:
            self._accumulator -= self.dt
            self.step()

        return self.outcome

    def abort(self):
        if self.running:
            self.outcome = Outcome.ABORTED