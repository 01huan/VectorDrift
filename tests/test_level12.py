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
from vector_drift.expr_parser import parse_expression
from vector_drift.level_presets import is_dynamic_level
from vector_drift.physics import Flight, ForceField, Outcome
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


# --- reference answers and near misses --------------------------------------------------

def _switch(c=10, h=0):
    """Section 1's field with push-down strength ``c`` and the switch at x = ``h``."""
    if h == 0:
        return "-x + abs(x)", f"-{c:g}(x + abs(x))"
    x = f"x - {h:g}"
    return f"-({x}) + abs({x})", f"-{c:g}(({x}) + abs({x}))"


# Section 1: a spring toward x = 0 on the left, a push down on the right.
A1 = ("-x + abs(x)", "-10(x + abs(x))")
# Section 2: the same field with the switch moved to x = 3.
A2 = ("-(x - 3) + abs(x - 3)", "-10((x - 3) + abs(x - 3))")
ANSWERS = (A1, A2)
TIMES = (1.77, 1.48)
NEAR_MISSES = [
    ("6", "-1"),
    ("1", "-3"),
    ("2", "0"),
    ("-x", "-x - y"),
    ("-x + 1", "y - 6"),
]


def _fly(level, fx, fy):
    field = ForceField.from_exprs(parse_expression(fx), parse_expression(fy))
    flight = Flight(field, SHIP, level)
    while flight.running:
        flight.step()
    return flight


def test_the_switch_helper_writes_the_reference_answers():
    assert _switch() == A1
    assert _switch(h=3) == A2


@pytest.mark.parametrize("index", [0, 1], ids=["section1", "section2"])
def test_each_reference_answer_reaches_without_a_bounce(index):
    flight = _fly(section(index), *ANSWERS[index])
    assert flight.outcome is Outcome.REACHED
    assert flight.bounces == 0
    assert flight.time == pytest.approx(TIMES[index], abs=0.05)


@pytest.mark.parametrize("index", [0, 1], ids=["section1", "section2"])
@pytest.mark.parametrize("answer", [0, 1], ids=["A1", "A2"])
def test_only_its_own_answer_clears_a_section(index, answer):
    outcome = _fly(section(index), *ANSWERS[answer]).outcome
    assert (outcome is Outcome.REACHED) == (answer == index)


@pytest.mark.parametrize("index", [0, 1], ids=["section1", "section2"])
@pytest.mark.parametrize("field", NEAR_MISSES, ids=lambda f: f"({f[0]}, {f[1]})")
def test_constant_and_linear_fields_do_not_clear_a_section(index, field):
    assert _fly(section(index), *field).outcome is not Outcome.REACHED


@pytest.mark.parametrize("c", [8, 10, 12, 14])
def test_section_one_takes_a_range_of_push_strengths(c):
    assert _fly(section(0), *_switch(c=c)).outcome is Outcome.REACHED


@pytest.mark.parametrize("c", [7, 15])
def test_section_one_misses_with_too_weak_or_too_strong_a_push(c):
    assert _fly(section(0), *_switch(c=c)).outcome is not Outcome.REACHED


@pytest.mark.parametrize("c", [6, 10, 15, 20, 25])
def test_section_two_takes_a_range_of_push_strengths(c):
    assert _fly(section(1), *_switch(c=c, h=3)).outcome is Outcome.REACHED


@pytest.mark.parametrize("h", [2, 2.5, 3.5, 4])
def test_section_two_takes_a_range_of_switch_lines(h):
    assert _fly(section(1), *_switch(h=h)).outcome is Outcome.REACHED


@pytest.mark.parametrize("h", [1.5, 4.5])
def test_section_two_misses_with_the_switch_too_far_left_or_right(h):
    assert _fly(section(1), *_switch(h=h)).outcome is not Outcome.REACHED
