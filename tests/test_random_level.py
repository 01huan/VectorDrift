"""Tests for the Level 7 random solvable level generator."""

import math

from vector_drift import config
from vector_drift.data import get_level
from vector_drift.physics import segment_hits_circle
from vector_drift.random_level import generate_random_level, generate_with_corridor


def _seg_dist(p, a, b):
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    denom = dx * dx + dy * dy
    t = 0.0 if denom <= 0 else ((p[0] - ax) * dx + (p[1] - ay) * dy) / denom
    t = max(0.0, min(1.0, t))
    return math.dist(p, (ax + dx * t, ay + dy * t))


def corridor_clearance(level, segments):
    """Largest corridor half-width the layout actually keeps (m)."""
    worst = float("inf")
    for ob in level.obstacles:
        gap = min(_seg_dist(ob.center, a, b) for a, b in segments)
        worst = min(worst, gap - ob.radius)
    return worst


def test_endpoints_keep_distance_L():
    for seed in range(20):
        level = generate_random_level(seed=seed)
        assert (
            math.dist(level.start, level.target_center)
            >= config.RANDOM_LEVEL_MIN_START_TARGET_DIST
        )


def test_obstacles_avoid_segments_not_infinite_lines():
    # A disc beyond a segment's endpoint must NOT count as blocking:
    # segment (not infinite line) vs circle keeps levels solvable yet dense.
    assert not segment_hits_circle((0, 0), (2, 0), (4, 0), 1.0)
    for seed in range(20):
        level, _, segments = generate_with_corridor(seed=seed)
        for ob in level.obstacles:
            assert not any(
                segment_hits_circle(a, b, ob.center, ob.radius) for a, b in segments
            )


def test_corridor_keeps_configured_clearance():
    for seed in range(20):
        level, _, segments = generate_with_corridor(seed=seed)
        assert corridor_clearance(level, segments) >= (
            config.RANDOM_LEVEL_CORRIDOR_CLEARANCE - 1e-9
        )


def test_counts_radii_and_world_bounds():
    for seed in range(20):
        level = generate_random_level(seed=seed)
        assert len(level.obstacles) == config.RANDOM_LEVEL_NUM_OBSTACLES
        for ob in level.obstacles:
            assert (
                config.RANDOM_LEVEL_OBSTACLE_RADIUS_MIN
                <= ob.radius
                <= config.RANDOM_LEVEL_OBSTACLE_RADIUS_MAX
            )
            x, y = ob.center
            assert abs(x) + ob.radius <= config.WORLD_HALF_W + 1e-9
            assert abs(y) + ob.radius <= config.WORLD_HALF_H + 1e-9


def test_same_seed_same_layout_via_get_level():
    a = get_level(config.RANDOM_LEVEL_ID, seed=123)
    b = get_level(config.RANDOM_LEVEL_ID, seed=123)
    assert a.start == b.start
    assert a.target_center == b.target_center
    assert [(o.center, o.radius) for o in a.obstacles] == [
        (o.center, o.radius) for o in b.obstacles
    ]


def test_level_spec_fields():
    level = generate_random_level(seed=7)
    assert level.id == config.RANDOM_LEVEL_ID
    assert level.name == config.RANDOM_LEVEL_NAME
    assert level.ship_id == config.RANDOM_LEVEL_SHIP_ID
    assert level.target_radius == config.RANDOM_LEVEL_TARGET_RADIUS
    assert level.time_limit == config.RANDOM_LEVEL_TIME_LIMIT
    assert level.lives == config.RANDOM_LEVEL_LIVES
