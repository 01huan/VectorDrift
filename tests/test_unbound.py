"""Unbound: the life that takes it may fly past the map edge, up to twice the world."""

import math

import pytest

from vector_drift import config
from vector_drift.data import SHIPS, LevelSpec, PickupSpec
from vector_drift.expr_parser import parse_expression
from vector_drift.physics import Flight, ForceField, Outcome
from vector_drift.pickups import EFFECTS, PickupState, UNBOUND_OUTER_SCALE, unbound_outer_bounds

SHIP = SHIPS["ship01"]
OUTER_W = 2 * config.WORLD_HALF_W           # 20 m
OUTER_H = 2 * config.WORLD_HALF_H           # 15 m

# Picked up right after launch: the ship starts at (-7, 0) and heads up.
UNBOUND = PickupSpec(center=(-7.0, 0.8), radius=0.45, kind="unbound")
SHIELD = PickupSpec(center=(-7.0, 0.8), radius=0.45, kind="shield")

# y swings 0 -> 10 -> 0 (above the 7.5 m edge and back) over about 4.44 s while
# x accelerates from -7 to the target at 7: only an unbound ship gets there.
LOOP = ("1.4213", "10 - 2*y")


def level(*pickups):
    return LevelSpec(id=1, name="test", start=(-7.0, 0.0), target_center=(7.0, 0.0),
                     target_radius=1.0, ship_id="ship01", pickups=tuple(pickups))


def field(fx, fy):
    return ForceField.from_exprs(parse_expression(fx), parse_expression(fy))


def fly(fx, fy, lv, **kwargs):
    flight = Flight(field(fx, fy), SHIP, lv, **kwargs)
    while flight.running:
        flight.step()
    return flight


def highest(flight):
    return max(y for _, y in flight.trail)


def test_unbound_is_a_registered_pickup():
    assert "unbound" in EFFECTS
    assert UNBOUND_OUTER_SCALE == 2.0
    assert unbound_outer_bounds((config.WORLD_HALF_W, config.WORLD_HALF_H)) == (OUTER_W, OUTER_H)


def test_without_unbound_leaving_the_map_is_out_of_bounds():
    flight = fly(*LOOP, level())
    assert flight.outcome is Outcome.OUT_OF_BOUNDS
    assert not flight.unbound
    assert flight.y > config.WORLD_HALF_H


def test_unbound_ship_leaves_the_map_comes_back_and_reaches():
    flight = fly(*LOOP, level(UNBOUND))
    assert flight.unbound
    assert flight.outcome is Outcome.REACHED
    assert highest(flight) > config.WORLD_HALF_H + 2.0


def test_unbound_ship_past_the_outer_edge_is_out_of_bounds():
    flight = fly("0", "10", level(UNBOUND))
    assert flight.unbound
    assert flight.outcome is Outcome.OUT_OF_BOUNDS
    assert flight.y > OUTER_H
    # It did fly on past the map edge first: one step is far shorter than 7.5 m.
    assert flight.y < OUTER_H + 1.0


@pytest.mark.parametrize("fx, fy, axis, edge", [
    ("-10", "0", 0, -OUTER_W),
    ("0", "-10", 1, -OUTER_H),
])
def test_outer_edge_holds_in_every_direction(fx, fy, axis, edge):
    lv = LevelSpec(id=1, name="test", start=(0.0, 0.0), target_center=(9.0, 6.0),
                   target_radius=0.5, ship_id="ship01",
                   pickups=(PickupSpec(center=(0.0, 0.0), radius=0.45, kind="unbound"),))
    flight = fly(fx, fy, lv)
    assert flight.outcome is Outcome.OUT_OF_BOUNDS
    pos = (flight.x, flight.y)
    assert pos[axis] < edge


def test_a_new_flight_starts_without_unbound():
    pickups = [PickupState.from_spec(UNBOUND)]
    first = fly(*LOOP, level(UNBOUND), pickups=pickups)
    assert first.unbound and first.outcome is Outcome.REACHED

    # Next life, same (consumed) pickups as GameScene passes them: no effect.
    second = fly(*LOOP, level(UNBOUND), pickups=pickups)
    assert not second.unbound
    assert second.outcome is Outcome.OUT_OF_BOUNDS
    assert second.y < config.WORLD_HALF_H + 1.0


def test_shield_is_not_used_up_by_the_map_edge_while_unbound():
    flight = Flight(field(*LOOP), SHIP, level(SHIELD, UNBOUND))
    crossed = None
    while flight.running:
        flight.step()
        if crossed is None and flight.y > config.WORLD_HALF_H:
            crossed = flight.shield_remaining
    assert flight.unbound
    assert crossed is not None and crossed > 0.0
    assert not any(e.get("kind") == "shield_used" for e in flight.pickup_events)
    assert flight.outcome is Outcome.REACHED


def test_fling_while_unbound_goes_to_the_outer_edge():
    # tan(x) has a pole at x = -3pi/2 on the way right: the ship is flung up.
    lv = level(PickupSpec(center=(-6.9, 0.0), radius=0.45, kind="unbound"))
    flight = fly("-x", "tan(x)", lv)
    assert flight.unbound
    assert flight.outcome is Outcome.OUT_OF_BOUNDS
    pole, edge = flight.trail[-2], flight.trail[-1]
    assert math.isclose(pole[0], -1.5 * math.pi, abs_tol=1e-6)
    assert math.isclose(edge[1], OUTER_H)
    assert math.isclose(flight.y, OUTER_H)


def test_fling_without_unbound_still_stops_at_the_map_edge():
    flight = fly("-x", "tan(x)", level())
    assert flight.outcome is Outcome.OUT_OF_BOUNDS
    assert math.isclose(flight.trail[-1][1], config.WORLD_HALF_H)
