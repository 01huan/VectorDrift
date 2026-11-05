"""Level 9 New Horizon, and the overlap rule for every multi-section level."""

import pytest

from vector_drift import config
from vector_drift.data import (LEVELS, HoleSpec, ObstacleSpec, PickupSpec, SectionSpec, all_levels,
                               get_level, multi_section_level, section_count, section_level,
                               section_shift)
from vector_drift.level_presets import PRESETS, dynamic_ids, is_dynamic_level
from vector_drift.scenes.game import START_MARKER_RADIUS_M

HALF_W, HALF_H = config.WORLD_HALF_W, config.WORLD_HALF_H
MULTI = [lv for lv in LEVELS if lv.sections]


# --- level 9 --------------------------------------------------------------------
def test_level_nine_is_a_fixed_two_section_level():
    level = get_level(9)
    assert level.name == "New Horizon"
    assert not is_dynamic_level(9)
    assert section_count(level) == 2
    first, second = section_level(level, 0), section_level(level, 1)
    for section in (first, second):
        assert section.start == (-7.0, 0.0)
        assert section.target_center == (7.0, 0.0)
        assert section.time_limit == 10.0
        assert section.obstacles == section.pickups == section.holes == ()
    assert section_shift(level, 0) == (14.0, 0.0)          # world x: -7 -> 7 -> 21


def test_level_nine_matches_level_one_where_it_should():
    one, nine = get_level(1), get_level(9)
    assert nine.ship_id == one.ship_id
    assert nine.lives == one.lives
    for section in nine.sections:
        assert section.target_radius == one.target_radius


def test_level_nine_is_on_the_level_select():
    assert 9 in {lv.id for lv in all_levels()}


def test_no_random_preset_takes_a_fixed_level_id():
    assert 9 not in dynamic_ids() and 9 not in PRESETS
    fixed = {lv.id for lv in LEVELS}
    assert not fixed & set(dynamic_ids())


@pytest.mark.usefixtures("pygame_display")
def test_level_nine_plays_through_checkpoint_to_the_win():
    from types import SimpleNamespace

    import pygame

    from vector_drift.scenes.base import SceneManager
    from vector_drift.scenes.game import ARRIVED, FLIGHT, PANNING, GameScene

    audio = SimpleNamespace(play=lambda *a, **k: None, start_loop=lambda *a, **k: None,
                            stop_loop=lambda *a, **k: None)
    manager = SceneManager(audio)
    manager.session.level_id = 9
    manager.session.fx_text, manager.session.fy_text = "5", "0"
    scene = GameScene(manager)
    manager.switch(scene)
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))

    for expected in (PANNING, ARRIVED):
        scene.dialogue = None
        scene._try_launch()
        while scene.state == FLIGHT:
            scene.update(0.05)
            scene.draw(surface)
        assert scene.state == expected
        while scene.state == PANNING:
            scene.update(0.05)
            scene.draw(surface)
    assert scene.section_index == 1
    assert scene.total_time == pytest.approx(2 * 2.27, abs=0.1)


# --- overlap between neighbouring sections ----------------------------------------
def _disc_hits_rect(center, radius, rect):
    """Does the disc (center, radius) reach into rect = (x0, y0, x1, y1)?"""
    x0, y0, x1, y1 = rect
    cx = min(max(center[0], x0), x1)
    cy = min(max(center[1], y0), y1)
    return (center[0] - cx) ** 2 + (center[1] - cy) ** 2 < radius ** 2 or (
        x0 < center[0] < x1 and y0 < center[1] < y1)


def _hole_discs(holes):
    for hole in holes:
        if isinstance(hole, HoleSpec):
            yield hole.black_center, hole.radius
            yield hole.white_center, hole.radius
        else:
            black, white, radius = hole
            yield black, radius
            yield white, radius


