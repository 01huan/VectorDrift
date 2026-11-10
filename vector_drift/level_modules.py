"""Procedural generation modules for the random drift levels.

Every module builds a :class:`GeneratedLayout`: the frozen ``LevelSpec`` plus
the data the validator needs (the intended flight route, its legs, the
required pickups and any teleports).  Modules are selected by the preset's
``generator`` field:

* ``"corridor"`` -- the original hidden-waypoint route (Random Drift I/II).
* ``"wormhole_network"`` -- sealed bumper walls; each gate is a black/white
  hole pair, so the level is only solvable by chaining the wormholes.
* ``"maze"`` -- a perfect maze (plus a braid of extra loops) whose walls are
  bumper rocks; the entrance and exit are the start and the target.
* ``"bomb"`` -- the target is sealed by a bumper ring that only a shockwave
  pickup can open; the shockwave is a required pickup.
* ``"extreme_time"`` -- a winding slalom against a very tight time limit, with
  extra-time pickups on the route.

Pure logic (no pygame); everything runs off the seeded ``rng`` so a seed always
reproduces the same layout.  Tunables live in ``level_presets.py``.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from . import config
from .data import HoleSpec, LevelSpec, ObstacleSpec, PickupSpec


@dataclass(frozen=True)
class GeneratedLayout:
    """One generated level plus the metadata the validator needs."""

    level: LevelSpec
    module: str
    route: tuple                 # flight waypoints, in traversal order
    segments: tuple              # the individual flight legs ((a, b), ...)
    required_pickups: tuple = ()  # pickup kinds the route must collect
    teleports: tuple = ()        # (black, white) hole pairs used by the route
    walls: tuple = ()            # (axis, fixed, lo, hi) wormhole gates


# --------------------------------------------------------------- helpers
def _clamp(value, lo, hi):
    return max(lo, min(hi, value))


def _rand_point(rng, margin):
    x = rng.uniform(-config.WORLD_HALF_W + margin, config.WORLD_HALF_W - margin)
    y = rng.uniform(-config.WORLD_HALF_H + margin, config.WORLD_HALF_H - margin)
    return (x, y)


def _peers(obstacles):
    return [(o.center, o.radius) for o in obstacles]


def _choose_template(preset, rng):
    from .random_level import _choose_template as _pick
    return _pick(preset, rng)


# ------------------------------------------------------------- corridor
def generate_corridor_layout(rng, preset):
    """Original hidden-waypoint corridor builder (Random Drift I/II)."""
    from . import random_level as rl

    start, target = rl.sample_endpoints(rng, preset)
    hidden = rl.sample_hidden_points(rng, preset=preset)
    ordered, segments = rl.build_corridor(start, hidden, target, rng)
    obstacles = rl.place_obstacles(rng, segments, start, target, preset=preset)
    pickups = rl.place_pickups(rng, segments, start, target,
                               placed=_peers(obstacles), preset=preset)
    peers = _peers(obstacles) + [(p.center, p.radius) for p in pickups]
    holes = rl.place_holes(rng, segments, start, target, placed=peers,
                           preset=preset)
    level = rl._make_spec(start, target, obstacles, preset, pickups, holes)
    return GeneratedLayout(
        level=level,
        module="corridor",
        route=tuple(ordered),
        segments=tuple((tuple(a), tuple(b)) for a, b in segments),
        required_pickups=tuple(getattr(preset, "required_pickup_kinds", ())),
    )


# ------------------------------------------------------- extreme time
def _slalom_route(start, target, count, rng):
    """A winding route: waypoints alternate on either side of the
    start -> target line, forcing sharp turns."""
    sx, sy = start
    tx, ty = target
    dx, dy = tx - sx, ty - sy
    dist = math.hypot(dx, dy) or 1.0
    ux, uy = dx / dist, dy / dist
    px_, py_ = -uy, ux
    amp = min(2.2, dist * 0.16)
    points = [start]
    for i in range(1, count + 1):
        t = i / (count + 1)
        side = 1.0 if i % 2 else -1.0
        offset = side * amp * rng.uniform(0.75, 1.0)
        x = _clamp(sx + dx * t + px_ * offset,
                   -config.WORLD_HALF_W + 0.6, config.WORLD_HALF_W - 0.6)
        y = _clamp(sy + dy * t + py_ * offset,
                   -config.WORLD_HALF_H + 0.6, config.WORLD_HALF_H - 0.6)
        points.append((x, y))
    points.append(target)
    return points


def generate_extreme_time_layout(rng, preset):
    """The corridor builder tuned to a tight slalom: sharp turns, extra-time
    pickups on the route and a very short time limit."""
    from . import random_level as rl

    start, target = rl.sample_endpoints(rng, preset)
    count = preset.num_hidden_points or 5
    route = tuple(_slalom_route(start, target, count, rng))
    segments = tuple(zip(route[:-1], route[1:]))
    obstacles = rl.place_obstacles(rng, segments, start, target, preset=preset)
    pickups = rl.place_pickups(rng, segments, start, target,
                               placed=_peers(obstacles), preset=preset)
    peers = _peers(obstacles) + [(p.center, p.radius) for p in pickups]
    holes = rl.place_holes(rng, segments, start, target, placed=peers,
                           preset=preset)
    level = rl._make_spec(start, target, obstacles, preset, pickups, holes)
    return GeneratedLayout(
        level=level,
        module="extreme_time",
        route=route,
        segments=segments,
        required_pickups=tuple(getattr(preset, "required_pickup_kinds", ())),
    )


# -------------------------------------------------------- wormhole network
def _sample_horizontal(rng, preset):
    """Endpoints split along x so vertical wormhole gates fit between them."""
    best = None
    for _ in range(preset.max_endpoint_attempts):
        start = _rand_point(rng, preset.endpoint_margin)
        target = _rand_point(rng, preset.endpoint_margin)
        span = abs(target[0] - start[0])
        if span >= preset.min_start_target_dist:
            return start, target
        if best is None or span > abs(best[1][0] - best[0][0]):
            best = (start, target)
    start, target = best
    if abs(target[0] - start[0]) < 9.6:
        start, target = (-8.5, 0.0), (8.5, 0.0)   # guaranteed split fallback
    if start[0] > target[0]:
        start, target = target, start
    return start, target


def generate_wormhole_network_layout(rng, preset):
    """Sealed bumper walls crossed only by chained black/white hole pairs."""
    from . import random_level as rl

    start, target = _sample_horizontal(rng, preset)
    sx, sy = start
    tx, ty = target
    span = tx - sx
    if abs(span) >= 13.0:
        n_walls = 3
    elif abs(span) >= 9.6:
        n_walls = 2
    else:
        n_walls = 1
    spacing = abs(span) / (n_walls + 1)
    direction = 1.0 if span >= 0 else -1.0
    offset = _clamp(0.30 * spacing, 1.35, 0.38 * spacing)

    walls = [sx + span * (k + 1) / (n_walls + 1) for k in range(n_walls)]
    wall_obstacles = []
    wall_r = 0.72
    wall_gap = 1.28   # < 2 * (0.72 + hull): walls are sealed
    for wx in walls:
        y = -config.WORLD_HALF_H
        end = config.WORLD_HALF_H
        while y < end - 1e-9:
            wall_obstacles.append(ObstacleSpec(center=(wx, y), radius=wall_r,
                                               restitution=preset.restitution))
            y += wall_gap
        wall_obstacles.append(ObstacleSpec(center=(wx, end), radius=wall_r,
                                           restitution=preset.restitution))

    holes = []
    route = [start]
    for i, wx in enumerate(walls):
        black_y = _clamp(sy + (ty - sy) * (i + 1) / (n_walls + 1)
                         + rng.uniform(-1.4, 1.4), -6.6, 6.6)
        offset_y = rng.uniform(1.8, 3.4) * rng.choice((-1.0, 1.0))
        white_y = _clamp(black_y + offset_y, -6.6, 6.6)
        if abs(white_y - black_y) < 1.0:
            white_y = _clamp(black_y - 2.0 * (1.0 if black_y >= 0.0 else -1.0),
                             -6.6, 6.6)
        black = (wx - direction * offset, black_y)
        white = (wx + direction * offset, white_y)
        holes.append(HoleSpec(black, white, radius=0.5))
        route.append(black)
        route.append(white)
    route.append(target)

    # Flight legs (the teleports themselves are not flown).
    legs = [(start, holes[0].black_center)]
    for i in range(len(holes) - 1):
        legs.append((holes[i].white_center, holes[i + 1].black_center))
    legs.append((holes[-1].white_center, target))
    segments = tuple(legs)

    # A few free rocks that avoid the flight legs, to keep the wild feel.
    peers = _peers(wall_obstacles)
    peers.extend((h.black_center, h.radius) for h in holes)
    peers.extend((h.white_center, h.radius) for h in holes)
    extra = rl.place_obstacles(rng, segments, start, target, preset=preset,
                               placed=peers)
    obstacles = tuple(wall_obstacles) + tuple(extra)

    peers = _peers(obstacles)
    peers.extend((h.black_center, h.radius) for h in holes)
    peers.extend((h.white_center, h.radius) for h in holes)
    pickups = rl.place_pickups(rng, segments, start, target, placed=peers,
                               preset=preset)

    level = rl._make_spec(start, target, obstacles, preset, pickups,
                           tuple(holes))
    wall_specs = tuple(("v", wx, -config.WORLD_HALF_H, config.WORLD_HALF_H)
                       for wx in walls)
    return GeneratedLayout(
        level=level,
        module="wormhole_network",
        route=tuple(route),
        segments=segments,
        required_pickups=tuple(getattr(preset, "required_pickup_kinds", ())),
        teleports=tuple((h.black_center, h.white_center) for h in holes),
        walls=wall_specs,
    )


# ----------------------------------------------------------------- maze
def _cell_center(col, row, cell, x0, y0):
    return (x0 + (col + 0.5) * cell, y0 + (row + 0.5) * cell)


def generate_maze_layout(rng, preset):
    """A sealed maze: bumper rocks along every wall, one guaranteed route."""
    cell = 3.0
    cols, rows = 6, 5
    x0 = -cell * cols / 2.0
    y0 = -cell * rows / 2.0

    # Randomized depth-first search (perfect maze) over the cell grid.
    walls_v = {(i, j) for i in range(1, cols) for j in range(rows)}   # (col, row) left of cell (i, j)
    walls_h = {(i, j) for i in range(cols) for j in range(1, rows)}   # (col, row) below cell (i, j)
    visited = {(0, 0)}
    stack = [(0, 0)]
    while stack:
        col, row = stack[-1]
        neighbours = []
        if col > 0 and (col - 1, row) not in visited:
            neighbours.append((col - 1, row, "v", (col, row)))
        if col < cols - 1 and (col + 1, row) not in visited:
            neighbours.append((col + 1, row, "v", (col + 1, row)))
        if row > 0 and (col, row - 1) not in visited:
            neighbours.append((col, row - 1, "h", (col, row)))
        if row < rows - 1 and (col, row + 1) not in visited:
            neighbours.append((col, row + 1, "h", (col, row + 1)))
        if not neighbours:
            stack.pop()
            continue
        ncol, nrow, axis, wall = rng.choice(neighbours)
        if axis == "v":
            walls_v.discard(wall)
        else:
            walls_h.discard(wall)
        visited.add((ncol, nrow))
        stack.append((ncol, nrow))

    # Braid: knock out a few extra walls so the maze has loops (it is far more
    # forgiving than a single dead-end corridor, but no less sealed).
    rest_v = sorted(walls_v)
    rest_h = sorted(walls_h)
    rng.shuffle(rest_v)
    rng.shuffle(rest_h)
    for wall in rest_v[:max(1, len(rest_v) // 5)]:
        walls_v.discard(wall)
    for wall in rest_h[:max(1, len(rest_h) // 5)]:
        walls_h.discard(wall)

    # Shortest path entrance -> exit (BFS, deterministic order).
    def neighbours_of(cell_key):
        col, row = cell_key
        out = []
        if (col, row) not in walls_v:
            if col > 0:
                out.append((col - 1, row))
        if (col + 1, row) not in walls_v:
            if col < cols - 1:
                out.append((col + 1, row))
        if (col, row) not in walls_h:
            if row > 0:
                out.append((col, row - 1))
        if (col, row + 1) not in walls_h:
            if row < rows - 1:
                out.append((col, row + 1))
        return out

    from collections import deque

    prev = {(0, 0): None}
    queue = deque([(0, 0)])
    goal = (cols - 1, rows - 1)
    while queue:
        cur = queue.popleft()
        if cur == goal:
            break
        for nxt in neighbours_of(cur):
            if nxt not in prev:
                prev[nxt] = cur
                queue.append(nxt)
    if goal not in prev:
        raise RuntimeError("maze generation produced an unsolvable layout")
    path = []
    cur = goal
    while cur is not None:
        path.append(cur)
        cur = prev[cur]
    path.reverse()
    route = tuple(_cell_center(col, row, cell, x0, y0) for col, row in path)
    segments = tuple(zip(route[:-1], route[1:]))

    # Bumper rocks along every wall segment (gap < ship diameter -> sealed).
    wall_r = 0.6
    step = 1.3
    obstacles = []

    def _discs_along(axis, fixed, lo, hi):
        positions = []
        t = 0.0
        while t <= hi - lo:
            positions.append(t)
            t += step
        if hi - lo - (positions[-1] if positions else 0.0) > 0.8:
            positions.append(hi - lo)
        for t in positions:
            if axis == "v":
                center = (fixed, lo + t)
            else:
                center = (lo + t, fixed)
            obstacles.append(ObstacleSpec(center=center, radius=wall_r,
                                          restitution=preset.restitution))

    for i, j in sorted(walls_v):
        wx = x0 + i * cell
        _discs_along("v", wx, y0 + j * cell, y0 + (j + 1) * cell)
    for i, j in sorted(walls_h):
        wy = y0 + j * cell
        _discs_along("h", wy, x0 + i * cell, x0 + (i + 1) * cell)
    # Perimeter: the y edges are the world bound; seal the x edges with walls.
    _discs_along("v", x0, y0, y0 + rows * cell)
    _discs_along("v", x0 + cols * cell, y0, y0 + rows * cell)

    start = _cell_center(0, 0, cell, x0, y0)
    target = _cell_center(cols - 1, rows - 1, cell, x0, y0)

    from . import random_level as rl

    peers = _peers(obstacles)
    pickups = rl.place_pickups(rng, segments, start, target, placed=peers,
                               preset=preset)
    level = rl._make_spec(start, target, tuple(obstacles), preset, pickups, ())
    return GeneratedLayout(
        level=level,
        module="maze",
        route=route,
        segments=segments,
        required_pickups=tuple(getattr(preset, "required_pickup_kinds", ())),
    )


# ----------------------------------------------------------------- bomb
def _sample_bomb_endpoints(rng, preset):
    """Sample (start, target) with the target central enough that the whole
    blast ring stays inside the world."""
    best = None
    for _ in range(preset.max_endpoint_attempts * 2):
        target = (rng.uniform(-5.5, 5.5), rng.uniform(-3.0, 3.0))
        start = _rand_point(rng, preset.endpoint_margin)
        span = math.dist(start, target)
        if span >= preset.min_start_target_dist:
            return start, target
        if best is None or span > math.dist(best[0], best[1]):
            best = (start, target)
    start, target = best
    if math.dist(start, target) < preset.min_start_target_dist:
        start, target = (-8.5, 0.0), (5.0, 0.0)
    return start, target


def generate_bomb_layout(rng, preset):
    """The target sealed by a bumper ring; a shockwave pickup opens it."""
    from . import random_level as rl

    start, target = _sample_bomb_endpoints(rng, preset)
    dist = math.dist(start, target) or 1.0
    ux, uy = (target[0] - start[0]) / dist, (target[1] - start[1]) / dist
    perp = (-uy, ux)

    ring_r = rng.uniform(2.7, 3.5)
    rock_r = 0.75
    count = max(9, math.ceil(2 * math.pi * ring_r / 1.35))
    obstacles = []
    for k in range(count):
        angle = 2 * math.pi * k / count + rng.uniform(-0.12, 0.12)
        center = (target[0] + ring_r * math.cos(angle),
                  target[1] + ring_r * math.sin(angle))
        obstacles.append(ObstacleSpec(center=center, radius=rock_r,
                                      restitution=preset.restitution))

    # Shockwave pickup on the way in, just outside the ring.
    reach = ring_r + 2.4
    jitter = rng.uniform(-1.3, 1.3)
    shock_center = (target[0] - ux * reach + perp[0] * jitter,
                    target[1] - uy * reach + perp[1] * jitter)
    pickups = [PickupSpec(center=shock_center, radius=0.5, kind="shockwave")]

    # Scatter a few rocks away from the route for texture.
    route = (start, shock_center, target)
    segments = ((start, shock_center), (shock_center, target))
    peers = _peers(obstacles) + [(shock_center, 0.5)]
    extra = rl.place_obstacles(rng, (segments[0],), start, target,
                               preset=preset, placed=peers)
    obstacles.extend(extra)

    peers = _peers(obstacles) + [(p.center, p.radius) for p in pickups]
    # Extra pickups only on the start -> shockwave leg (inside the ring is a
    # dead zone until the ring is blasted).
    extra_pickups = rl.place_pickups(rng, (segments[0],), start, target,
                                     placed=peers, preset=preset)
    pickups.extend(extra_pickups)

    level = rl._make_spec(start, target, tuple(obstacles), preset,
                           tuple(pickups), ())
    return GeneratedLayout(
        level=level,
        module="bomb",
        route=route,
        segments=segments,
        required_pickups=("shockwave",),
    )


# ------------------------------------------------------------- dispatch
GENERATORS = {
    "corridor": generate_corridor_layout,
    "extreme_time": generate_extreme_time_layout,
    "wormhole_network": generate_wormhole_network_layout,
    "maze": generate_maze_layout,
    "bomb": generate_bomb_layout,
}


def generate_layout(seed, preset):
    """Build one layout for ``preset`` (after its template is chosen).

    Applies the module's own retry policy and falls back to an obstacle-free
    layout when the attempts are exhausted, so callers always get a level.
    """
    rng = random.Random(seed)
    preset = _choose_template(preset, rng)
    module = getattr(preset, "generator", "corridor")
    generator = GENERATORS.get(module)
    if generator is None:
        raise ValueError(f"Unknown level generator module {module!r}")

    for _ in range(max(1, preset.max_level_attempts)):
        try:
            layout = generator(rng, preset)
        except RuntimeError:
            continue
        if layout is not None:
            return layout

    from . import random_level as rl

    # Last resort: an obstacle-free corridor is always solvable.
    fallback_seed = random.Random(rng.random()).randrange(2 ** 31)
    start, target = rl.sample_endpoints(random.Random(fallback_seed), preset)
    level = rl._make_spec(start, target, (), preset)
    return GeneratedLayout(
        level=level,
        module=module,
        route=(start, target),
        segments=((start, target),),
        required_pickups=tuple(getattr(preset, "required_pickup_kinds", ())),
    )


def known_modules():
    return tuple(GENERATORS)
