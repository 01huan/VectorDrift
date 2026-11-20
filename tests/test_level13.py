"""Level 13 Change of Course: the abs switch on the y axis, and the first change of pan direction.

Three sections, two checkpoints; the pans go up (0, 13), then right (16, 0).
y + abs(y) is 0 below y = 0 and 2y above it; -y + abs(y) is the other way
round. Section 1 crosses a wall by wormhole with the switch at y = 0,
section 2 moves the switch to y = -1 and needs the Shockwave, section 3
reviews level 10's swirl, flipped, with the Shield.
"""

import pytest

from vector_drift import config
from vector_drift.data import (LEVELS, SHIPS, LevelSpec, all_levels, get_level, section_count,
                               section_level, section_shift)
from vector_drift.level_presets import is_dynamic_level
from vector_drift.pickups import discs_overlap

LEVEL = get_level(13)
SHIP = SHIPS[LEVEL.ship_id]
HULL = SHIP.hull_radius
ROCK_R = 0.8
PICKUP_R = 0.45

STARTS = ((6.0, -6.0), (-1.5, -6.5), (-8.0, 4.5))
TARGETS = ((-1.5, 6.5), (8.0, 4.5), (5.5, -4.5))
ROCKS = (
    tuple((x, 0.0) for x in (-9.6, -8.0, -6.4, -4.8, -3.2, -1.6, 0.0, 1.6, 3.2, 4.8, 6.4, 8.0, 9.6)),
    tuple((2.5, y) for y in (-4.7, -3.1, -1.5, 0.1, 1.7, 3.3, 4.9, 6.5))
    + tuple((0.0, y) for y in (-4.7, -3.1, -1.5))
    + tuple((x, -4.7) for x in (-4.8, -3.2, 4.1, 5.0)),
    tuple((x, -1.0) for x in (1.0, 2.5, 4.0, 5.5, 7.0, 8.5, 10.0))
    + tuple((1.0, y) for y in (-2.5, -4.0, -5.5, -7.0)),
)
BLACK_HOLE, WHITE_HOLE, HOLE_R = (6.0, -2.5), (4.0, 2.0), 0.5
SHOCKWAVE = (-0.5, 1.6)
SHIELD = (-1.0, 4.5)
SECTION_IDS = ["section1", "section2", "section3"]


def section(index):
    return section_level(LEVEL, index)


# --- layout -----------------------------------------------------------------------
def test_level_thirteen_is_a_fixed_three_section_level():
    assert isinstance(LEVEL, LevelSpec) and LEVEL in LEVELS
    assert LEVEL.name == "Change of Course"
    assert not is_dynamic_level(13)
    assert section_count(LEVEL) == 3
    assert LEVEL.lives == 5
    for k in range(3):
        s = section(k)
        assert s.target_radius == 1.0
        assert s.time_limit == 10.0
        assert all(o.radius == ROCK_R for o in s.obstacles)
        assert not [p for p in s.pickups if p.kind == "money"]       # no coins


@pytest.mark.parametrize("index", [0, 1, 2], ids=SECTION_IDS)
def test_start_target_and_rocks_match_the_plan(index):
    s = section(index)
    assert s.start == STARTS[index]
    assert s.target_center == TARGETS[index]
    assert len(s.obstacles) == len(ROCKS[index])
    assert {o.center for o in s.obstacles} == set(ROCKS[index])


def test_section_one_has_only_the_wormhole():
    s = section(0)
    assert s.pickups == ()
    (hole,) = s.holes
    assert (hole.black_center, hole.white_center, hole.radius) == (BLACK_HOLE, WHITE_HOLE, HOLE_R)


def test_section_two_has_only_the_shockwave():
    s = section(1)
    assert s.holes == ()
    assert [(p.kind, p.center, p.radius) for p in s.pickups] == [("shockwave", SHOCKWAVE, PICKUP_R)]


def test_section_three_has_only_the_shield():
    s = section(2)
    assert s.holes == ()
    assert [(p.kind, p.center, p.radius) for p in s.pickups] == [("shield", SHIELD, PICKUP_R)]


def test_the_pans_go_up_then_to_the_right():
    # World: (6, -6) -> (-1.5, 6.5) -> (8, 17.5) -> (21.5, 8.5).
    assert section_shift(LEVEL, 0) == (0.0, 13.0)
    assert section_shift(LEVEL, 1) == (16.0, 0.0)


def _things(s):
    yield "start", s.start, 0.0
    yield "target", s.target_center, s.target_radius
    for p in s.pickups:
        yield f"{p.kind} {p.center}", p.center, p.radius
    for h in s.holes:
        yield "black hole", h.black_center, h.radius
        yield "white hole", h.white_center, h.radius


@pytest.mark.parametrize("index", [0, 1, 2], ids=SECTION_IDS)
def test_nothing_sits_in_a_rock(index):
    s = section(index)
    for name, center, radius in _things(s):
        for rock in s.obstacles:
            assert not discs_overlap(center, radius, rock.center, rock.radius + HULL), (name, rock.center)


def test_level_select_lists_level_thirteen():
    cards = {lv.id: lv for lv in all_levels()}
    assert cards[13] is LEVEL


def test_level_thirteen_gives_its_xp():
    assert config.XP_FIXED_LEVEL_BASE[13] == 340
