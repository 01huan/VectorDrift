"""Level 13 Change of Course: the abs switch on the y axis, and the first change of pan direction.

Three sections, two checkpoints; the pans go up (0, 13), then right (16, 0).
y + abs(y) is 0 below y = 0 and 2y above it; -y + abs(y) is the other way
round. Section 1 crosses a wall by wormhole with the switch at y = 0,
section 2 moves the switch to y = -1 and needs the Shockwave, section 3
reviews level 10's swirl, flipped, with the Shield.
"""

import dataclasses

import pytest

from vector_drift import config
from vector_drift.data import (LEVELS, SHIPS, LevelSpec, all_levels, get_level, section_count,
                               section_level, section_shift)
from vector_drift.expr_parser import parse_expression
from vector_drift.level_presets import is_dynamic_level
from vector_drift.physics import Flight, ForceField, Outcome
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


# --- reference answers and near misses --------------------------------------------------
# Section 1: a spring toward y = 0 below the wall, a push to the left above it.
B1 = ("-4(y + abs(y))", "-y + abs(y)")
# Section 2: the same switch moved to y = -1, pushing to the right above it.
B2 = ("10((y + 1) + abs(y + 1))", "-(y + 1) + abs(y + 1)")
# Section 3: level 10's swirl flipped upside down, clockwise round (-7, 2.5).
B3 = ("y - 2.5", "-x - 7")
ANSWERS = (B1, B2, B3)
TIMES = (1.29, 1.79, 3.51)
NEAR_MISSES = [
    ("0", "5"),
    ("5", "5"),
    ("-3", "5"),
    ("2", "3"),
    ("-x", "6 - y"),
    ("y", "-x"),
]


def _fly(level, fx, fy):
    field = ForceField.from_exprs(parse_expression(fx), parse_expression(fy))
    flight = Flight(field, SHIP, level)
    while flight.running:
        flight.step()
    return flight


def _events(flight):
    return [event.get("kind") for event in flight.pickup_events]


def _push_left(c):
    return f"-{c:g}(y + abs(y))", "-y + abs(y)"


def _push_right(c=10, h=1):
    if h == 0:
        return f"{c:g}(y + abs(y))", "-y + abs(y)"
    y = f"y + {h:g}"
    return f"{c:g}(({y}) + abs({y}))", f"-({y}) + abs({y})"


def test_the_helpers_write_the_reference_answers():
    assert _push_left(4) == B1
    assert _push_right() == B2


@pytest.mark.parametrize("index", [0, 1, 2], ids=SECTION_IDS)
def test_each_reference_answer_reaches_without_a_bounce(index):
    flight = _fly(section(index), *ANSWERS[index])
    assert flight.outcome is Outcome.REACHED
    assert flight.bounces == 0
    assert flight.time == pytest.approx(TIMES[index], abs=0.05)


def test_section_one_goes_through_the_wormhole():
    assert _fly(section(0), *B1).teleports == 1


def test_section_two_takes_the_shockwave():
    assert "shockwave" in _events(_fly(section(1), *B2))


def test_section_three_takes_the_shield_and_uses_it():
    events = _events(_fly(section(2), *B3))
    assert "shield" in events and "shield_used" in events


@pytest.mark.parametrize("index", [0, 1, 2], ids=SECTION_IDS)
@pytest.mark.parametrize("answer", [0, 1, 2], ids=["B1", "B2", "B3"])
def test_only_its_own_answer_clears_a_section(index, answer):
    outcome = _fly(section(index), *ANSWERS[answer]).outcome
    assert (outcome is Outcome.REACHED) == (answer == index)


@pytest.mark.parametrize("index", [0, 1, 2], ids=SECTION_IDS)
@pytest.mark.parametrize("field", NEAR_MISSES, ids=lambda f: f"({f[0]}, {f[1]})")
def test_constant_linear_and_swirl_fields_do_not_clear_a_section(index, field):
    assert _fly(section(index), *field).outcome is not Outcome.REACHED


def test_section_one_needs_the_wormhole():
    bare = dataclasses.replace(section(0), holes=())
    assert _fly(bare, *B1).outcome is not Outcome.REACHED


@pytest.mark.parametrize("index", [1, 2], ids=["section2", "section3"])
def test_sections_two_and_three_need_their_pickup(index):
    bare = dataclasses.replace(section(index), pickups=())
    assert _fly(bare, *ANSWERS[index]).outcome is not Outcome.REACHED


@pytest.mark.parametrize("c", [3, 4, 5, 6, 7])
def test_section_one_takes_a_range_of_push_strengths(c):
    assert _fly(section(0), *_push_left(c)).outcome is Outcome.REACHED


def test_section_one_misses_with_too_weak_a_push():
    assert _fly(section(0), *_push_left(2)).outcome is not Outcome.REACHED


@pytest.mark.parametrize("c", [8, 10, 15, 20])
def test_section_two_takes_a_range_of_push_strengths(c):
    assert _fly(section(1), *_push_right(c=c)).outcome is Outcome.REACHED


@pytest.mark.parametrize("c", [6, 25])
def test_section_two_misses_with_too_weak_or_too_strong_a_push(c):
    assert _fly(section(1), *_push_right(c=c)).outcome is not Outcome.REACHED


@pytest.mark.parametrize("h", [1, 1.5])
def test_section_two_takes_a_range_of_switch_lines(h):
    assert _fly(section(1), *_push_right(h=h)).outcome is Outcome.REACHED


@pytest.mark.parametrize("h", [0, 0.5, 2])
def test_section_two_misses_with_the_switch_too_low_or_too_high(h):
    assert _fly(section(1), *_push_right(h=h)).outcome is not Outcome.REACHED
