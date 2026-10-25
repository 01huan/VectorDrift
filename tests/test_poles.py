"""Passing through a point of infinite force flings the ship off the field."""
import math

import pytest

from vector_drift import config
from vector_drift.data import SHIPS, LevelSpec, ObstacleSpec, get_level
from vector_drift.expr_parser import parse_expression, singular_parts
from vector_drift.physics import Flight, ForceField, Outcome

LEVEL = get_level(1)                     # start (-7, 0), target (7, 0)
SHIP = SHIPS[LEVEL.ship_id]


def field(fx, fy):
    return ForceField.from_exprs(parse_expression(fx), parse_expression(fy))


def fly(fx, fy, level=LEVEL):
    flight = Flight(field(fx, fy), SHIP, level)
    while flight.running:
        flight.step()
    return flight


def flung(flight):
    """True if the flight ended with a straight shot to the edge."""
    return (flight.outcome is Outcome.OUT_OF_BOUNDS
            and math.dist(flight.trail[-2], flight.trail[-1]) > 1.0)


@pytest.mark.parametrize("text, parts", [
    ("tan(x)", [("call", "cos", (("var", "x"),))]),
    ("1/x^2", [("var", "x")]),
    ("x^-1", [("var", "x")]),
    ("log(abs(x))", [("var", "x")]),
    ("1/(2*x*y)", [("var", "x"), ("var", "y")]),
    ("1/sqrt(x)", [("var", "x")]),
    ("x^2 + sqrt(x) + sin(y)", []),
])
def test_singular_parts(text, parts):
    assert [p._node for p in singular_parts(parse_expression(text))] == parts


def test_tan_pole_flings_ship_straight_up_and_out():
    flight = fly("-x", "tan(x)")             # first pole on the way: x = -3pi/2
    assert flung(flight)
    pole, edge = flight.trail[-2], flight.trail[-1]
    assert math.isclose(pole[0], -1.5 * math.pi, abs_tol=1e-6)
    assert math.isclose(edge[1], config.WORLD_HALF_H)   # tan -> +inf just left of the pole
    assert abs(edge[0] - pole[0]) < 0.5


def test_fling_follows_the_force_on_the_approach_side():
    flight = fly("-x", "-tan(x)")
    assert flung(flight)
    assert math.isclose(flight.trail[-1][1], -config.WORLD_HALF_H)


@pytest.mark.parametrize("fx, fy, pole_x", [
    ("-x", "1/x", 0.0),
    ("-x", "1/(x+3)^2", -3.0),              # no sign change across this one
    ("-x", "1/abs(x+3)", -3.0),
    ("-x", "log(abs(x))", 0.0),             # infinite, however slowly
    ("-x", "1/tan(x)", -2 * math.pi),
    ("1", "1/sqrt(-x-3)", -3.0),            # infinite at the edge of its domain
])
def test_infinite_force_flings(fx, fy, pole_x):
    flight = fly(fx, fy)
    assert flung(flight)
    assert math.isclose(flight.trail[-2][0], pole_x, abs_tol=1e-6)


@pytest.mark.parametrize("fx, fy", [
    ("-x", "0"),                 # Fx = -x crosses zero at x = 0
    ("-x", "sin(x)/x"),          # removable: tends to 1
    ("-x", "x*log(abs(x))"),     # tends to 0
    ("-x", "floor(x) - 0.5"),    # bounded jump
])
def test_finite_force_is_not_a_pole(fx, fy):
    assert not flung(fly(fx, fy))


def test_domain_edge_with_finite_force_still_diverges():
    flight = fly("1", "sqrt(-x-3)")          # tends to 0, undefined past x = -3
    assert flight.outcome is Outcome.DIVERGED


def _about_to_cross_pole(vx, obstacles=()):
    level = LevelSpec(id=99, name="pole", start=(math.pi / 2 - 0.03, 0.0),
                      target_center=(7.0, 0.0), target_radius=1.0,
                      ship_id=LEVEL.ship_id, obstacles=obstacles)
    flight = Flight(field("0", "tan(x)"), SHIP, level)
    flight.vx = vx
    return flight


def test_crossing_pole_within_one_step_flings():
    flight = _about_to_cross_pole(6.0)       # this step ends at pi/2 + 0.02
    assert flight.step() is Outcome.OUT_OF_BOUNDS
    assert math.isclose(flight.y, config.WORLD_HALF_H)


def test_landing_right_next_to_pole_flings_too():
    # This step ends 1e-7 m short of pi/2, where |tan| is past MAX_FORCE.
    flight = _about_to_cross_pole((0.03 - 1e-7) / config.DT)
    assert flight.step() is Outcome.OUT_OF_BOUNDS
    assert math.isclose(flight.y, config.WORLD_HALF_H)


def test_bumper_before_pole_in_same_step_bounces_instead():
    # Bumper surface (radius + hull) at pi/2 - 0.01: hit at t = 0.4 < pole t = 0.6.
    bumper = ObstacleSpec(center=(math.pi / 2 + 0.5, 0.0), radius=0.51 - SHIP.hull_radius)
    flight = _about_to_cross_pole(6.0, (bumper,))
    assert flight.step() is Outcome.RUNNING
    assert flight.bounces == 1
    assert flight.vx < 0


def test_bumper_the_ship_is_already_inside_does_not_block_the_fling():
    # Same rule as the bounce: a bumper overlapping the ship at the start of
    # the step is not "hit first", so crossing pi/2 inside it still flings.
    inside = ObstacleSpec(center=(math.pi / 2, 0.0), radius=1.0)
    flight = _about_to_cross_pole(6.0, (inside,))
    assert flight.step() is Outcome.OUT_OF_BOUNDS
    assert math.isclose(flight.y, config.WORLD_HALF_H)
    assert flight.bounces == 0
