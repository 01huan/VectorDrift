"""Random solvable level generator (Level 7).

Strategy (guaranteed solvable by construction):

1. Sample start/target with minimum separation L.
2. Sample K hidden waypoints, shuffle and join
   start -> hidden... -> target with straight segments. This polyline
   is the hidden safe corridor: a path always exists by construction.
3. Sample n circular obstacles with random radii, rejecting any disc
   that touches the corridor. The test is segment-vs-circle (not an
   infinite line), so obstacles may sit beyond segment endpoints.

Pure logic (no pygame); tunables live in config under RANDOM_LEVEL_*.
Pass ``seed`` for deterministic output in tests.
"""

import math
import random

from . import config
from .data import LevelSpec, ObstacleSpec
from .physics import segment_hits_circle


def _rand_point(rng, margin):
    """Uniform point inside the world rect shrunk by ``margin``."""
    x = rng.uniform(-config.WORLD_HALF_W + margin, config.WORLD_HALF_W - margin)
    y = rng.uniform(-config.WORLD_HALF_H + margin, config.WORLD_HALF_H - margin)
    return (x, y)


def sample_endpoints(rng):
    """Sample (start, target) with distance >= L."""
    for _ in range(config.RANDOM_LEVEL_MAX_ENDPOINT_ATTEMPTS):
        start = _rand_point(rng, config.RANDOM_LEVEL_ENDPOINT_MARGIN)
        target = _rand_point(rng, config.RANDOM_LEVEL_ENDPOINT_MARGIN)
        if math.dist(start, target) >= config.RANDOM_LEVEL_MIN_START_TARGET_DIST:
            return start, target
    raise RuntimeError("could not sample separated start/target")


def sample_hidden_points(rng, count=None):
    """Sample ``count`` hidden waypoints spread over the world."""
    count = config.RANDOM_LEVEL_NUM_HIDDEN_POINTS if count is None else count
    return [_rand_point(rng, config.RANDOM_LEVEL_HIDDEN_MARGIN) for _ in range(count)]


def build_corridor(start, hidden_points, target, rng):
    """Join start -> shuffled hidden points -> target; keep segments."""
    order = list(hidden_points)
    rng.shuffle(order)
    ordered = [start, *order, target]
    segments = list(zip(ordered[:-1], ordered[1:]))
    return ordered, segments


def _obstacle_ok(center, radius, segments, start, target, placed):
    """Check one candidate against corridor, endpoints and peers."""
    if math.dist(center, start) <= radius + config.RANDOM_LEVEL_START_CLEARANCE:
        return False
    if math.dist(center, target) <= (
        radius + config.RANDOM_LEVEL_TARGET_RADIUS + config.RANDOM_LEVEL_TARGET_CLEARANCE
    ):
        return False
    
    # -----------------------------------------------------------------
    # 【新增：防止直線通關機制】
    # 檢查這個障礙物是否「沒有」擋住起終點直線。
    # 為了逼玩家拐彎，我們希望前幾個障礙物「必須」去擋住起終點的直接連線！
    # 註：segment_hits_circle 的前兩個參數改成 start 和 target
    # -----------------------------------------------------------------
    # 這裡我們假設讓前 1 個障礙物（或更多）必須去卡住直線捷徑
    if len(placed) < 1:  
        # 如果這個隨機位置沒有擋住起終點直線，我們就拒絕它（重抽），直到抽到能擋住直線的為止
        if not segment_hits_circle(start, target, center, radius):
            return False
    # -----------------------------------------------------------------

    clearance = radius + config.RANDOM_LEVEL_CORRIDOR_CLEARANCE
    if any(segment_hits_circle(a, b, center, clearance) for a, b in segments):
        return False
    gap = config.RANDOM_LEVEL_MIN_OBSTACLE_GAP
    if any(math.dist(center, c) <= radius + r + gap for c, r in placed):
        return False
    return True



def place_obstacles(rng, segments, start, target, count=None):
    """Sample ``count`` non-blocking obstacles around the corridor."""
    count = config.RANDOM_LEVEL_NUM_OBSTACLES if count is None else count
    placed = []  # [(center, radius)]
    for _ in range(count):
        for _ in range(config.RANDOM_LEVEL_MAX_PLACE_ATTEMPTS):
            radius = rng.uniform(
                config.RANDOM_LEVEL_OBSTACLE_RADIUS_MIN,
                config.RANDOM_LEVEL_OBSTACLE_RADIUS_MAX,
            )
            margin = radius + config.RANDOM_LEVEL_EDGE_MARGIN
            if margin >= config.WORLD_HALF_W or margin >= config.WORLD_HALF_H:
                continue
            center = _rand_point(rng, margin)
            if _obstacle_ok(center, radius, segments, start, target, placed):
                placed.append((center, radius))
                break
        else:
            raise RuntimeError("could not place a non-blocking obstacle")
    return tuple(ObstacleSpec(center=center, radius=radius) for center, radius in placed)


def _make_spec(start, target, obstacles):
    return LevelSpec(
        id=config.RANDOM_LEVEL_ID,
        name=config.RANDOM_LEVEL_NAME,
        start=start,
        target_center=target,
        target_radius=config.RANDOM_LEVEL_TARGET_RADIUS,
        ship_id=config.RANDOM_LEVEL_SHIP_ID,
        time_limit=config.RANDOM_LEVEL_TIME_LIMIT,
        lives=config.RANDOM_LEVEL_LIVES,
        obstacles=obstacles,
    )


def generate_with_corridor(seed=None):
    """Build a level; also return hidden corridor (for tests/debug).

    Retries whole layouts a bounded number of times; as a last resort
    falls back to an obstacle-free (always solvable) layout.
    """
    rng = random.Random(seed)
    for _ in range(config.RANDOM_LEVEL_MAX_LEVEL_ATTEMPTS):
        try:
            start, target = sample_endpoints(rng)
            ordered, segments = build_corridor(
                start, sample_hidden_points(rng), target, rng
            )
            obstacles = place_obstacles(rng, segments, start, target)
            return _make_spec(start, target, obstacles), ordered, segments
        except RuntimeError:
            continue
    start, target = sample_endpoints(random.Random(rng.random()))
    return _make_spec(start, target, ()), [start, target], [(start, target)]


def generate_random_level(seed=None):
    """Generate the Level 7 random-but-solvable level."""
    level, _, _ = generate_with_corridor(seed=seed)
    return level
