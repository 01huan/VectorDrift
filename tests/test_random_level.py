"""Tests for presets, rules, and Level 8 (extensibility)."""

import math

from vector_drift import config
from vector_drift.data import get_level
from vector_drift.level_presets import (
    PRESET_7,
    RandomPreset,
    dynamic_ids,
    get_preset,
    is_dynamic_level,
    register_preset,
)
from vector_drift.physics import segment_hits_circle
from vector_drift.random_level import (
    RULES,
    generate_random_level,
    generate_with_corridor,
    rule_direct_blockers,
)


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
            >= PRESET_7.min_start_target_dist
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
            PRESET_7.corridor_clearance - 1e-9
        )


def test_counts_radii_and_world_bounds():
    for seed in range(20):
        level = generate_random_level(seed=seed)
        assert len(level.obstacles) == PRESET_7.num_obstacles
        for ob in level.obstacles:
            assert (
                PRESET_7.obstacle_radius_min
                <= ob.radius
                <= PRESET_7.obstacle_radius_max
            )
            x, y = ob.center
            assert abs(x) + ob.radius <= config.WORLD_HALF_W + 1e-9
            assert abs(y) + ob.radius <= config.WORLD_HALF_H + 1e-9


def test_same_seed_same_layout_via_get_level():
    a = get_level(7, seed=123)
    b = get_level(7, seed=123)
    assert a.start == b.start
    assert a.target_center == b.target_center
    assert [(o.center, o.radius) for o in a.obstacles] == [
        (o.center, o.radius) for o in b.obstacles
    ]


def test_level_spec_fields():
    level = generate_random_level(seed=7)
    assert level.id == PRESET_7.level_id
    assert level.name == PRESET_7.name
    assert level.ship_id == PRESET_7.ship_id
    assert level.target_radius == PRESET_7.target_radius
    assert level.time_limit == PRESET_7.time_limit
    assert level.lives == PRESET_7.lives


# --- extensibility: presets / Level 8 / custom rules -------------------

def test_dynamic_registry_covers_7_and_8():
    assert 7 in dynamic_ids() and 8 in dynamic_ids()
    assert is_dynamic_level(7) and is_dynamic_level(8)
    assert not is_dynamic_level(1)


def test_level8_differs_from_level7_by_preset():
    p7, p8 = get_preset(7), get_preset(8)
    assert (p8.num_obstacles, p8.target_radius) != (p7.num_obstacles, p7.target_radius)
    lv8 = generate_random_level(8, seed=7)
    assert lv8.id == 8 and len(lv8.obstacles) == p8.num_obstacles


def test_level8_layout_respects_own_preset():
    preset = get_preset(8)
    for seed in range(5):
        level, _, segments = generate_with_corridor(seed=seed, level_id=8)
        assert len(level.obstacles) == preset.num_obstacles
        for ob in level.obstacles:
            assert preset.obstacle_radius_min <= ob.radius <= preset.obstacle_radius_max
            gap = min(_seg_dist(ob.center, a, b) for a, b in segments)
            assert gap - ob.radius >= preset.corridor_clearance - 1e-9
        blockers = [o for o in level.obstacles
                    if segment_hits_circle(level.start, level.target_center,
                                           o.center, o.radius)]
        assert len(blockers) >= preset.num_direct_blockers


def test_custom_preset_and_extra_rule_without_core_edits():
    def forbid_top_half(ctx):
        return ctx.center[1] <= 0.0  # y <= 0 only

    custom = RandomPreset(level_id=99, name="Custom", num_obstacles=4,
                          num_direct_blockers=0, extra_rules=(forbid_top_half,))
    register_preset(custom)
    try:
        assert is_dynamic_level(99)
        level = get_level(99, seed=3)
        assert level.id == 99 and len(level.obstacles) == 4
        assert all(o.center[1] <= 0.0 + 1e-9 for o in level.obstacles)
        # Rule pipeline is data: num_direct_blockers=0 disables the blocker rule.
        assert len(RULES) == 4
    finally:
        from vector_drift.level_presets import PRESETS
        PRESETS.pop(99, None)
    assert not is_dynamic_level(99)
