"""Procedural Level Validator.

Every generated level is checked *before it is handed to the player*.  The
checks come in two flavours:

* **Fast path analysis** -- pure geometry, always runs.  A coarse occupancy
  grid plus A* decides whether a route exists at all, whether the intended
  route legs are clear, whether required pickups (e.g. the bomb module's
  shockwave) are reachable, and whether the wormhole walls are really sealed.
  This is what catches "everything is blocked" and "the required pickup is
  unreachable".
* **AI Solver probe** -- a short, deterministic PSO run (small budget) asks
  whether a non-trivial force field can actually fly the level under the
  formal game physics.  Passing confirms solvability; failing only marks the
  report as *unconfirmed* because the geometric checks already guarantee a
  path (the generator builds one), so a failed probe never rejects a level
  by itself -- unless ``require_solver_confirmed`` is set in the preset (see
  ``ValidationProfile``) or forced with ``require_solver=True``.

Difficulty heuristics (route length vs time limit, obstacle density) are
warnings: they flag levels that are likely too easy or too hard, but they are
never a hard error because players -- and the AI Solver -- still get to try.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from . import config
from .data import LevelSpec, SHIPS
from .physics import Outcome, segment_hits_circle

_RESOLUTION = 0.12


@dataclass(frozen=True)
class ValidationCheck:
    name: str
    passed: bool
    severity: str        # "error" | "warning" | "info"
    message: str
    details: dict = field(default_factory=dict)


@dataclass
class ValidationReport:
    level_id: int
    seed: int | None
    generator: str
    checks: list
    metrics: dict = field(default_factory=dict)
    solver_confirmed: bool | None = None
    solver_result: object | None = None
    route: tuple | None = None
    segments: tuple | None = None

    @property
    def ok(self):
        return not any(c.severity == "error" and not c.passed
                       for c in self.checks)

    @property
    def errors(self):
        return [c for c in self.checks if c.severity == "error" and not c.passed]

    @property
    def warnings(self):
        return [c for c in self.checks if c.severity == "warning" and not c.passed]

    @property
    def infos(self):
        return [c for c in self.checks if c.severity == "info"]

    def summary(self):
        errors = len(self.errors)
        warnings = len(self.warnings)
        if errors:
            status = "REJECTED"
        elif self.solver_confirmed is True:
            status = "OK (solver confirmed)"
        elif self.solver_confirmed is None:
            status = "OK (geometry only)"
        else:
            status = "OK (solver probe found nothing in budget)"
        failed = ", ".join(c.name for c in self.errors) or "-"
        return (f"level {self.level_id} [{self.generator}] seed={self.seed}: "
                f"{status}; {len(self.checks)} checks, "
                f"{errors} error(s) [{failed}], {warnings} warning(s)")

    def to_dict(self):
        return {
            "level_id": self.level_id,
            "seed": self.seed,
            "generator": self.generator,
            "ok": self.ok,
            "solver_confirmed": self.solver_confirmed,
            "metrics": dict(self.metrics),
            "checks": [
                {"name": c.name, "passed": c.passed, "severity": c.severity,
                 "message": c.message, "details": dict(c.details)}
                for c in self.checks
            ],
        }


def _check(checks, name, passed, severity, message, **details):
    checks.append(ValidationCheck(name=name, passed=bool(passed),
                                  severity=severity, message=message,
                                  details=details))


# ----------------------------------------------------------------- grid
def _as_discs(obstacles, hull):
    """Normalise obstacles to [(center, radius + hull)] discs.

    Accepts ObstacleSpec objects or (center, radius) pairs.
    """
    discs = []
    for ob in obstacles:
        center = getattr(ob, "center", None)
        radius = getattr(ob, "radius", None)
        if center is None:
            center, radius = ob
        discs.append(((center[0], center[1]), radius + hull))
    return discs


def _inflated(obstacles, hull):
    return _as_discs(obstacles, hull)


def _build_grid(obstacles, resolution=_RESOLUTION):
    """Occupancy grid of the world; True = blocked by an inflated disc."""
    w = int(2 * config.WORLD_HALF_W / resolution) + 1
    h = int(2 * config.WORLD_HALF_H / resolution) + 1
    blocked = bytearray(w * h)
    for (cx, cy), r in obstacles:
        i0 = max(0, int((cx - r + config.WORLD_HALF_W) / resolution) - 1)
        i1 = min(w - 1, int((cx + r + config.WORLD_HALF_W) / resolution) + 1)
        j0 = max(0, int((cy - r + config.WORLD_HALF_H) / resolution) - 1)
        j1 = min(h - 1, int((cy + r + config.WORLD_HALF_H) / resolution) + 1)
        r2 = r * r
        for j in range(j0, j1 + 1):
            cy_cell = -config.WORLD_HALF_H + j * resolution
            dy = cy_cell - cy
            dy2 = dy * dy
            if dy2 > r2:
                continue
            half = math.sqrt(r2 - dy2)
            col0 = max(0, int((cx - half + config.WORLD_HALF_W) / resolution))
            col1 = min(w - 1, int((cx + half + config.WORLD_HALF_W) / resolution))
            row_base = j * w
            for i in range(col0, col1 + 1):
                blocked[row_base + i] = 1
    return blocked, w, h


def _cell(point, resolution=_RESOLUTION):
    i = int((point[0] + config.WORLD_HALF_W) / resolution)
    j = int((point[1] + config.WORLD_HALF_H) / resolution)
    i = max(0, min(int(2 * config.WORLD_HALF_W / resolution), i))
    j = max(0, min(int(2 * config.WORLD_HALF_H / resolution), j))
    return i, j


def _nearest_free(blocked, w, h, cell, max_radius=6):
    if not blocked[cell[1] * w + cell[0]]:
        return cell
    for radius in range(1, max_radius + 1):
        for dj in range(-radius, radius + 1):
            for di in range(-radius, radius + 1):
                if abs(di) != radius and abs(dj) != radius:
                    continue
                i, j = cell[0] + di, cell[1] + dj
                if 0 <= i < w and 0 <= j < h and not blocked[j * w + i]:
                    return (i, j)
    return None


def _astar(blocked, w, h, start, goal):
    """A* over the 8-connected grid. Returns (reachable, cost)."""
    import heapq

    if start is None or goal is None:
        return False, math.inf
    sx, sy = start
    gx, gy = goal
    if blocked[sy * w + sx] or blocked[gy * w + gx]:
        return False, math.inf

    def hfun(i, j):
        dx, dy = abs(i - gx), abs(j - gy)
        return max(dx, dy) + 0.4142 * min(dx, dy)

    start_index = sy * w + sx
    goal_index = gy * w + gx
    g_score = {start_index: 0.0}
    came_from = {}
    heap = [(hfun(sx, sy), 0.0, start_index)]
    closed = bytearray(w * h)
    neighbours = ((1, 0, 1.0), (0, 1, 1.0), (-1, 0, 1.0), (0, -1, 1.0),
                  (1, 1, 1.4142), (1, -1, 1.4142), (-1, 1, 1.4142),
                  (-1, -1, 1.4142))
    while heap:
        _, cost, index = heapq.heappop(heap)
        if closed[index]:
            continue
        closed[index] = 1
        if index == goal_index:
            return True, cost
        i, j = index % w, index // w
        for di, dj, step in neighbours:
            ni, nj = i + di, j + dj
            if not (0 <= ni < w and 0 <= nj < h):
                continue
            n_index = nj * w + ni
            if blocked[n_index] or closed[n_index]:
                continue
            tentative = cost + step
            if tentative < g_score.get(n_index, math.inf):
                g_score[n_index] = tentative
                came_from[n_index] = index
                heapq.heappush(heap,
                               (tentative + hfun(ni, nj), tentative, n_index))
    return False, math.inf


def _reachable(level, obstacles, start, goal, resolution=_RESOLUTION,
               nearest=True):
    hull = SHIPS.get(level.ship_id, SHIPS["ship01"]).hull_radius
    blocked, w, h = _build_grid(_as_discs(obstacles, hull), resolution)
    start_cell = _nearest_free(blocked, w, h, _cell(start, resolution))
    goal_cell = (_nearest_free(blocked, w, h, _cell(goal, resolution))
                 if nearest else _cell(goal, resolution))
    return _astar(blocked, w, h, start_cell, goal_cell)


# ------------------------------------------------------------- checks
def _endpoint_checks(level, preset, checks):
    start, target = level.start, level.target_center
    in_bounds = (abs(start[0]) <= config.WORLD_HALF_W and
                 abs(start[1]) <= config.WORLD_HALF_H and
                 abs(target[0]) <= config.WORLD_HALF_W and
                 abs(target[1]) <= config.WORLD_HALF_H)
    _check(checks, "endpoints_in_bounds", in_bounds, "error",
           "start/target lie inside the default world bounds" if in_bounds
           else "start/target out of the default world bounds")

    minimum = getattr(preset, "min_start_target_dist", 10.0)
    dist = math.dist(start, target)
    _check(checks, "endpoint_distance", dist >= minimum - 1e-9, "error",
           f"start->target distance {dist:.2f} m (minimum {minimum:.2f})",
           distance=dist, minimum=minimum)

    hull = SHIPS.get(level.ship_id, SHIPS["ship01"]).hull_radius
    close_start = close_target = False
    for ob in level.obstacles:
        if math.dist(start, ob.center) < ob.radius + hull - 1e-6:
            close_start = True
        if math.dist(target, ob.center) < ob.radius + level.target_radius:
            close_target = True
    _check(checks, "start_clear", not close_start, "warning",
           "start pad clear of obstacles" if not close_start
           else "an obstacle overlaps the start pad")
    _check(checks, "target_clear", not close_target, "warning",
           "target clear of obstacles" if not close_target
           else "an obstacle overlaps the target disc")


def _grid_checks(level, obstacles, checks, metrics=None, expect_blocked=False):
    start, target = level.start, level.target_center
    reachable, cost = _reachable(level, obstacles, start, target)
    if metrics is not None:
        metrics["a_star_length_m"] = cost * _RESOLUTION
    if expect_blocked:
        _check(checks, "path_exists", not reachable, "info",
               "the target is sealed: no plain path exists (by design)"
               if not reachable else
               "the target is reachable without any pickup (ring not sealed)")
        return
    _check(checks, "path_exists", reachable, "error",
           "a flight path exists from start to target" if reachable
           else "no path from start to target (everything is blocked)")


def _route_checks(level, route, segments, checks, metrics, module=None):
    if not segments:
        return
    hull = SHIPS.get(level.ship_id, SHIPS["ship01"]).hull_radius
    inflated = _inflated(level.obstacles, hull)
    # The bomb module's final leg runs through the sealed ring by design; it
    # only clears after a shockwave blast, which the bomb checks verify.
    legs = list(segments)
    check_legs = legs[:-1] if module == "bomb" else legs
    clear = True
    hit = None
    length = 0.0
    for a, b in legs:
        length += math.dist(a, b)
    for a, b in check_legs:
        for center, radius in inflated:
            if segment_hits_circle(a, b, center, radius):
                clear = False
                hit = (a, b, center)
                break
        if not clear:
            break
    _check(checks, "route_clear", clear, "error",
           "the intended route legs are clear of obstacles" if clear
           else f"the intended route passes through an obstacle at {hit[2]}",
           hit=hit)
    metrics["route_length"] = length
    return length


def _difficulty_checks(level, route_length, preset, checks, metrics,
                       a_star=None, module=None):
    profile = getattr(preset, "validation", None)
    if profile is None:
        return
    # A* shortest path length is the realistic minimum flying distance; the
    # intended (often deliberately winding) route is only a fallback for
    # levels the grid cannot reach (wormhole gates, sealed bomb rings).
    base = a_star if (a_star and math.isfinite(a_star) and a_star > 0.0) else route_length
    reference = max(profile.reference_speed, 0.1)
    limit = float(level.time_limit)
    estimate = base / reference if base else 0.0
    fraction = estimate / limit if limit > 0 else math.inf
    metrics["route_time_estimate_s"] = estimate
    metrics["route_time_fraction"] = fraction
    ok = profile.min_route_time_fraction <= fraction <= profile.max_route_time_fraction
    if fraction > profile.max_route_time_fraction:
        message = (f"route needs ~{estimate:.1f}s at {reference:.1f} m/s, "
                   f"{fraction * 100:.0f}% of the {limit:.1f}s limit -- too hard")
    elif fraction < profile.min_route_time_fraction:
        message = (f"route needs ~{estimate:.1f}s at {reference:.1f} m/s, "
                   f"{fraction * 100:.0f}% of the {limit:.1f}s limit -- trivial")
    else:
        message = (f"route time ~{estimate:.1f}s of {limit:.1f}s limit "
                   f"({fraction * 100:.0f}%) -- within difficulty band")
    _check(checks, "route_time_fraction", ok, "warning", message,
           estimate=estimate, fraction=fraction, limit=limit)

    obstacles = list(level.obstacles)
    area = (2 * config.WORLD_HALF_W) * (2 * config.WORLD_HALF_H)
    density = len(obstacles) / area
    metrics["obstacle_count"] = len(obstacles)
    metrics["obstacle_density"] = density
    if profile.max_obstacle_density is not None:
        _check(checks, "obstacle_density",
               density <= profile.max_obstacle_density, "warning",
               f"{len(obstacles)} obstacles ({density:.4f}/m^2, "
               f"limit {profile.max_obstacle_density})",
               density=density)

    lo = getattr(preset, "num_obstacles_min", None)
    hi = getattr(preset, "num_obstacles_max", None)
    countable = module in (None, "corridor", "extreme_time")
    if (lo is not None or hi is not None) and countable:
        lo = 0 if lo is None else int(lo)
        hi = int(hi) if hi is not None else len(obstacles)
        in_range = lo <= len(obstacles) <= hi
        _check(checks, "obstacle_count", in_range, "warning",
               f"{len(obstacles)} obstacles (expected {lo}..{hi})",
               count=len(obstacles))


def _direct_blocker_checks(level, preset, checks):
    required = int(getattr(preset, "num_direct_blockers", 0) or 0)
    if required <= 0:
        return
    hull = SHIPS.get(level.ship_id, SHIPS["ship01"]).hull_radius
    hits = sum(1 for ob in level.obstacles
               if segment_hits_circle(level.start, level.target_center,
                                      ob.center, ob.radius + hull))
    _check(checks, "direct_line_blocked", hits >= required, "warning",
           f"{hits} obstacle(s) block the straight line "
           f"(need {required})", hits=hits)


def _required_pickup_checks(level, preset, checks):
    kinds = tuple(getattr(preset, "required_pickup_kinds", ()) or ())
    if not kinds:
        return
    start = level.start
    for kind in kinds:
        matching = [p for p in level.pickups if getattr(p, "kind", None) == kind]
        if not matching:
            _check(checks, "required_pickup_present", False, "error",
                   f"level requires a {kind!r} pickup but none was placed",
                   kind=kind)
            continue
        reachable = False
        for pickup in matching:
            ok, _ = _reachable(level, level.obstacles, start, pickup.center,
                               nearest=False)
            if ok:
                reachable = True
                break
        _check(checks, "required_pickup_reachable", reachable, "error",
               f"at least one {kind!r} pickup is reachable from the start"
               if reachable
               else f"no {kind!r} pickup is reachable from the start",
               kind=kind, count=len(matching))


def _bomb_checks(level, checks):
    """The bomb module: the ring must be sealed, and a reachable shockwave
    must open it."""
    shockwaves = [p for p in level.pickups if getattr(p, "kind", None) == "shockwave"]
    if not shockwaves:
        return  # presence already reported by required_pickup_present
    from .pickups import SHOCKWAVE_BLAST_RADIUS, obstacles_hit_by_blast

    start = level.start
    target = level.target_center

    # 1) The target must NOT be reachable while the ring is intact.
    sealed, _ = _reachable(level, level.obstacles, start, target)
    _check(checks, "target_sealed", not sealed, "warning",
           "the ring is sealed: the target is not reachable without blasting"
           if not sealed
           else "the target is reachable without blasting; the ring is open")

    # 2) Pick the first shockwave whose blast opens the route to the target.
    opened = False
    destroyed_count = 0
    for pickup in shockwaves:
        survivors, destroyed = obstacles_hit_by_blast(
            pickup.center, SHOCKWAVE_BLAST_RADIUS, level.obstacles)
        blast_opens, _ = _reachable(level, survivors,
                                    pickup.center, target)
        if blast_opens:
            opened = True
            destroyed_count = len(destroyed)
            break
    _check(checks, "path_opens_after_blast", opened, "error",
           f"blasting a shockwave opens the route to the target "
           f"({destroyed_count} obstacle(s) destroyed)" if opened
           else "no shockwave blast opens a path to the target",
           destroyed=destroyed_count)


def _wormhole_checks(level, walls, teleports, checks):
    hull = SHIPS.get(level.ship_id, SHIPS["ship01"]).hull_radius
    # 1) Every wall seals the world span it crosses.
    sealed_all = True
    details = []
    for axis, fixed, lo, hi in walls:
        intervals = []
        for ob in level.obstacles:
            if axis == "v":
                d = abs(ob.center[0] - fixed)
            else:
                d = abs(ob.center[1] - fixed)
            reach = ob.radius + hull
            if d < reach:
                half = math.sqrt(max(0.0, reach * reach - d * d))
                if axis == "v":
                    intervals.append((ob.center[1] - half, ob.center[1] + half))
                else:
                    intervals.append((ob.center[0] - half, ob.center[0] + half))
        intervals.sort()
        cursor = lo
        covered = True
        for a, b in intervals:
            if a > cursor + 1e-9:
                covered = False
                break
            cursor = max(cursor, b)
        covered = covered and cursor >= hi - 1e-9
        sealed_all = sealed_all and covered
        details.append({"wall": fixed, "axis": axis, "sealed": covered})
    _check(checks, "walls_sealed", sealed_all, "error",
           "every wormhole gate is sealed by bumper rocks" if sealed_all
           else "a wormhole gate has a gap the ship can fly through",
           walls=details)

    # 2) Holes are inside the world and usable (not buried in rock).
    holes_ok = True
    hole_details = []
    for black, white in teleports:
        for point in (black, white):
            if (abs(point[0]) > config.WORLD_HALF_W or
                    abs(point[1]) > config.WORLD_HALF_H):
                holes_ok = False
                hole_details.append({"point": point, "issue": "out of bounds"})
                continue
            buried = any(math.dist(point, ob.center) < ob.radius + hull - 1e-9
                         for ob in level.obstacles)
            if buried:
                holes_ok = False
                hole_details.append({"point": point, "issue": "buried in rock"})
        if math.dist(black, white) < 0.4:
            holes_ok = False
            hole_details.append({"black": black, "white": white,
                                 "issue": "holes too close together"})
    _check(checks, "holes_valid", holes_ok, "error",
           "wormhole pairs are placed on free ground" if holes_ok
           else "a wormhole pair is unusable (out of bounds or buried)",
           holes=hole_details)


def _trivial_field_checks(level, checks):
    """A level solved by a trivial field is formula-dependent and dull."""
    from .expr_parser import parse_expression
    from .physics import Flight, ForceField

    tx, ty = level.target_center
    candidates = [
        (f"{tx} - x", f"{ty} - y"),
        (f"2 * ({tx} - x)", f"2 * ({ty} - y)"),
        (f"4 * ({tx} - x)", f"4 * ({ty} - y)"),
        (f"({tx} - x) / 3", f"({ty} - y) / 3"),
        ("-x", "-y"),
        ("1", "0"),
        ("0", "1"),
    ]
    hit = None
    from .data import SHIPS
    ship = SHIPS.get(level.ship_id, SHIPS["ship01"])
    for fx, fy in candidates:
        try:
            field = ForceField.from_exprs(parse_expression(fx), parse_expression(fy))
            flight = Flight(field, ship, level)
            flight.max_steps = min(flight.max_steps, 600)  # 5 s is plenty to flag
            while flight.running:
                flight.step()
            if flight.outcome is Outcome.REACHED:
                hit = (fx, fy)
                break
        except Exception:
            continue
    _check(checks, "trivial_field", hit is None, "warning",
           "no trivial target-attraction field solves the level" if hit is None
           else f"a trivial field solves the level (fx={hit[0]}, fy={hit[1]}); "
                "it may be too easy",
           trivial=hit)


def _solver_probe(level, preset, checks, profile, seed):
    run_solver = getattr(profile, "run_solver", False)
    if not run_solver:
        _check(checks, "solver_confirms", True, "info",
               "AI Solver probe disabled for this preset")
        return None, None
    from .expr_parser import parse_expression
    from .physics import ForceField
    from .solver import PSOConfig, PSOSolver

    probe_seed = seed if seed is not None else 0
    solver = PSOSolver(PSOConfig(
        template_key=getattr(profile, "solver_template", "general_poly"),
        n_particles=getattr(profile, "solver_particles", 10),
        max_simulations=getattr(profile, "solver_simulations", 16),
        early_stop_on_success=True,
        n_workers=1,
        max_steps=getattr(profile, "solver_max_steps", 480),
        record_trajectory=False,
        seed=probe_seed,
    ))
    result = solver.solve(level,
                          simulation_budget=getattr(profile, "solver_simulations", 16),
                          rng_seed=probe_seed)
    confirmed = False
    flight_time = None
    best = getattr(result, "best", None)
    if best is not None:
        try:
            field = ForceField.from_exprs(parse_expression(best.fx_text),
                                          parse_expression(best.fy_text))
            ship = SHIPS.get(level.ship_id, SHIPS["ship01"])
            from .physics import Flight
            flight = Flight(field, ship, level)
            while flight.running:
                flight.step()
            confirmed = flight.outcome is Outcome.REACHED
            flight_time = flight.time
        except Exception:
            confirmed = False
    require = bool(getattr(profile, "require_solver_confirmed", False))
    message = ("AI Solver found a verified solution under the formal physics"
               if confirmed else
               "AI Solver found no solution within the probe budget "
               "(geometry still guarantees a path)")
    _check(checks, "solver_confirms", confirmed or not require, "info",
           message if not require else message,
           confirmed=confirmed, flight_time=flight_time,
           simulations=getattr(result, "total_simulations", None))
    return confirmed, result


# ----------------------------------------------------------------- API
def validate_level(level, *, preset=None, route=None, segments=None,
                   teleports=None, walls=None, generator=None, seed=None,
                   run_solver=None, require_solver=None):
    """Validate one generated (or fixed) level.

    Pass the intended ``route``/``segments``/``teleports``/``walls`` from the
    generator whenever available; the geometric checks use them.  ``preset``
    supplies the difficulty knobs and the AI Solver probe settings.
    """
    from .level_presets import PRESETS, RandomPreset, ValidationProfile

    if preset is None:
        preset = PRESETS.get(getattr(level, "id", None))
    import dataclasses
    profile = getattr(preset, "validation", ValidationProfile())
    if run_solver is not None:
        profile = dataclasses.replace(profile, run_solver=bool(run_solver))
    if require_solver is not None:
        profile = dataclasses.replace(profile,
                                      require_solver_confirmed=bool(require_solver))

    module = generator or getattr(preset, "generator", "corridor")
    checks = []
    metrics = {"module": module, "time_limit": level.time_limit,
               "lives": level.lives, "target_radius": level.target_radius}
    teleports = teleports or ()
    walls = walls or ()

    _endpoint_checks(level, preset, checks)
    if module == "wormhole_network":
        _wormhole_checks(level, walls, teleports, checks)
        _grid_checks(level, level.obstacles, checks, metrics, expect_blocked=True)
    elif module == "bomb":
        _grid_checks(level, level.obstacles, checks, metrics, expect_blocked=True)
    else:
        _grid_checks(level, level.obstacles, checks, metrics)
    if segments:
        _route_checks(level, route, segments, checks, metrics, module)
    _difficulty_checks(level, metrics.get("route_length"), preset, checks,
                       metrics, a_star=metrics.get("a_star_length_m"),
                       module=module)
    _direct_blocker_checks(level, preset, checks)
    _required_pickup_checks(level, preset, checks)
    if module == "bomb":
        _bomb_checks(level, checks)
    _trivial_field_checks(level, checks)
    solver_confirmed, solver_result = _solver_probe(level, preset, checks,
                                                    profile, seed)

    return ValidationReport(
        level_id=getattr(level, "id", 0),
        seed=seed,
        generator=module,
        checks=checks,
        metrics=metrics,
        solver_confirmed=solver_confirmed,
        solver_result=solver_result,
        route=tuple(route) if route else None,
        segments=tuple(segments) if segments else None,
    )
