"""Level 10 Shortcut: chapter 2's first diagonal pan.

Section 1 reviews level 4's wormhole (a steady push plus a spring toward a
slanted line); section 2 reviews the Shield with level 7's swirl (an L-shaped
wall, passed through one rock).
"""

import math

import pytest

from vector_drift import config
from vector_drift.data import (LEVELS, SHIPS, LevelSpec, all_levels, get_level, section_count,
                               section_level, section_shift)
from vector_drift.level_presets import is_dynamic_level
from vector_drift.pickups import discs_overlap

LEVEL = get_level(10)
SHIP = SHIPS[LEVEL.ship_id]
HULL = SHIP.hull_radius
ROCK_R = 0.8
HALF_W, HALF_H = config.WORLD_HALF_W, config.WORLD_HALF_H

START = (-7.0, -4.5)
WALL = tuple((2.0, y) for y in (-7.0, -5.4, -3.8, -2.2, -0.6, 1.0, 2.6, 4.2, 5.8, 7.4))
BLACK, WHITE = (-7.0, 1.5), (4.0, -1.0)
ROW = tuple((x, 1.0) for x in (2.0, 3.55, 5.1, 6.65, 8.2, 9.75))
COLUMN = ((2.0, 1.0),) + tuple((2.0, y) for y in (2.55, 4.1, 5.65, 7.2))
SHIELD = (0.0, -4.5)


def first():
    return section_level(LEVEL, 0)


def second():
    return section_level(LEVEL, 1)


# --- layout -----------------------------------------------------------------------
def test_level_ten_is_a_fixed_two_section_level():
    assert isinstance(LEVEL, LevelSpec) and LEVEL in LEVELS
    assert LEVEL.name == "Shortcut"
    assert not is_dynamic_level(10)
    assert section_count(LEVEL) == 2
    assert LEVEL.lives == 5
    for section in (first(), second()):
        assert section.start == START
        assert section.target_radius == 1.0
        assert section.time_limit == 10.0
        assert all(o.radius == ROCK_R for o in section.obstacles)


def test_level_ten_has_no_coins():
    for section in (first(), second()):
        assert not [p for p in section.pickups if p.kind == "money"]


def test_the_pan_goes_up_and_to_the_right():
    assert section_shift(LEVEL, 0) == (14.0, 9.0)       # world (-7, -4.5) -> (7, 4.5) -> (13.5, 9)


def test_section_one_is_a_wall_at_x_2_and_a_wormhole_across_it():
    section = first()
    assert section.target_center == (7.0, 4.5)
    assert sorted(o.center for o in section.obstacles) == sorted(WALL)
    assert section.pickups == ()
    assert len(section.holes) == 1
    hole = section.holes[0]
    assert (hole.black_center, hole.white_center, hole.radius) == (BLACK, WHITE, 0.5)


def test_section_two_is_an_l_shaped_wall_and_one_shield():
    section = second()
    assert section.target_center == (6.5, 4.5)
    assert sorted(o.center for o in section.obstacles) == sorted(set(ROW) | set(COLUMN))
    assert section.holes == ()
    assert [(p.center, p.radius, p.kind) for p in section.pickups] == [(SHIELD, 0.45, "shield")]


def _sealed(rocks):
    for a, b in zip(rocks, rocks[1:]):
        assert math.dist(a, b) <= 2 * ROCK_R + 2 * HULL, (a, b)


def test_section_one_wall_seals_the_map_from_top_to_bottom():
    _sealed(WALL)
    assert WALL[0][1] - ROCK_R < -HALF_H and WALL[-1][1] + ROCK_R > HALF_H


def test_section_two_wall_seals_the_top_right_corner():
    _sealed(ROW)
    _sealed(COLUMN)
    assert ROW[-1][0] + ROCK_R > HALF_W                 # the row reaches the right edge
    assert COLUMN[-1][1] + ROCK_R > HALF_H              # the column reaches the top edge
    x, y = second().target_center
    assert x > COLUMN[0][0] and y > ROW[0][1]           # the planet is inside the corner


def _things(section):
    yield "start", section.start, 0.0
    yield "target", section.target_center, section.target_radius
    for hole in section.holes:
        yield "black hole", hole.black_center, hole.radius
        yield "white hole", hole.white_center, hole.radius
    for p in section.pickups:
        yield f"{p.kind} {p.center}", p.center, p.radius


@pytest.mark.parametrize("index", [0, 1], ids=["section1", "section2"])
def test_nothing_sits_in_a_rock(index):
    section = section_level(LEVEL, index)
    for name, center, radius in _things(section):
        for rock in section.obstacles:
            assert not discs_overlap(center, radius, rock.center, rock.radius + HULL), (name, rock.center)


def test_level_select_lists_level_ten():
    cards = {lv.id: lv for lv in all_levels()}
    assert cards[10] is LEVEL
