"""Placement rules for procedurally generated levels.

Pure geometry: no pygame, no registry mutation. :mod:`vector_drift.random_level`
owns the generation/retry flow and re-exports these helpers for compatibility.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from . import config
from .data import ObstacleSpec
from .level_presets import get_preset
from .physics_core import segment_hits_circle


@dataclass(frozen=True)
class PlaceContext:
    """Everything a placement rule may inspect for one candidate disc."""

    center: tuple
    radius: float
    segments: tuple  # hidden safe corridor
    start: tuple
    target: tuple
    placed: tuple  # previously accepted (center, radius) pairs (both kinds)
    preset: object  # RandomPreset
    index: int  # len(placed): 0-based position of this candidate
    for_pickup: bool = False  # True: skip obstacle-only rules (block/corridor)


def _rand_point(rng, margin):
    """Uniform point inside the world rect shrunk by ``margin``."""
    x = rng.uniform(-config.WORLD_HALF_W + margin, config.WORLD_HALF_W - margin)
    y = rng.uniform(-config.WORLD_HALF_H + margin, config.WORLD_HALF_H - margin)
    return (x, y)


def _preset_or_default(preset=None, level_id=8):
    return preset if preset is not None else get_preset(level_id)


def sample_endpoints(rng, preset=None):
    """Sample (start, target) with distance >= L."""
    preset = _preset_or_default(preset)
    for _ in range(preset.max_endpoint_attempts):
        start = _rand_point(rng, preset.endpoint_margin)
        target = _rand_point(rng, preset.endpoint_margin)
        if math.dist(start, target) >= preset.min_start_target_dist:
            return start, target
    raise RuntimeError("could not sample separated start/target")


def sample_hidden_points(rng, count=None, preset=None):
    """Sample ``count`` hidden waypoints spread over the world."""
    preset = _preset_or_default(preset)
    count = preset.num_hidden_points if count is None else count
    return [_rand_point(rng, preset.hidden_margin) for _ in range(count)]


def build_corridor(start, hidden_points, target, rng):
    """Join start -> shuffled hidden points -> target; keep segments."""
    order = list(hidden_points)
    rng.shuffle(order)
    ordered = [start, *order, target]
    segments = list(zip(ordered[:-1], ordered[1:]))
    return ordered, segments


def rule_clear_of_endpoints(ctx):
    """Keep discs away from start pad and target edge."""
    p = ctx.preset
    if math.dist(ctx.center, ctx.start) <= ctx.radius + p.start_clearance:
        return False
    if math.dist(ctx.center, ctx.target) <= ctx.radius + p.target_radius + p.target_clearance:
        return False
    return True


def rule_direct_blockers(ctx):
    """First N discs must block the start->target shortcut (no free shot)."""
    if ctx.for_pickup:
        return True
    if ctx.index < ctx.preset.num_direct_blockers:
        return segment_hits_circle(ctx.start, ctx.target, ctx.center, ctx.radius)
    return True


def rule_clear_of_corridor(ctx):
    """Every disc must clear the hidden safe corridor (segment, not line)."""
    if ctx.for_pickup:
        return True
    clearance = ctx.radius + ctx.preset.corridor_clearance
    return not any(segment_hits_circle(a, b, ctx.center, clearance) for a, b in ctx.segments)


def rule_spaced_from_peers(ctx):
    """Discs must not overlap each other (plus gap) -- any kind mix."""
    gap = ctx.preset.min_obstacle_gap
    from .pickups import discs_overlap  # lazy: avoids import cycle
    return not any(
        discs_overlap(ctx.center, ctx.radius, c, r, gap) for c, r in ctx.placed
    )


def rule_pickup_on_corridor(ctx):
    """Pickups must sit ON the route so the ship can actually reach them."""
    if not ctx.for_pickup:
        return True
    limit = ctx.radius + float(getattr(ctx.preset, "pickup_corridor_max", 0.6))
    return any(segment_hits_circle(a, b, ctx.center, limit) for a, b in ctx.segments)


# Rules shared by obstacles AND pickups (endpoint clearance, peer spacing).
COMMON_RULES = (
    rule_clear_of_endpoints,
    rule_spaced_from_peers,
)

# Rules that apply ONLY to obstacles (pickups intentionally ignore them).
OBSTACLE_ONLY_RULES = (
    rule_direct_blockers,
    rule_clear_of_corridor,
)

# Full obstacle pipeline: common + obstacle-only + preset extras.
OBSTACLE_RULES = (*COMMON_RULES, *OBSTACLE_ONLY_RULES)


def _obstacle_ok(center, radius, segments, start, target, placed, preset=None):
    """Check one candidate against corridor, endpoints and peers."""
    preset = _preset_or_default(preset)
    ctx = PlaceContext(
        center=center, radius=radius, segments=tuple(segments),
        start=start, target=target, placed=tuple(placed),
        preset=preset, index=len(placed),
    )
    return all(rule(ctx) for rule in (*OBSTACLE_RULES, *preset.extra_rules))


def _obstacle_count(preset, rng, count=None):
    """Resolve obstacle count: explicit override, else fixed or min/max."""
    if count is not None:
        return count
    lo = getattr(preset, "num_obstacles_min", None)
    hi = getattr(preset, "num_obstacles_max", None)
    if lo is None and hi is None:
        return getattr(preset, "num_obstacles", 0)
    if lo is None:
        lo = getattr(preset, "num_obstacles", 0)
    if hi is None:
        hi = getattr(preset, "num_obstacles", 0)
    if hi < lo:
        lo, hi = hi, lo
    return rng.randint(int(lo), int(hi))


def place_obstacles(rng, segments, start, target, count=None, preset=None,
                    placed=None, strict=True):
    """Sample ``count`` non-blocking obstacles around the corridor.

    ``placed`` seeds the peer list (e.g. the walls of a wormhole module) so
    scattered obstacles never stack on them.  With ``strict=False`` a disc
    that cannot be placed is skipped instead of raising, so tight routes
    (the slalom module) still get as many rocks as fit.
    """
    preset = _preset_or_default(preset)
    count = _obstacle_count(preset, rng, count)
    placed = list(placed) if placed else []  # [(center, radius)]
    seed_count = len(placed)  # pre-seeded peers are not returned as new rocks
    for _ in range(count):
        placed_any = False
        for _ in range(preset.max_place_attempts):
            radius = rng.uniform(preset.obstacle_radius_min, preset.obstacle_radius_max)
            margin = radius + preset.edge_margin
            if margin >= config.WORLD_HALF_W or margin >= config.WORLD_HALF_H:
                continue
            center = _rand_point(rng, margin)
            if _obstacle_ok(center, radius, segments, start, target, placed, preset):
                placed.append((center, radius))
                placed_any = True
                break
        if not placed_any:
            if strict:
                raise RuntimeError("could not place a non-blocking obstacle")
    return tuple(
        ObstacleSpec(center=center, radius=radius, restitution=preset.restitution,
                     kind=preset.obstacle_kind)
        for center, radius in placed[seed_count:]
    )


def _pickup_ok(center, radius, segments, start, target, placed, preset=None):
    """Check one pickup candidate: endpoints + peers (any kind) + on-route."""
    preset = _preset_or_default(preset)
    ctx = PlaceContext(
        center=center, radius=radius, segments=tuple(segments),
        start=start, target=target, placed=tuple(placed),
        preset=preset, index=len(placed), for_pickup=True,
    )
    # Common rules (endpoints, peer spacing) + pickup-only on-route rule.
    return all(rule(ctx) for rule in (*COMMON_RULES, rule_pickup_on_corridor,
                                      *preset.extra_rules))


def place_pickups(rng, segments, start, target, placed=(), groups=None, preset=None):
    """Sample pickups ON the corridor, clear of discs and endpoints.

    Same shape as obstacles: just center + size (+ kind). ``groups`` is an
    iterable of (kind, count, radius); default = preset.pickup_groups, so
    random levels are fully driven by level_presets.py. ``placed`` seeds
    the peer list with obstacle (center, radius) pairs so pickup<->obstacle
    and pickup<->pickup never stack. Returns () instead of raising when
    the route is too crowded (pickups are bonus, not required).
    """
    from .data import PickupSpec  # lazy: avoids data <-> random_level cycle

    preset = _preset_or_default(preset)
    if groups is None:
        groups = getattr(preset, "pickup_groups", ())
    peers = list(placed)
    out = []
    for group in groups or ():
        # Support count/radius as fixed values or (min, max) ranges.
        if not isinstance(group, (tuple, list)) or len(group) < 3:
            continue
        kind = group[0]
        if len(group) == 3:
            count_spec, radius_spec = group[1], group[2]
        elif len(group) == 4:
            # (kind, count_min, count_max, radius) OR (kind, count, radius_min, radius_max)
            # Disambiguate by type of the middle fields.
            if isinstance(group[1], (tuple, list)) or isinstance(group[2], (tuple, list)):
                count_spec, radius_spec = group[1], (group[2], group[3]) if not isinstance(group[3], (tuple, list)) else group[3]
            else:
                # both ints: treat as count range
                count_spec = (group[1], group[2])
                radius_spec = group[3]
        elif len(group) >= 5:
            count_spec = (group[1], group[2])
            radius_spec = (group[3], group[4])
        else:
            continue
        try:
            if isinstance(count_spec, (tuple, list)):
                count = rng.randint(int(count_spec[0]), int(count_spec[1]))
            else:
                count = int(count_spec)
        except (TypeError, ValueError):
            continue
        try:
            if isinstance(radius_spec, (tuple, list)):
                radius = rng.uniform(float(radius_spec[0]), float(radius_spec[1]))
            else:
                radius = float(radius_spec)
        except (TypeError, ValueError):
            continue
        margin = radius + preset.edge_margin
        if margin >= config.WORLD_HALF_W or margin >= config.WORLD_HALF_H:
            continue  # cannot fit a disc of this size in the world
        for _ in range(int(count)):
            placed_one = False
            for _ in range(preset.max_place_attempts):
                center = _rand_point(rng, margin)
                if _pickup_ok(center, radius, segments, start, target, peers, preset):
                    peers.append((center, radius))
                    out.append(PickupSpec(center=center, radius=radius, kind=kind))
                    placed_one = True
                    break
            if not placed_one:
                break  # too crowded: fewer (or zero) pickups is fine
    return tuple(out)


def place_holes(rng, segments, start, target, placed=(), preset=None):
    preset = _preset_or_default(preset)
    n = preset.num_holes or preset.num_wormholes or preset.num_portals
    n = int(n or 0)

    out = []
    placed = list(placed or [])
    r = 0.5
    gap = 0.2

    # 起點與終點的安全距離
    start_clearance = preset.start_clearance
    target_clearance = preset.target_radius + preset.target_clearance

    for _ in range(n):
        for _attempt in range(preset.max_place_attempts):
            seg = rng.choice(segments) if segments else (start, target)
            a, b = seg
            t = rng.random()

            black = (
                a[0] + (b[0] - a[0]) * t,
                a[1] + (b[1] - a[1]) * t,
            )
            white = _rand_point(rng, preset.edge_margin)

            # 1. Hole 不得與起點或終點重疊
            if math.dist(black, start) <= r + start_clearance:
                continue
            if math.dist(white, start) <= r + start_clearance:
                continue

            if math.dist(black, target) <= r + target_clearance:
                continue
            if math.dist(white, target) <= r + target_clearance:
                continue

            # 2. 黑白端點不得與既有物件重疊
            if any(
                math.dist(center, point) <= radius + r + gap
                for center, radius in placed
                for point in (black, white)
            ):
                continue

            # 3. 同一組黑白端點不得互相重疊
            if math.dist(black, white) <= 2 * r + gap:
                continue

            out.append((black, white, r))
            placed.extend(((black, r), (white, r)))
            break

    return tuple(out)


__all__ = [
    "PlaceContext", "COMMON_RULES", "OBSTACLE_ONLY_RULES", "OBSTACLE_RULES",
    "_rand_point", "_preset_or_default", "sample_endpoints",
    "sample_hidden_points", "build_corridor", "rule_clear_of_endpoints",
    "rule_direct_blockers", "rule_clear_of_corridor",
    "rule_spaced_from_peers", "rule_pickup_on_corridor", "_obstacle_ok",
    "_obstacle_count", "place_obstacles", "_pickup_ok", "place_pickups",
    "place_holes",
]