def _props(section, *, start, target):
    """(what, center, radius) of everything drawn for a section, checkpoints left out."""
    for o in section.obstacles:
        yield "obstacle", o.center, o.radius
    for p in section.pickups:
        yield f"{p.kind} pickup", p.center, p.radius
    for center, radius in _hole_discs(section.holes):
        yield "hole", center, radius
    if start:
        yield "start pad", section.start, START_MARKER_RADIUS_M
    if target:
        yield "planet", section.target_center, section.target_radius


def overlap_problems(level):
    """Everything inside the area two neighbouring sections share on screen.

    During a pan both sections are drawn, so a prop there would pop in (next
    section) or vanish (previous section). Only the shared checkpoint (the
    previous target = the next start) may sit in it. Coordinates: section k.
    """
    problems = []
    last = len(level.sections) - 1
    for k in range(last):
        sx, sy = section_shift(level, k)
        shared = (max(-HALF_W, sx - HALF_W), max(-HALF_H, sy - HALF_H),
                  min(HALF_W, sx + HALF_W), min(HALF_H, sy + HALF_H))
        if shared[0] >= shared[2] or shared[1] >= shared[3]:
            continue                                    # the screens do not touch
        here, there = level.sections[k], level.sections[k + 1]
        for what, center, radius in _props(here, start=(k == 0), target=False):
            if _disc_hits_rect(center, radius, shared):
                problems.append(f"level {level.id} section {k + 1}: {what} at {center}")
        for what, center, radius in _props(there, start=False, target=(k + 1 == last)):
            moved = (center[0] + sx, center[1] + sy)
            if _disc_hits_rect(moved, radius, shared):
                problems.append(f"level {level.id} section {k + 2}: {what} at {center}")
    return problems


@pytest.mark.parametrize("level", MULTI, ids=lambda lv: f"level{lv.id}")
def test_nothing_but_the_checkpoint_sits_where_sections_overlap(level):
    assert overlap_problems(level) == []


def test_there_is_a_multi_section_level_to_check():
    assert [lv.id for lv in MULTI] == [9]


def test_the_overlap_check_catches_props_from_either_side():
    bad = multi_section_level(
        id=99, name="Bad", ship_id="ship01",
        sections=(
            # Section 1's rock at x = 6 is inside the shared strip x in [4, 10].
            SectionSpec(start=(-7.0, 0.0), target_center=(7.0, 0.0),
                        obstacles=(ObstacleSpec(center=(6.0, 4.0), radius=0.8),)),
            # Section 2's coin at x = -8 is that strip in section 2's coordinates;
            # its hole at x = -3.6 (r 0.5) just reaches into it (-4).
            SectionSpec(start=(-7.0, 0.0), target_center=(7.0, 0.0),
                        pickups=(PickupSpec(center=(-8.0, -4.0), kind="money"),),
                        holes=(((-3.6, 5.0), (3.0, 5.0), 0.5),)),
        ),
    )
    problems = overlap_problems(bad)
    assert len(problems) == 3
    assert any("section 1: obstacle" in p for p in problems)
    assert any("section 2: money pickup" in p for p in problems)
    assert any("section 2: hole" in p for p in problems)


def test_the_overlap_check_follows_diagonal_pans():
    # Pan (12, 8): shared area is x in [2, 10], y in [0.5, 7.5] of section 1.
    level = multi_section_level(
        id=98, name="Diagonal", ship_id="ship01",
        sections=(
            SectionSpec(start=(-7.0, -5.0), target_center=(6.0, 4.0),
                        obstacles=(ObstacleSpec(center=(6.0, -3.0), radius=0.8),)),   # below it: fine
            SectionSpec(start=(-6.0, -4.0), target_center=(5.0, 0.0),
                        obstacles=(ObstacleSpec(center=(-8.0, -2.0), radius=0.8),)),  # = (4, 6): inside
        ),
    )
    assert overlap_problems(level) == ["level 98 section 2: obstacle at (-8.0, -2.0)"]
