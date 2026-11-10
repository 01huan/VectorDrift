"""Geometric and heuristic checks for the Procedural Level Validator."""

from __future__ import annotations

import math

from . import config
from .data import SHIPS
from .physics import Outcome, segment_hits_circle
from .validation_grid import _RESOLUTION, _inflated, _reachable
from .validation_report import _check


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


__all__ = [
    "_endpoint_checks", "_grid_checks", "_route_checks", "_difficulty_checks",
    "_direct_blocker_checks", "_required_pickup_checks", "_bomb_checks",
    "_wormhole_checks", "_trivial_field_checks",
]
