"""Level 6: a curved rock wall seals the target in; only an Unbound ship goes around it."""

import dataclasses
import itertools
import math
import random

import pytest

from vector_drift import config
from vector_drift.data import LEVELS, SHIPS, LevelSpec, all_levels, get_level
from vector_drift.physics import Flight, ForceField, Outcome
from vector_drift.pickups import discs_overlap

LEVEL = get_level(6)
SHIP = SHIPS[LEVEL.ship_id]
HULL = SHIP.hull_radius
ROCK_R = 0.8
WALL_Y = (0.0, 1.5, 3.0, 4.4, 5.6, 6.7, 7.6, 8.4)
UNBOUNDS = {(-2.7, 6.3), (-2.7, -6.3)}


def wall_x(y):
    return 4.5 + y * y / 12


def rocks_by_y():
    return sorted(LEVEL.obstacles, key=lambda o: o.center[1])


def test_level_six_is_first_unbound():
    assert isinstance(LEVEL, LevelSpec) and LEVEL in LEVELS
    assert LEVEL.name == "First Unbound"
    assert LEVEL.start == (-7.0, 0.0)
    assert LEVEL.target_center == (7.5, 0.0) and LEVEL.target_radius == 1.0
    assert LEVEL.ship_id == "ship01"
    assert LEVEL.time_limit == 10.0
    assert LEVEL.sections == () and LEVEL.holes == ()


def test_the_wall_follows_the_curve():
    centers = sorted(o.center for o in LEVEL.obstacles)
    expected = sorted({(round(wall_x(y), 2), s * y) for y in WALL_Y for s in (1, -1)})
    assert len(LEVEL.obstacles) == 15
    assert centers == expected
    assert all(o.radius == ROCK_R for o in LEVEL.obstacles)


def test_the_two_pickups_are_unbound():
    assert {(p.center, p.radius, p.kind) for p in LEVEL.pickups} == {
        (c, 0.45, "unbound") for c in UNBOUNDS}


def test_neighbouring_rocks_leave_no_gap_for_the_ship():
    rocks = rocks_by_y()
    for a, b in zip(rocks, rocks[1:]):
        assert math.dist(a.center, b.center) < 2 * (ROCK_R + HULL), (a.center, b.center)


def test_both_ends_stick_out_past_the_corners():
    rocks = rocks_by_y()
    for end in (rocks[0], rocks[-1]):
        x, y = end.center
        assert abs(y) > config.WORLD_HALF_H and x > config.WORLD_HALF_W


@pytest.mark.parametrize("name, center, radius", [
    ("target", LEVEL.target_center, LEVEL.target_radius),
    ("start", LEVEL.start, 0.0),
    *[(f"unbound {c}", c, 0.45) for c in sorted(UNBOUNDS)],
])
def test_nothing_sits_in_a_rock(name, center, radius):
    for rock in LEVEL.obstacles:
        assert not discs_overlap(center, radius, rock.center, rock.radius + HULL), (name, rock.center)


def test_everything_but_the_wall_ends_is_on_the_map():
    for center in (LEVEL.start, LEVEL.target_center, *UNBOUNDS):
        assert abs(center[0]) < config.WORLD_HALF_W and abs(center[1]) < config.WORLD_HALF_H


def test_level_select_lists_level_six_as_playable():
    cards = {lv.id: lv for lv in all_levels()}
    assert cards[6] is LEVEL


# --- without Unbound the target can't be reached --------------------------------------
def _fields():
    """Every constant push with |Fx|, |Fy| <= 3, plus a fixed sample of linear fields
    Fx = a*x + b*y + c, Fy = d*x + e*y + f with integer coefficients in [-3, 3]."""
    span = range(-3, 4)
    fields = [(0, 0, c, 0, 0, f) for c, f in itertools.product(span, span)]
    rng = random.Random(6)
    every = list(itertools.product(span, repeat=6))
    fields += rng.sample(every, 3000)             # about 10 s
    return fields


def test_no_field_reaches_the_target_without_unbound():
    bare = dataclasses.replace(LEVEL, pickups=())
    reached = []
    for a, b, c, d, e, f in _fields():
        flight = Flight(ForceField(a=a, b=b, c=c, d=d, e=e, f=f), SHIP, bare)
        while flight.running:
            flight.step()
        if flight.outcome is Outcome.REACHED:
            reached.append((a, b, c, d, e, f))
    assert reached == []
