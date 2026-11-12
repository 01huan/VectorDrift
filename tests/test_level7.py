"""Level 7: a sealed column of rocks; a Shield gets the ship through or round it."""

import dataclasses
import math

import pytest

from vector_drift import config
from vector_drift.data import LEVELS, SHIPS, LevelSpec, all_levels, get_level
from vector_drift.physics import Flight, ForceField, Outcome
from vector_drift.pickups import discs_overlap

LEVEL = get_level(7)
SHIP = SHIPS[LEVEL.ship_id]
HULL = SHIP.hull_radius
ROCK_R = 0.8
ROCK_YS = (-6.2, -4.65, -3.1, -1.55, 0.0, 1.55, 3.1, 4.65, 6.2)
SHIELDS = {(3.5, 4.0), (3.5, -4.0)}


def rocks_by_y():
    return sorted(LEVEL.obstacles, key=lambda o: o.center[1])


def test_level_seven_is_first_shield():
    assert isinstance(LEVEL, LevelSpec) and LEVEL in LEVELS
    assert LEVEL.name == "First Shield"
    assert LEVEL.start == (7.0, 0.0)                    # this one flies right to left
    assert LEVEL.target_center == (-7.0, 0.0) and LEVEL.target_radius == 1.0
    assert LEVEL.ship_id == "ship01"
    assert LEVEL.time_limit == 10.0
    assert LEVEL.sections == () and LEVEL.holes == ()


def test_the_wall_is_one_column_at_x_zero():
    assert sorted(o.center for o in LEVEL.obstacles) == sorted((0.0, y) for y in ROCK_YS)
    assert all(o.radius == ROCK_R for o in LEVEL.obstacles)


def test_the_two_pickups_are_shields():
    assert {(p.center, p.radius, p.kind) for p in LEVEL.pickups} == {
        (c, 0.45, "shield") for c in SHIELDS}


def test_neighbouring_rocks_seal_the_middle():
    rocks = rocks_by_y()
    for a, b in zip(rocks, rocks[1:]):
        assert math.dist(a.center, b.center) <= a.radius + b.radius, (a.center, b.center)


def test_a_narrow_slit_is_left_at_each_edge():
    rocks = rocks_by_y()
    for end in (rocks[0], rocks[-1]):
        reach = abs(end.center[1]) + end.radius + HULL
        gap = config.WORLD_HALF_H - reach
        assert gap > 0.0, end.center
        assert gap == pytest.approx(0.3)


@pytest.mark.parametrize("name, center, radius", [
    ("target", LEVEL.target_center, LEVEL.target_radius),
    ("start", LEVEL.start, 0.0),
    *[(f"shield {c}", c, 0.45) for c in sorted(SHIELDS)],
])
def test_nothing_sits_in_a_rock(name, center, radius):
    for rock in LEVEL.obstacles:
        assert not discs_overlap(center, radius, rock.center, rock.radius + HULL), (name, rock.center)


def test_level_select_lists_level_seven_as_playable():
    cards = {lv.id: lv for lv in all_levels()}
    assert cards[7] is LEVEL


# --- reference answers --------------------------------------------------------------
# Linear fields Fx = a*x + b*y + c, Fy = d*x + e*y + f.
THROUGH = dict(a=-2.0, b=-1.0, c=3.0, d=2.0, e=-3.0, f=-0.5)   # F = (3 - 2x - y, -0.5 + 2x - 3y)
BOUNCE = dict(a=-2.0, b=0.5, c=-1.0, d=-3.0, e=-3.0, f=-2.0)   # F = (-1 - 2x + 0.5y, -2 - 3x - 3y)


def _fly(coeffs, level=LEVEL):
    flight = Flight(ForceField(**coeffs), SHIP, level)
    while flight.running:
        flight.step()
    return flight


def _shield_uses(flight):
    """('rock' | 'edge') per shield_used event, from where the shield broke."""
    rocks = {o.center for o in LEVEL.obstacles}
    kinds = []
    for event in flight.pickup_events:
        if event.get("kind") == "shield_used":
            kinds.append("rock" if tuple(event["center"]) in rocks else "edge")
    return kinds


def test_through_the_wall_with_a_shield():
    flight = _fly(THROUGH)
    assert flight.outcome is Outcome.REACHED
    assert _shield_uses(flight) == ["rock"]             # carried through the wall
    assert flight.time <= LEVEL.time_limit


def test_bouncing_off_the_edge_with_a_shield():
    flight = _fly(BOUNCE)
    assert flight.outcome is Outcome.REACHED
    assert _shield_uses(flight) == ["edge"]             # one bounce, then round the wall
    assert flight.time <= LEVEL.time_limit


@pytest.mark.parametrize("coeffs", [THROUGH, BOUNCE], ids=["through", "bounce"])
def test_reference_answers_need_the_shield(coeffs):
    bare = dataclasses.replace(LEVEL, pickups=())
    assert _fly(coeffs, bare).outcome is not Outcome.REACHED
