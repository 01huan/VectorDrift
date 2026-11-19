"""Level 9 Ascent: chapter 2 opens with the first upward pan.

Section 1 reviews level 2's bounce off round rocks (its swirl, turned on its
side); section 2 reviews level 3's shockwave (a ring of rocks round the
planet, opened by one blast).
"""

import dataclasses
import math

import pytest

from vector_drift.data import (LEVELS, SHIPS, LevelSpec, all_levels, get_level, section_count,
                               section_level, section_shift)
from vector_drift.expr_parser import parse_expression
from vector_drift.level_presets import RANDOM_LEVEL_ID, is_dynamic_level
from vector_drift.physics import Flight, ForceField, Outcome
from vector_drift.pickups import SHOCKWAVE_BLAST_RADIUS, discs_overlap, obstacles_hit_by_blast

LEVEL = get_level(9)
SHIP = SHIPS[LEVEL.ship_id]
HULL = SHIP.hull_radius
ROCK_R = 0.8

ROW = ((-1.6, 0.0), (0.0, 0.0), (1.6, 0.0))
RING_CENTER = (0.0, 2.5)
RING = ((0.0, -0.1), (1.67, 0.51), (2.56, 2.05), (2.25, 3.8), (0.89, 4.94),
        (-0.89, 4.94), (-2.25, 3.8), (-2.56, 2.05), (-1.67, 0.51))
SHOCKWAVE = (-4.0, -0.5)


def first():
    return section_level(LEVEL, 0)


def second():
    return section_level(LEVEL, 1)


# --- layout -----------------------------------------------------------------------
def test_level_nine_is_a_fixed_two_section_level():
    assert isinstance(LEVEL, LevelSpec) and LEVEL in LEVELS
    assert LEVEL.name == "Ascent"
    assert not is_dynamic_level(9)
    assert section_count(LEVEL) == 2
    assert LEVEL.lives == 5
    for section in (first(), second()):
        assert section.start == (0.0, -5.5)
        assert section.target_radius == 1.0
        assert section.time_limit == 10.0
        assert section.holes == ()


def test_the_pan_goes_straight_up():
    assert section_shift(LEVEL, 0) == (0.0, 11.0)      # world y: -5.5 -> 5.5 -> 13.5


def test_section_one_is_a_row_of_three_rocks_below_the_checkpoint():
    section = first()
    assert section.target_center == (0.0, 5.5)
    assert sorted(o.center for o in section.obstacles) == sorted(ROW)
    assert all(o.radius == ROCK_R for o in section.obstacles)
    assert section.pickups == ()


def test_section_two_is_a_ring_round_the_planet_and_one_shockwave():
    section = second()
    assert section.target_center == RING_CENTER
    assert sorted(o.center for o in section.obstacles) == sorted(RING)
    assert all(o.radius == ROCK_R for o in section.obstacles)
    assert [(p.center, p.radius, p.kind) for p in section.pickups] == [(SHOCKWAVE, 0.45, "shockwave")]


def test_the_ring_is_level_threes_ring_every_40_degrees_from_270():
    for k, center in enumerate(RING):
        angle = math.radians(270 + 40 * k)
        expected = (RING_CENTER[0] + 2.6 * math.cos(angle), RING_CENTER[1] + 2.6 * math.sin(angle))
        assert center == pytest.approx(expected, abs=0.01)


def test_neighbouring_ring_rocks_seal_the_planet():
    ring = list(RING) + [RING[0]]
    for a, b in zip(ring, ring[1:]):
        assert math.dist(a, b) <= 2 * ROCK_R + 2 * HULL, (a, b)


def _things(section, pickups):
    yield "start", section.start, 0.0
    yield "target", section.target_center, section.target_radius
    for p in pickups:
        yield f"{p.kind} {p.center}", p.center, p.radius


@pytest.mark.parametrize("index", [0, 1], ids=["section1", "section2"])
def test_nothing_sits_in_a_rock(index):
    section = section_level(LEVEL, index)
    for name, center, radius in _things(section, section.pickups):
        for rock in section.obstacles:
            assert not discs_overlap(center, radius, rock.center, rock.radius + HULL), (name, rock.center)


def test_level_select_lists_level_nine_and_the_random_level_after_it():
    cards = {lv.id: lv for lv in all_levels()}
    assert cards[9] is LEVEL
    assert RANDOM_LEVEL_ID == 10 and is_dynamic_level(10)
    assert "ship10" in SHIPS


# --- reference answers and near misses --------------------------------------------------
# Section 1: level 2's swirl turned on its side, round (0, -4.5), right or left of the rocks.
RIGHT = ("-y - 4.5", "x")
LEFT = ("y + 4.5", "-x")
# Section 2: a steady push up with level 3's spring toward the slanted line x = y/2.
SPRING = ("-2x + y", "2")
BLASTED = {(-2.56, 2.05), (-1.67, 0.51)}


def _fly(level, fx, fy):
    field = ForceField.from_exprs(parse_expression(fx), parse_expression(fy))
    flight = Flight(field, SHIP, level)
    while flight.running:
        flight.step()
    return flight


def _blasted(level, flight):
    return {o.center for o in level.obstacles} - {o.center for o in flight.obstacle_specs}


@pytest.mark.parametrize("answer", [RIGHT, LEFT], ids=["right", "left"])
def test_section_one_swirls_round_the_rocks_into_the_checkpoint(answer):
    flight = _fly(first(), *answer)
    assert flight.outcome is Outcome.REACHED
    assert flight.bounces == 0
    assert flight.time == pytest.approx(4.28, abs=0.05)


def test_section_two_takes_the_shockwave_through_the_ring():
    section = second()
    flight = _fly(section, *SPRING)
    assert flight.outcome is Outcome.REACHED
    assert flight.bounces == 0
    assert flight.time == pytest.approx(2.86, abs=0.05)
    assert {p.center for p in flight.pickups if p.consumed} == {SHOCKWAVE}
    assert _blasted(section, flight) == BLASTED


def test_the_shockwave_blasts_exactly_two_ring_rocks():
    _, destroyed = obstacles_hit_by_blast(SHOCKWAVE, SHOCKWAVE_BLAST_RADIUS, second().obstacles)
    assert {o.center for o in destroyed} == BLASTED


def test_section_one_cannot_just_push_straight_up():
    assert _fly(first(), "0", "5").outcome is not Outcome.REACHED


def test_section_two_ring_is_closed_without_the_shockwave():
    bare = dataclasses.replace(second(), pickups=())
    assert _fly(bare, *SPRING).outcome is not Outcome.REACHED


@pytest.mark.parametrize("answer", [RIGHT, LEFT], ids=["right", "left"])
def test_section_one_answers_leave_the_map_in_section_two(answer):
    assert _fly(second(), *answer).outcome is Outcome.OUT_OF_BOUNDS
