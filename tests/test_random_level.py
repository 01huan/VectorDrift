"""Tests for presets, rules, and Level 8 (extensibility)."""

import math
from dataclasses import replace

from vector_drift import config
from vector_drift.data import get_level
from vector_drift.level_presets import (
    PRESET_8,
    RandomPreset,
    dynamic_ids,
    get_preset,
    is_dynamic_level,
    register_preset,
)
from vector_drift.physics import segment_hits_circle
from vector_drift.random_level import (
    OBSTACLE_RULES,
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
            >= min(t.min_start_target_dist for t in PRESET_8.templates)
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
            min(t.corridor_clearance for t in PRESET_8.templates) - 1e-9
        )


def test_counts_radii_and_world_bounds():
    corridor_templates = [t for t in PRESET_8.templates if t.generator == "corridor"]
    for seed in range(20):
        level, report = generate_random_level(seed=seed, return_report=True)
        if report.generator == "corridor":
            assert any(
                template.num_obstacles_min <= len(level.obstacles) <= template.num_obstacles_max
                for template in corridor_templates
                if template.num_obstacles_min is not None
            )
        for ob in level.obstacles:
            x, y = ob.center
            # Obstacles may stick out past the world edge (like the fixed
            # levels' side-poking rocks) but must overlap the world.
            assert abs(x) < config.WORLD_HALF_W + ob.radius
            assert abs(y) < config.WORLD_HALF_H + ob.radius


def test_same_seed_same_layout_via_get_level():
    a = get_level(8, seed=123)
    b = get_level(8, seed=123)
    assert a.start == b.start
    assert a.target_center == b.target_center
    assert [(o.center, o.radius) for o in a.obstacles] == [
        (o.center, o.radius) for o in b.obstacles
    ]


def test_level_spec_fields():
    level = generate_random_level(seed=7)
    assert level.id == PRESET_8.level_id
    assert level.name == PRESET_8.name
    assert any(
        (level.ship_id, level.target_radius, level.time_limit, level.lives)
        == (template.ship_id, template.target_radius, template.time_limit, template.lives)
        for template in PRESET_8.templates
    )


def test_random_level_selects_one_complete_template_per_generation():
    templates = (
        RandomPreset(
            level_id=98,
            name="Pickup template",
            time_limit=11.0,
            lives=2,
            num_obstacles=0,
            num_hidden_points=1,
            num_direct_blockers=0,
            pickup_groups=(("life", 1, 0.1),),
        ),
        RandomPreset(
            level_id=98,
            name="Empty template",
            time_limit=17.0,
            lives=4,
            num_obstacles=1,
            num_hidden_points=1,
            num_direct_blockers=0,
            pickup_groups=(),
        ),
    )
    preset = RandomPreset(
        level_id=98,
        name="Multi-template level",
        templates=templates,
    )

    outcomes = set()
    for seed in range(20):
        level = generate_random_level(98, seed=seed, preset=preset)
        again = generate_random_level(98, seed=seed, preset=preset)
        assert level == again
        assert level.id == preset.level_id
        assert level.name == preset.name

        outcome = (
            level.time_limit,
            level.lives,
            len(level.obstacles),
            tuple(p.kind for p in level.pickups),
        )
        outcomes.add(outcome)
        if level.lives == 2:
            assert level.time_limit == 11.0
            assert level.obstacles == ()
            assert tuple(p.kind for p in level.pickups) == ("life",)
        else:
            assert level.lives == 4
            assert level.time_limit == 17.0
            assert len(level.obstacles) == 1
            assert level.pickups == ()

    assert outcomes == {(11.0, 2, 0, ("life",)), (17.0, 4, 1, ())}


# --- extensibility: presets / Level 8 / custom rules -------------------

def test_dynamic_registry_contains_merged_level_8_only():
    assert dynamic_ids() == (8,)
    assert not is_dynamic_level(7) and is_dynamic_level(8)
    assert not is_dynamic_level(1)


def test_level8_contains_the_original_corridor_templates():
    generators = [t.generator for t in get_preset(8).templates]
    assert generators.count("corridor") == 2
    assert set(generators) == {"corridor", "wormhole_network", "maze",
                               "bomb", "extreme_time"}
    p7, p8 = [t for t in get_preset(8).templates if t.generator == "corridor"]
    assert (p8.num_obstacles, p8.target_radius) != (p7.num_obstacles, p7.target_radius)
    lv8 = generate_random_level(8, seed=7)
    assert lv8.id == 8
    assert lv8.name == PRESET_8.name


def test_level8_ships_all_modules():
    generators = {t.generator for t in get_preset(8).templates}
    assert generators == {"corridor", "wormhole_network", "maze",
                          "bomb", "extreme_time"}


def test_level8_layout_respects_own_preset():
    preset = get_preset(8)
    corridor = [t for t in preset.templates if t.generator == "corridor"]
    assert corridor
    for template in corridor:
        single_template_preset = replace(preset, templates=(template,))
        for seed in range(5):
            level, _, segments = generate_with_corridor(
                seed=seed, level_id=8, preset=single_template_preset
            )
            assert template.num_obstacles_min <= len(level.obstacles) <= template.num_obstacles_max
            for ob in level.obstacles:
                assert template.obstacle_radius_min <= ob.radius <= template.obstacle_radius_max
                gap = min(_seg_dist(ob.center, a, b) for a, b in segments)
                assert gap - ob.radius >= template.corridor_clearance - 1e-9
            blockers = [o for o in level.obstacles
                        if segment_hits_circle(level.start, level.target_center,
                                               o.center, o.radius)]
            assert len(blockers) >= template.num_direct_blockers


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
        assert len(OBSTACLE_RULES) == 4
    finally:
        from vector_drift.level_presets import PRESETS
        PRESETS.pop(99, None)
    assert not is_dynamic_level(99)
