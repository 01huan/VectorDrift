"""Within one physics step, events are taken in the order the ship meets them on its path.

The first black hole on the flown path ends the step: one teleport, the
velocity the ship had on entering it, no bounce after it applied, and only
the path flown before it counts for pickups and the target.
"""

import math
from dataclasses import replace

import pytest

from vector_drift import config
from vector_drift.data import SHIPS, get_level
from vector_drift.data_models import HoleSpec, ObstacleSpec, PickupSpec
from vector_drift.expr_parser import parse_expression
from vector_drift.physics import Flight, ForceField, Outcome

SHIP = SHIPS["ship01"]
WHITE = (5.0, -5.0)


def _field(fx, fy):
    return ForceField.from_exprs(parse_expression(fx), parse_expression(fy))


def _level(**changes):
    return replace(get_level(4), **changes)


def test_a_hole_before_a_rock_in_the_same_step_teleports_once_with_the_incoming_velocity():
    black = (-0.85, 0.0)
    level = _level(start=(-6.0, 0.0),
                   obstacles=(ObstacleSpec(center=(0.0, 0.0), radius=0.8),),
                   holes=(HoleSpec(black_center=black, white_center=WHITE, radius=0.3),))
    flight = Flight(_field("2000", "0"), SHIP, level)
    while flight.running and flight.teleports == 0:
        p0, before = (flight.x, flight.y), len(flight.trail)
        flight.step()

    assert flight.teleports == 1
    assert flight.bounces == 0
    assert flight.vx > 0.0 and flight.vy == 0.0           # the speed it went in with
    assert (flight.x, flight.y) == WHITE
    # The step's trail is the stroke's end at the hole entry, then the white hole.
    assert flight.trail[before - 1] == p0
    assert len(flight.trail) == before + 2
    (i,) = flight.trail_breaks
    assert i == before + 1
    entry = flight.trail[i - 1]
    assert math.dist(entry, black) == pytest.approx(0.3 + SHIP.hull_radius)
    assert entry[0] < black[0]                            # where it went in, not past it
    assert flight.trail[i] == WHITE


def _straight(holes=(), target=(9.0, 6.0), target_radius=0.1, pickups=()):
    """A ship at (-1, 0) flying +x at 2 m per step, no force."""
    level = _level(start=(-1.0, 0.0), obstacles=(), pickups=pickups, holes=holes,
                   target_center=target, target_radius=target_radius)
    flight = Flight(_field("0", "0"), SHIP, level)
    flight.vx = 2.0 / config.DT
    flight.step()
    return flight


def test_a_target_before_the_hole_is_reached_without_a_teleport():
    flight = _straight(holes=(HoleSpec(black_center=(0.6, 0.0), white_center=WHITE, radius=0.1),),
                       target=(0.0, 0.0))
    assert flight.outcome is Outcome.REACHED
    assert flight.teleports == 0 and not flight.hole_teleported
    assert flight.trail_breaks == []


def test_a_target_after_the_hole_is_not_reached():
    flight = _straight(holes=(HoleSpec(black_center=(-0.5, 0.0), white_center=WHITE, radius=0.1),),
                       target=(0.5, 0.0))
    assert flight.outcome is Outcome.RUNNING
    assert flight.teleports == 1
    assert (flight.x, flight.y) == WHITE


def test_the_first_hole_on_the_path_wins_over_the_list_order():
    far = HoleSpec(black_center=(0.5, 0.0), white_center=(-5.0, 5.0), radius=0.1)
    near = HoleSpec(black_center=(-0.5, 0.0), white_center=WHITE, radius=0.1)
    flight = _straight(holes=(far, near))
    assert flight.teleports == 1
    assert (flight.x, flight.y) == WHITE


def test_a_pickup_past_the_hole_entry_is_not_taken():
    flight = _straight(holes=(HoleSpec(black_center=(-0.5, 0.0), white_center=WHITE, radius=0.1),),
                       pickups=(PickupSpec(center=(0.5, 0.0), radius=0.1, kind="extratime"),))
    assert flight.teleports == 1
    assert flight.pickup_events == []
    assert not any(p.consumed for p in flight.pickups)


def test_a_pickup_before_the_hole_is_taken():
    flight = _straight(holes=(HoleSpec(black_center=(0.5, 0.0), white_center=WHITE, radius=0.1),),
                       pickups=(PickupSpec(center=(-0.5, 0.0), radius=0.1, kind="extratime"),))
    assert flight.teleports == 1
    assert [e["kind"] for e in flight.pickup_events] == ["extratime"]
