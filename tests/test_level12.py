"""Level 12 Turning Point: the first level to teach abs(x) as a switch.

Two sections, one checkpoint, the first pan down and to the right. x + abs(x)
is 0 left of x = 0 and 2x right of it, so it only turns on on the right;
-x + abs(x) is the other way round. Section 1 switches at x = 0; section 2
runs the same route with the switch moved to x = 3.
"""

import pytest

from vector_drift import config
from vector_drift.data import (LEVELS, SHIPS, LevelSpec, all_levels, get_level, section_count,
                               section_level, section_shift)
from vector_drift.level_presets import is_dynamic_level
from vector_drift.pickups import discs_overlap

LEVEL = get_level(12)
SHIP = SHIPS[LEVEL.ship_id]
HULL = SHIP.hull_radius
ROCK_R = 0.8

START = (-7.0, 5.5)
CHECKPOINT = (6.9, -5.5)
PLANET = (9.0, 2.0)
ROCKS_1 = tuple((x, 3.5) for x in (-9.6, -8.0, -6.4, -4.8, -3.2, -1.6, 0.0, 1.6)) + (
    (-3.2, 7.0), (3.2, 1.6), (7.5, -1.5), (9.1, -1.5))
ROCKS_2 = tuple((x, 2.5) for x in (-9.6, -8.0, -6.4, -4.8, -3.2, -1.6, 0.0, 1.6, 3.2, 4.8, 6.4)) + (
    (5.0, 3.75), (-1.6, 7.0), (9.2, 4.5))


def section(index):
    return section_level(LEVEL, index)


# --- layout -----------------------------------------------------------------------
def test_level_twelve_is_a_fixed_two_section_level():
    assert isinstance(LEVEL, LevelSpec) and LEVEL in LEVELS
    assert LEVEL.name == "Turning Point"
    assert not is_dynamic_level(12)
    assert section_count(LEVEL) == 2
    assert LEVEL.lives == 5
    for k in range(2):
        s = section(k)
        assert s.target_radius == 1.0
        assert s.time_limit == 10.0
        assert s.holes == ()
        assert s.pickups == ()                          # no props, no coins
        assert all(o.radius == ROCK_R for o in s.obstacles)


def test_section_one_layout():
    s = section(0)
    assert s.start == START
    assert s.target_center == CHECKPOINT
    assert len(s.obstacles) == len(ROCKS_1) == 12
    assert {o.center for o in s.obstacles} == set(ROCKS_1)


def test_section_two_layout():
    s = section(1)
    assert s.start == START
    assert s.target_center == PLANET
    assert len(s.obstacles) == len(ROCKS_2) == 14
    assert {o.center for o in s.obstacles} == set(ROCKS_2)


def test_the_pan_goes_down_and_to_the_right():
    # World: (-7, 5.5) -> (6.9, -5.5) (checkpoint) -> (22.9, -9) (planet).
    assert section_shift(LEVEL, 0) == pytest.approx((13.9, -11.0))


def _things(s):
    yield "start", s.start, 0.0
    yield "target", s.target_center, s.target_radius


@pytest.mark.parametrize("index", [0, 1], ids=["section1", "section2"])
def test_nothing_sits_in_a_rock(index):
    s = section(index)
    for name, center, radius in _things(s):
        for rock in s.obstacles:
            assert not discs_overlap(center, radius, rock.center, rock.radius + HULL), (name, rock.center)


def test_level_select_lists_level_twelve():
    cards = {lv.id: lv for lv in all_levels()}
    assert cards[12] is LEVEL


def test_level_twelve_gives_its_xp():
    assert config.XP_FIXED_LEVEL_BASE[12] == 320
