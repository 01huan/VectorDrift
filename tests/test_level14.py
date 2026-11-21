"""Level 14 Boomerang: chapter two's finale, the abs switch with everything before it.

Three sections, two checkpoints; the pans go up (0, 13), then up and to the
right (16, 13). Section 1 loops outside the map with Unbound and a switch
that only pushes up past the right edge, section 2 needs both the Shockwave
and the Shield, section 3 combines a wormhole, a Shield and a switch at x = -2.
"""

import pytest

from vector_drift import config
from vector_drift.data import (LEVELS, SHIPS, LevelSpec, all_levels, get_level, section_count,
                               section_level, section_shift)
from vector_drift.level_presets import is_dynamic_level
from vector_drift.pickups import discs_overlap

LEVEL = get_level(14)
SHIP = SHIPS[LEVEL.ship_id]
HULL = SHIP.hull_radius
ROCK_R = 0.8
PICKUP_R = 0.45

ROW = (-9.6, -8.0, -6.4, -4.8, -3.2, -1.6, 0.0, 1.6, 3.2, 4.8, 6.4, 8.0, 9.6)
STARTS = ((-8.0, -6.5), (-7.0, -7.0), (-8.0, -6.5))
TARGETS = ((-7.0, 6.0), (8.0, 6.5), (7.0, 6.0))
ROCKS = (
    tuple((x, -4.8) for x in ROW) + ((3.5, -1.5), (2.5, 4.25), (-3.75, 4.5)),
    tuple((x, -2.0) for x in ROW) + tuple((4.0, y) for y in (-0.4, 1.2, 2.8, 4.4, 6.0, 7.5)),
    tuple((-2.0, y) for y in (-7.5, -6.0, -4.5, -3.0, -1.5, 0.0, 1.5, 3.0, 4.5, 6.0, 7.5))
    + tuple((x, 2.0) for x in (5.0, 6.7, 8.4, 10.1))
    + tuple((5.0, y) for y in (3.1, 5.0, 6.9)),
)
UNBOUND = (3.0, -6.5)
SHOCKWAVE = (-6.0, -3.5)
SHIELD_2 = (1.5, 3.1)
SHIELD_3 = (3.0, 2.2)
BLACK_HOLE, WHITE_HOLE, HOLE_R = (-8.0, 2.0), (1.0, -4.0), 0.5
SECTION_IDS = ["section1", "section2", "section3"]


def section(index):
    return section_level(LEVEL, index)


# --- layout -----------------------------------------------------------------------
def test_level_fourteen_is_a_fixed_three_section_level():
    assert isinstance(LEVEL, LevelSpec) and LEVEL in LEVELS
    assert LEVEL.name == "Boomerang"
    assert not is_dynamic_level(14)
    assert section_count(LEVEL) == 3
    assert LEVEL.lives == 5
    for k in range(3):
        s = section(k)
        assert s.target_radius == 1.0
        assert s.time_limit == 10.0
        assert all(o.radius == ROCK_R for o in s.obstacles)
        assert all(p.radius == PICKUP_R for p in s.pickups)
        assert not [p for p in s.pickups if p.kind == "money"]       # no coins


@pytest.mark.parametrize("index", [0, 1, 2], ids=SECTION_IDS)
def test_start_target_and_rocks_match_the_plan(index):
    s = section(index)
    assert s.start == STARTS[index]
    assert s.target_center == TARGETS[index]
    assert len(s.obstacles) == len(ROCKS[index])
    assert {o.center for o in s.obstacles} == set(ROCKS[index])


def test_section_one_has_only_the_unbound():
    s = section(0)
    assert s.holes == ()
    assert [(p.kind, p.center, p.radius) for p in s.pickups] == [("unbound", UNBOUND, PICKUP_R)]


def test_section_two_has_only_the_shockwave_and_the_shield():
    s = section(1)
    assert s.holes == ()
    assert sorted((p.kind, p.center, p.radius) for p in s.pickups) == [
        ("shield", SHIELD_2, PICKUP_R), ("shockwave", SHOCKWAVE, PICKUP_R)]


def test_section_three_has_only_the_shield_and_the_wormhole():
    s = section(2)
    assert [(p.kind, p.center, p.radius) for p in s.pickups] == [("shield", SHIELD_3, PICKUP_R)]
    (hole,) = s.holes
    assert (hole.black_center, hole.white_center, hole.radius) == (BLACK_HOLE, WHITE_HOLE, HOLE_R)


def test_the_pans_go_up_then_up_and_to_the_right():
    # World: (-8, -6.5) -> (-7, 6) -> (8, 19.5) -> (23, 32).
    assert section_shift(LEVEL, 0) == (0.0, 13.0)
    assert section_shift(LEVEL, 1) == (16.0, 13.0)


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


def test_level_select_lists_level_fourteen():
    cards = {lv.id: lv for lv in all_levels()}
    assert cards[14] is LEVEL


def test_level_fourteen_gives_its_xp():
    assert config.XP_FIXED_LEVEL_BASE[14] == 360
