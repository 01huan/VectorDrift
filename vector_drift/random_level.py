"""Random solvable level generator (dynamic levels: 7, 8, ...).

Strategy (guaranteed solvable by construction):

1. Sample start/target with minimum separation L.
2. Sample K hidden waypoints, shuffle and join
   start -> hidden... -> target with straight segments. This polyline
   is the hidden safe corridor: a path always exists by construction.
3. Sample n circular obstacles with random radii, rejecting any disc
   that violates a rule (see RULES below).
4. Sample m pickups ON the corridor (same center+radius shape as
   obstacles), rejecting any that stacks on an obstacle, peer pickup
   or endpoint. Tunables: RandomPreset.pickup_groups /
   pickup_corridor_max.

How to extend (no core edits needed):

* New random level (e.g. Level 9): add ``RandomPreset(level_id=9, ...)``
  in level_presets.py -- done. Different params, same generator.
* New obstacle flavour (e.g. kind="super"): add a renderer in
  ``sprites.OBSTACLE_RENDERERS`` and, only if placement must change,
  append a rule function to ``extra_rules`` of that preset.
* New placement constraint: write ``def my_rule(ctx) -> bool`` and either
  append to ``COMMON_RULES`` / ``OBSTACLE_ONLY_RULES`` (global) or to one
  preset's ``extra_rules``.

Pure logic (no pygame); tunables live in level_presets.py.
Pass ``seed`` for deterministic output in tests.
Backward compat: all public functions accept ``preset=None`` (defaults to
Level 7) and ``generate_random_level(seed=...)`` keyword style still works.
"""

import math
import random
from dataclasses import dataclass

from . import config
from .data import LevelSpec, ObstacleSpec
from .level_presets import get_preset
from .physics import segment_hits_circle


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


def _preset_or_default(preset=None, level_id=7):
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

# Backward-compat alias: existing tests / callers reference RULES.
RULES = OBSTACLE_RULES


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


def place_obstacles(rng, segments, start, target, count=None, preset=None):
    """Sample ``count`` non-blocking obstacles around the corridor."""
    preset = _preset_or_default(preset)
    count = _obstacle_count(preset, rng, count)
    placed = []  # [(center, radius)]
    for _ in range(count):
        for _ in range(preset.max_place_attempts):
            radius = rng.uniform(preset.obstacle_radius_min, preset.obstacle_radius_max)
            margin = radius + preset.edge_margin
            if margin >= config.WORLD_HALF_W or margin >= config.WORLD_HALF_H:
                continue
            center = _rand_point(rng, margin)
            if _obstacle_ok(center, radius, segments, start, target, placed, preset):
                placed.append((center, radius))
                break
        else:
            raise RuntimeError("could not place a non-blocking obstacle")
    return tuple(
        ObstacleSpec(center=center, radius=radius, restitution=preset.restitution,
                     kind=preset.obstacle_kind)
        for center, radius in placed
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
    for _ in range(n):
        for _attempt in range(preset.max_place_attempts):
            seg = rng.choice(segments) if segments else (start, target)
            a, b = seg
            t = rng.random()
            bx = a[0] + (b[0]-a[0])*t
            by = a[1] + (b[1]-a[1])*t
            black = (bx, by)
            white = _rand_point(rng, preset.edge_margin)
            r = 0.5
            # avoid overlaps with existing discs (obstacles/pickups/peers)
            ok = True
            for (pc, pr) in placed:
                if math.dist(pc, black) <= pr + r + 0.2:
                    ok = False
                    break
            if ok:
                for (pc, pr) in placed:
                    if math.dist(pc, white) <= pr + r + 0.2:
                        ok = False
                        break
            if ok:
                out.append((black, white, r))
                placed.append((black, r))
                placed.append((white, r))
                break
    return tuple(out)




def _make_spec(start, target, obstacles, preset=None, pickups=(), holes=()):
    preset = _preset_or_default(preset)
    from .data import HoleSpec
    hole_specs = []
    for h in (holes or ()):
        if isinstance(h, HoleSpec):
            hole_specs.append(h)
        elif isinstance(h, (tuple, list)):
            hole_specs.append(HoleSpec(black_center=h[0], white_center=h[1],
                                      radius=h[2] if len(h) > 2 else 0.5))
    return LevelSpec(
        id=preset.level_id,
        name=preset.name,
        start=start,
        target_center=target,
        target_radius=preset.target_radius,
        ship_id=preset.ship_id,
        time_limit=preset.time_limit,
        lives=preset.lives,
        obstacles=obstacles,
        pickups=pickups,
        holes=tuple(hole_specs),
    )


def generate_with_corridor(seed=None, level_id=7, preset=None):
    """Build a level; also return hidden corridor (for tests/debug).

    Retries whole layouts a bounded number of times; as a last resort
    falls back to an obstacle-free (always solvable) layout.
    """
    preset = _preset_or_default(preset, level_id)
    rng = random.Random(seed)
    for _ in range(preset.max_level_attempts):
        try:
            start, target = sample_endpoints(rng, preset)
            ordered, segments = build_corridor(
                start, sample_hidden_points(rng, preset=preset), target, rng
            )
            obstacles = place_obstacles(rng, segments, start, target, preset=preset)
            peers = [(o.center, o.radius) for o in obstacles]
            pickups = place_pickups(rng, segments, start, target, placed=peers,
                                    preset=preset)
            holes = place_holes(rng, segments, start, target, placed=peers, preset=preset)
            return _make_spec(start, target, obstacles, preset, pickups, holes), ordered, segments
        except RuntimeError:
            continue
    start, target = sample_endpoints(random.Random(rng.random()), preset)
    return _make_spec(start, target, (), preset), [start, target], [(start, target)]


def generate_random_level(level_id=7, seed=None, preset=None):
    """Generate a random-but-solvable level (default: Level 7).

    ``generate_random_level(seed=123)`` (old keyword style) still means
    Level 7 with that seed.
    """
    if isinstance(level_id, random.Random):
        raise TypeError("pass seed=..., not a Random instance")
    if preset is None and not isinstance(level_id, int):
        # Backward compat: generate_random_level(seed_value) -> Level 7.
        seed, level_id = level_id, 7
    preset = _preset_or_default(preset, level_id)
    level, _, _ = generate_with_corridor(seed=seed, preset=preset)
    return level
