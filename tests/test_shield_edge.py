"""Shield at the map edge: one elastic bounce, sharing the one protection with bumpers.

Driven through Flight.step so GameScene and the AI solver (both fly a Flight)
get the same rules.
"""

import math

import pytest

from vector_drift import config
from vector_drift.data import SHIPS, LevelSpec, ObstacleSpec, PickupSpec
from vector_drift.expr_parser import parse_expression
from vector_drift.physics import Flight, ForceField, Outcome
from vector_drift.pickups import SHIELD_DURATION

SHIP = SHIPS["ship01"]
HALF_W, HALF_H = config.WORLD_HALF_W, config.WORLD_HALF_H


def _level(start=(0.0, 0.0), obstacles=(), pickups=None, target=(9.0, -6.5)):
    if pickups is None:
        pickups = (PickupSpec(center=start, radius=0.3, kind="shield"),)
    return LevelSpec(id=1, name="test", start=start, target_center=target,
                     target_radius=0.3, ship_id="ship01",
                     obstacles=tuple(obstacles), pickups=tuple(pickups))


def _coasting(vx, vy, **kwargs):
    """No force, constant velocity; the shield pickup sits on the start point."""
    flight = Flight(ForceField(), SHIP, _level(**kwargs))
    flight.vx, flight.vy = vx, vy
    flight.step()
    return flight


def _used(flight):
    return [e for e in flight.pickup_events if e.get("kind") == "shield_used"]


def _inside(flight):
    return abs(flight.x) <= HALF_W and abs(flight.y) <= HALF_H


def _step_until_bounce(flight):
    """Step until the velocity changes (the edge bounce); return (before, after)."""
    before = (flight.vx, flight.vy)
    while flight.running and (flight.vx, flight.vy) == before:
        flight.step()
    return before, (flight.vx, flight.vy)


@pytest.mark.parametrize("vx, vy", [(20.0, 0.0), (-20.0, 0.0), (0.0, 20.0), (0.0, -20.0)])
def test_shield_bounces_off_each_edge(vx, vy):
    flight = _coasting(vx, vy)
    assert flight.shield_remaining > 0.0

    before, after = _step_until_bounce(flight)

    assert flight.outcome is Outcome.RUNNING          # bounced, not out of bounds
    assert _inside(flight)
    # Only the component normal to the edge flips; the speed is unchanged.
    assert after == (-before[0], before[1]) if vx else after == (before[0], -before[1])
    assert flight.shield_remaining == 0.0
    used = _used(flight)
    assert len(used) == 1
    assert flight.time < SHIELD_DURATION


def test_bounce_mirrors_the_position_back_inside():
    flight = _coasting(20.0, 0.0, start=(0.05, 0.0))
    while flight.running and flight.vx > 0.0:
        before = flight.x
        flight.step()
    # The step would have ended at before + 20*dt; it is mirrored about x = 10.
    overshoot = before + 20.0 * flight.dt - HALF_W
    assert overshoot > 0.0
    assert flight.x == pytest.approx(HALF_W - overshoot)
    assert _used(flight)[0]["center"][0] == pytest.approx(HALF_W)


def test_corner_flips_both_components():
    # x reaches 10 and y reaches 7.5 at the same moment (t = 0.495 s).
    flight = _coasting(20.0, 15.0, start=(0.1, 0.075))
    _step_until_bounce(flight)
    assert (flight.vx, flight.vy) == (-20.0, -15.0)
    assert flight.outcome is Outcome.RUNNING
    assert _inside(flight)
    assert flight.shield_remaining == 0.0
    assert len(_used(flight)) == 1


def test_second_edge_after_the_bounce_is_out_of_bounds():
    flight = _coasting(20.0, 0.0)
    while flight.running:
        flight.step()
    assert flight.outcome is Outcome.OUT_OF_BOUNDS
    assert flight.x < -HALF_W                          # bounced off x = 10, left at x = -10
    assert len(_used(flight)) == 1


def test_shield_used_on_a_bumper_leaves_none_for_the_edge():
    rock = ObstacleSpec(center=(3.0, 0.0), radius=0.5)
    flight = _coasting(20.0, 0.0, obstacles=[rock])
    while flight.running:
        flight.step()
    assert flight.outcome is Outcome.OUT_OF_BOUNDS
    assert flight.x > HALF_W                           # passed the rock, out on the right
    assert flight.bounces == 0
    assert len(_used(flight)) == 1


def test_shield_used_on_the_edge_leaves_none_for_a_bumper():
    rock = ObstacleSpec(center=(-5.0, 0.0), radius=0.5)
    flight = _coasting(20.0, 0.0, obstacles=[rock])
    _step_until_bounce(flight)                        # the edge at x = 10
    assert flight.shield_remaining == 0.0
    while flight.running and flight.bounces == 0:
        flight.step()
    assert flight.bounces == 1                         # the rock bounces it as usual
    assert flight.vx > 0.0
    assert flight.x > -5.0                             # not carried through
    assert len(_used(flight)) == 1


def test_expired_shield_does_not_bounce():
    flight = _coasting(3.0, 0.0)                       # reaches x = 10 at ~3.33 s
    while flight.running:
        flight.step()
    assert flight.time > SHIELD_DURATION
    assert flight.outcome is Outcome.OUT_OF_BOUNDS
    assert _used(flight) == []


def _field(fx, fy):
    return ForceField.from_exprs(parse_expression(fx), parse_expression(fy))


def test_fling_with_shield_bounces_once_then_fails_as_usual():
    # tan(x) has a pole at x = -3pi/2 on the way right: the ship is flung up.
    lv = _level(start=(-7.0, 0.0), target=(7.0, 0.0),
                pickups=(PickupSpec(center=(-7.0, 0.0), radius=0.3, kind="shield"),))
    flight = Flight(_field("-x", "tan(x)"), SHIP, lv)
    while flight.running and not _used(flight):
        flight.step()

    assert flight.outcome is Outcome.RUNNING           # bounced instead of out of bounds
    assert flight.shield_remaining == 0.0
    assert len(_used(flight)) == 1
    assert abs(flight.y) == pytest.approx(HALF_H)      # on the edge it was flung to
    assert flight.vy * flight.y < 0.0                  # heading back inside

    while flight.running:
        flight.step()
    assert flight.outcome is Outcome.OUT_OF_BOUNDS
    assert len(_used(flight)) == 1


def test_fling_without_shield_is_unchanged():
    lv = _level(start=(-7.0, 0.0), target=(7.0, 0.0), pickups=())
    flight = Flight(_field("-x", "tan(x)"), SHIP, lv)
    while flight.running:
        flight.step()
    assert flight.outcome is Outcome.OUT_OF_BOUNDS
    assert math.isclose(flight.trail[-1][1], HALF_H)


def test_unbound_takes_the_edge_and_keeps_the_shield():
    lv = _level(pickups=(PickupSpec(center=(0.0, 0.0), radius=0.3, kind="shield"),
                         PickupSpec(center=(0.0, 0.0), radius=0.3, kind="unbound")))
    flight = Flight(ForceField(), SHIP, lv)
    flight.vx = 20.0
    while flight.running and flight.x <= HALF_W + 1.0:
        flight.step()
    assert flight.unbound
    assert flight.outcome is Outcome.RUNNING
    assert flight.vx == 20.0                           # no bounce
    assert flight.shield_remaining > 0.0               # still there for a bumper
    assert _used(flight) == []
