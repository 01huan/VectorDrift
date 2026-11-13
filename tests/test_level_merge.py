"""The merged random level: 1..3 screens, chained by checkpoints."""

import math

from vector_drift.data import section_count, section_level, section_shift
from vector_drift.level_merge import (
    MAX_SECTIONS,
    choose_themes,
    combine_reports,
    generate_merged_layout,
)
from vector_drift.level_presets import PRESET_8, RandomPreset
from vector_drift.level_validator import validate_level
from vector_drift.random_level import generate_random_level


def _screens(level):
    """Every screen of a level, as plain one-screen levels."""
    return [section_level(level, k) for k in range(section_count(level))]


def test_a_random_level_has_one_to_three_screens():
    counts = set()
    for seed in range(30):
        level = generate_random_level(8, seed=seed, run_solver=False)
        counts.add(section_count(level))
    assert counts <= {1, 2, 3}
    assert 1 in counts, "a random level may be a single screen"
    assert len(counts) > 1, "the screens should vary from visit to visit"


def test_the_screens_use_different_themes():
    for seed in range(20):
        merged = generate_merged_layout(seed, PRESET_8)
        themes = [section.preset for section in merged.sections]
        assert len(set(themes)) == len(themes)


def test_the_same_seed_gives_the_same_merged_level():
    for seed in (3, 11, 42):
        first = generate_merged_layout(seed, PRESET_8)
        again = generate_merged_layout(seed, PRESET_8)
        assert first.level == again.level
        assert [section.layout.level for section in first.sections] == \
            [section.layout.level for section in again.sections]


def test_max_sections_is_respected():
    for seed in range(10):
        merged = generate_merged_layout(seed, PRESET_8, max_sections=1)
        assert len(merged.sections) == 1
        assert merged.level.sections == ()
    for seed in range(10):
        merged = generate_merged_layout(seed, PRESET_8, max_sections=2)
        assert len(merged.sections) <= 2


def test_choose_themes_never_repeats_a_theme():
    import random

    rng = random.Random(7)
    for _ in range(20):
        themes = choose_themes(PRESET_8, rng, max_sections=MAX_SECTIONS)
        assert 1 <= len(themes) <= MAX_SECTIONS
        assert len(set(themes)) == len(themes)
        assert set(themes) <= set(PRESET_8.templates)


def test_the_merged_level_mirrors_its_first_screen():
    for seed in range(20):
        level = generate_random_level(8, seed=seed, run_solver=False)
        screens = _screens(level)
        first = screens[0]
        assert level.id == PRESET_8.level_id
        assert level.name == PRESET_8.name
        assert level.start == first.start
        assert level.target_center == first.target_center
        assert level.target_radius == first.target_radius
        assert level.time_limit == first.time_limit
        assert level.obstacles == first.obstacles
        assert level.pickups == first.pickups
        assert level.holes == first.holes


def test_every_screen_but_the_last_ends_on_a_checkpoint():
    """The screens are chained: the camera pans from a checkpoint to the next."""
    for seed in range(20):
        level = generate_random_level(8, seed=seed, run_solver=False)
        screens = _screens(level)
        assert len(screens) == section_count(level)
        for k in range(len(screens) - 1):
            shift = section_shift(level, k)
            assert math.isfinite(shift[0]) and math.isfinite(shift[1])
            # The next screen starts where the checkpoint is: the ship
            # continues from the checkpoint it just reached.
            here, there = screens[k], screens[k + 1]
            assert shift == (here.target_center[0] - there.start[0],
                             here.target_center[1] - there.start[1])


def test_every_screen_validates_on_its_own():
    for seed in range(10):
        merged = generate_merged_layout(seed, PRESET_8)
        for section in merged.sections:
            layout = section.layout
            report = validate_level(
                section.level, preset=section.preset, route=layout.route,
                segments=layout.segments, teleports=layout.teleports,
                walls=layout.walls, generator=layout.module,
                seed=section.seed, run_solver=False)
            assert report.ok, [c.message for c in report.errors]


def test_the_merged_report_keeps_the_screen_of_every_check():
    merged = generate_merged_layout(5, PRESET_8)
    reports = []
    for section in merged.sections:
        layout = section.layout
        reports.append(validate_level(
            section.level, preset=section.preset, route=layout.route,
            segments=layout.segments, teleports=layout.teleports,
            walls=layout.walls, generator=layout.module,
            seed=section.seed, run_solver=False))
    report = combine_reports(reports, PRESET_8.level_id, 5)
    assert report.metrics["sections"] == len(reports)
    assert report.metrics["modules"] == tuple(r.generator for r in reports)
    assert report.generator == "merged"
    sections = {check.details.get("section") for check in report.checks}
    assert sections == set(range(1, len(reports) + 1))


def test_a_preset_without_templates_is_merged_into_one_screen():
    preset = RandomPreset(level_id=77, name="Single", num_obstacles=3,
                           num_hidden_points=2, num_direct_blockers=0)
    merged = generate_merged_layout(3, preset)
    assert len(merged.sections) == 1
    assert merged.level.sections == ()
    assert merged.level.id == 77
