"""Level 14 Boomerang: chapter two's finale, the abs switch with everything before it.

Three sections, two checkpoints; the pans go up (0, 13), then up and to the
right (16, 13). Section 1 loops outside the map with Unbound and a switch
that only pushes up past the right edge, section 2 needs both the Shockwave
and the Shield, section 3 combines a wormhole, a Shield and a switch at x = -2.
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


# --- reference answers and near misses --------------------------------------------------
# Section 1: a spring toward x = 4, and a push up only outside the right edge (x > 10).
C1 = ("4 - x", "0.25((x - 10) + abs(x - 10))")
# Section 2: straight up through the Shockwave, then bending right through the Shield.
C2 = ("y + 7", "2")
# Section 3: no sideways force left of the wall at x = -2, a push right past it.
C3 = ("(x + 2) + abs(x + 2)", "3")
ANSWERS = (C1, C2, C3)
TIMES = (5.89, 3.60, 3.42)
NEAR_MISSES = [
    ("0", "5"),
    ("5", "5"),
    ("3", "3"),
    ("-x", "2"),
    ("4 - x", "0"),          # the spring without the switch
    ("-2x + 8", "1"),        # a linear shortcut
    ("y", "-x"),             # a swirl
]


def _fly(level, fx, fy):
    field = ForceField.from_exprs(parse_expression(fx), parse_expression(fy))
    flight = Flight(field, SHIP, level)
    while flight.running:
        flight.step()
    return flight


def _events(flight):
    return [event.get("kind") for event in flight.pickup_events]


def _lift(c):
    return "4 - x", f"{c:g}((x - 10) + abs(x - 10))"


def _bend(c=1, f=3):
    fx = "(x + 2) + abs(x + 2)" if c == 1 else f"{c:g}((x + 2) + abs(x + 2))"
    return fx, f"{f:g}"


def _without(s, *kinds):
    return dataclasses.replace(s, pickups=tuple(p for p in s.pickups if p.kind not in kinds))


def test_the_helpers_write_the_reference_answers():
    assert _lift(0.25) == C1
    assert _bend() == C3


@pytest.mark.parametrize("index", [0, 1, 2], ids=SECTION_IDS)
def test_each_reference_answer_reaches_without_a_bounce(index):
    flight = _fly(section(index), *ANSWERS[index])
    assert flight.outcome is Outcome.REACHED
    assert flight.bounces == 0
    assert flight.time == pytest.approx(TIMES[index], abs=0.05)


def test_section_one_takes_the_unbound():
    assert "unbound" in _events(_fly(section(0), *C1))


def test_section_two_takes_the_shockwave_and_the_shield_and_uses_it():
    events = _events(_fly(section(1), *C2))
    assert "shockwave" in events
    assert "shield" in events and "shield_used" in events


def test_section_three_goes_through_the_wormhole_and_uses_the_shield():
    flight = _fly(section(2), *C3)
    assert flight.teleports == 1
    events = _events(flight)
    assert "shield" in events and "shield_used" in events


@pytest.mark.parametrize("index", [0, 1, 2], ids=SECTION_IDS)
@pytest.mark.parametrize("answer", [0, 1, 2], ids=["C1", "C2", "C3"])
def test_only_its_own_answer_clears_a_section(index, answer):
    outcome = _fly(section(index), *ANSWERS[answer]).outcome
    assert (outcome is Outcome.REACHED) == (answer == index)


@pytest.mark.parametrize("index", [0, 1, 2], ids=SECTION_IDS)
@pytest.mark.parametrize("field", NEAR_MISSES, ids=lambda f: f"({f[0]}, {f[1]})")
def test_constant_linear_and_swirl_fields_do_not_clear_a_section(index, field):
    assert _fly(section(index), *field).outcome is not Outcome.REACHED


def test_section_one_needs_the_unbound():
    assert _fly(_without(section(0), "unbound"), *C1).outcome is not Outcome.REACHED


@pytest.mark.parametrize("kind", ["shockwave", "shield"])
def test_section_two_needs_both_pickups(kind):
    assert _fly(_without(section(1), kind), *C2).outcome is not Outcome.REACHED


def test_section_three_needs_the_shield():
    assert _fly(_without(section(2), "shield"), *C3).outcome is not Outcome.REACHED


def test_section_three_needs_the_wormhole():
    bare = dataclasses.replace(section(2), holes=())
    assert _fly(bare, *C3).outcome is not Outcome.REACHED


@pytest.mark.parametrize("c", [0.23, 0.24, 0.25, 0.26])
def test_section_one_takes_a_narrow_range_of_lifts(c):
    assert _fly(section(0), *_lift(c)).outcome is Outcome.REACHED


@pytest.mark.parametrize("c", [0.2, 0.3])
def test_section_one_misses_with_too_weak_or_too_strong_a_lift(c):
    assert _fly(section(0), *_lift(c)).outcome is not Outcome.REACHED


@pytest.mark.parametrize("field", [("2y + 14", "4"), ("0.5(y + 7)", "1")],
                         ids=lambda f: f"({f[0]}, {f[1]})")
def test_section_two_only_minds_the_ratio(field):
    assert _fly(section(1), *field).outcome is Outcome.REACHED


@pytest.mark.parametrize("fy", ["1.6", "2.4"])
def test_section_two_misses_with_the_ratio_off(fy):
    assert _fly(section(1), "y + 7", fy).outcome is not Outcome.REACHED


@pytest.mark.parametrize("c, f", [(1, 2.6), (1, 3.4), (0.8, 3)])
def test_section_three_takes_a_range_of_pushes(c, f):
    assert _fly(section(2), *_bend(c, f)).outcome is Outcome.REACHED


def test_section_three_misses_with_too_strong_a_push_right():
    assert _fly(section(2), *_bend(1.2, 3)).outcome is not Outcome.REACHED
