
import math
from types import SimpleNamespace

import pytest

from vector_drift import config
from vector_drift.data import SHIPS, get_level
from vector_drift.expr_parser import parse_expression
from vector_drift.physics import (
    Flight,
    ForceField,
    Outcome,
    segment_hits_circle,
)

LEVEL = get_level(1)
SHIP = SHIPS[LEVEL.ship_id]


def fly(field):
    flight = Flight(field, SHIP, LEVEL)
    while flight.running:
        flight.step()
    return flight


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

class ExpressionStub:
    """Simple expression object implementing evaluate(x, y)."""

    def __init__(self, function):
        self.function = function

    def evaluate(self, x, y):
        return self.function(x, y)


class BrokenField:
    """A force field that raises a chosen exception."""

    def __init__(self, exception):
        self.exception = exception

    def at(self, x, y):
        raise self.exception


class LinearFieldExpression:
    """Mimics a LinearExpr with x, y, and c coefficients."""

    def __init__(self, x, y, c):
        self.x = x
        self.y = y
        self.c = c


# ---------------------------------------------------------------------------
# Legacy linear force field
# ---------------------------------------------------------------------------

def test_default_force_field_is_zero():
    field = ForceField()

    assert field.at(0, 0) == (0.0, 0.0)
    assert field.at(10, -5) == (0.0, 0.0)


def test_legacy_linear_force_field():
    field = ForceField(a=2, b=3, c=4, d=5, e=6, f=7)

    assert field.at(1, 2) == (12.0, 24.0)
    assert field.at(-1, 0) == (2.0, 2.0)


def test_force_field_returns_floats():
    field = ForceField(c=2, f=3)

    fx, fy = field.at(1, 2)

    assert isinstance(fx, float)
    assert isinstance(fy, float)


def test_force_field_is_immutable():
    field = ForceField(c=2)

    with pytest.raises(AttributeError):
        field.c = 10


def test_force_field_rejects_non_finite_legacy_result():
    field = ForceField(a=1e308)

    with pytest.raises(ArithmeticError):
        field.at(2, 0)


@pytest.mark.parametrize(
    "coefficients",
    [
        {"a": float("nan")},
        {"b": float("inf")},
        {"c": float("-inf")},
        {"d": float("nan")},
        {"e": float("inf")},
        {"f": float("-inf")},
    ],
)
def test_force_field_rejects_nan_and_infinity(coefficients):
    field = ForceField(**coefficients)

    with pytest.raises(ArithmeticError):
        field.at(1, 1)


# ---------------------------------------------------------------------------
# General force expressions
# ---------------------------------------------------------------------------

def test_force_field_from_callable_expressions():
    field = ForceField.from_exprs(
        lambda x, y: 2 * x + y,
        lambda x, y: x - 3 * y,
    )

    assert field.at(2, 3) == (7.0, -7.0)


def test_force_field_from_evaluable_expressions():
    fx = ExpressionStub(lambda x, y: x**2 + y)
    fy = ExpressionStub(lambda x, y: x * y)

    field = ForceField.from_exprs(fx, fy)

    assert field.at(3, 2) == (11.0, 6.0)


def test_force_field_supports_mixed_expression_types():
    fx = lambda x, y: x + y
    fy = ExpressionStub(lambda x, y: x - y)

    field = ForceField.from_exprs(fx, fy)

    assert field.at(5, 2) == (7.0, 3.0)


def test_force_field_from_linear_expressions_preserves_coefficients():
    fx = LinearFieldExpression(x=1, y=2, c=3)
    fy = LinearFieldExpression(x=4, y=5, c=6)

    field = ForceField.from_exprs(fx, fy)

    assert field.fx_expr is None
    assert field.fy_expr is None
    assert (field.a, field.b, field.c) == (1, 2, 3)
    assert (field.d, field.e, field.f) == (4, 5, 6)
    assert field.at(2, 3) == (11.0, 29.0)


def test_force_field_general_expression_uses_current_position():
    field = ForceField.from_exprs(
        lambda x, y: x,
        lambda x, y: y,
    )

    assert field.at(1, 2) == (1.0, 2.0)
    assert field.at(3, 4) == (3.0, 4.0)


def test_force_field_rejects_missing_expression():
    field = ForceField.from_exprs(
        lambda x, y: x + y,
        None,
    )

    with pytest.raises(ValueError, match="Missing force expression"):
        field.at(1, 2)


def test_force_field_rejects_non_callable_expression():
    field = ForceField.from_exprs(123, lambda x, y: y)

    with pytest.raises(ArithmeticError, match="Force expression must"):
        field.at(1, 2)


@pytest.mark.parametrize(
    "result",
    [
        float("nan"),
        float("inf"),
        float("-inf"),
    ],
)
def test_force_field_rejects_non_finite_expression_result(result):
    field = ForceField.from_exprs(
        lambda x, y: result,
        lambda x, y: 0,
    )

    with pytest.raises(ArithmeticError, match="Force is not finite"):
        field.at(0, 0)


@pytest.mark.parametrize(
    "result",
    [
        None,
        object(),
        "not a number",
    ],
)
def test_force_field_rejects_invalid_expression_result(result):
    field = ForceField.from_exprs(
        lambda x, y: result,
        lambda x, y: 0,
    )

    with pytest.raises(ArithmeticError, match="Invalid force expression result"):
        field.at(0, 0)


def test_force_field_accepts_integer_expression_result():
    field = ForceField.from_exprs(
        lambda x, y: 3,
        lambda x, y: -4,
    )

    assert field.at(0, 0) == (3.0, -4.0)


def test_force_field_accepts_numeric_string_result():
    # Current implementation converts the expression result with float().
    field = ForceField.from_exprs(
        lambda x, y: "3.5",
        lambda x, y: "-2",
    )

    assert field.at(0, 0) == (3.5, -2.0)


def test_force_field_wraps_value_error_from_expression():
    def bad_expression(x, y):
        raise ValueError("bad input")

    field = ForceField.from_exprs(bad_expression, lambda x, y: 0)

    with pytest.raises(ArithmeticError, match="Invalid force expression result"):
        field.at(0, 0)


def test_force_field_wraps_type_error_from_expression():
    def bad_expression(x, y):
        raise TypeError("bad type")

    field = ForceField.from_exprs(bad_expression, lambda x, y: 0)

    with pytest.raises(ArithmeticError, match="Invalid force expression result"):
        field.at(0, 0)


def test_force_field_wraps_overflow_error_from_expression():
    def bad_expression(x, y):
        raise OverflowError("overflow")

    field = ForceField.from_exprs(bad_expression, lambda x, y: 0)

    with pytest.raises(ArithmeticError, match="Invalid force expression result"):
        field.at(0, 0)


def test_force_field_propagates_arithmetic_error_from_expression():
    def bad_expression(x, y):
        raise ZeroDivisionError("division by zero")

    field = ForceField.from_exprs(bad_expression, lambda x, y: 0)

    with pytest.raises(ZeroDivisionError):
        field.at(0, 0)


# ---------------------------------------------------------------------------
# Flight initialization and properties
# ---------------------------------------------------------------------------

def test_flight_starts_at_level_start():
    flight = Flight(ForceField(), SHIP, LEVEL)

    assert (flight.x, flight.y) == LEVEL.start
    assert (flight.vx, flight.vy) == (0.0, 0.0)
    assert flight.steps == 0
    assert flight.outcome is Outcome.RUNNING
    assert flight.trail == [LEVEL.start]


def test_flight_accepts_custom_start():
    start = (1.5, -2.5)
    flight = Flight(ForceField(), SHIP, LEVEL, start=start)

    assert (flight.x, flight.y) == start
    assert flight.trail == [start]


@pytest.mark.parametrize("dt", [0, -1, float("nan"), float("inf"), float("-inf")])
def test_flight_rejects_invalid_dt(dt):
    with pytest.raises(ValueError, match="dt must be a finite positive number"):
        Flight(ForceField(), SHIP, LEVEL, dt=dt)


@pytest.mark.parametrize("mass", [0, -1, float("nan"), float("inf"), float("-inf")])
def test_flight_rejects_invalid_ship_mass(mass):
    ship = SimpleNamespace(mass=mass, hull_radius=SHIP.hull_radius)

    with pytest.raises(
        ValueError,
        match="Ship mass must be a finite positive number",
    ):
        Flight(ForceField(), ship, LEVEL)


def test_flight_time_and_time_left_initially():
    flight = Flight(ForceField(), SHIP, LEVEL)

    assert flight.time == pytest.approx(0.0)
    assert flight.time_left == pytest.approx(LEVEL.time_limit)


def test_flight_force_property_returns_force():
    flight = Flight(ForceField(c=2, f=-3), SHIP, LEVEL)

    assert flight.force == (2.0, -3.0)


def test_flight_force_property_returns_nan_on_field_error():
    flight = Flight(
        BrokenField(ValueError("invalid field")),
        SHIP,
        LEVEL,
    )

    fx, fy = flight.force

    assert math.isnan(fx)
    assert math.isnan(fy)


def test_flight_running_property():
    flight = Flight(ForceField(), SHIP, LEVEL)

    assert flight.running is True

    flight.abort()

    assert flight.running is False


# ---------------------------------------------------------------------------
# Normal flight outcomes
# ---------------------------------------------------------------------------

def test_zero_field_times_out_after_exactly_1200_steps():
    flight = fly(ForceField())

    assert flight.outcome is Outcome.TIMEOUT
    assert flight.steps == 1200
    assert flight.time == pytest.approx(10.0)
    assert (flight.x, flight.y) == (-7.0, 0.0)


def test_fx_2_reaches_target():
    flight = fly(ForceField(c=2))

    assert flight.outcome is Outcome.REACHED
    # Continuous solution: -7 + t^2 = 5.8 -> t = sqrt(12.8).
    assert flight.time == pytest.approx(12.8**0.5, abs=0.02)


def test_fx_1_reaches_within_10_seconds():
    flight = fly(ForceField(c=1))

    assert flight.outcome is Outcome.REACHED
    # Continuous solution: -7 + t^2/2 = 5.8 -> t = sqrt(25.6).
    assert flight.time == pytest.approx(25.6**0.5, abs=0.02)


def test_fx_0_2_is_too_slow():
    flight = fly(ForceField(c=0.2))

    assert flight.outcome is Outcome.TIMEOUT


def test_resume_from_custom_start_at_rest():
    first = fly(ForceField(c=0.2))

    resumed = Flight(
        ForceField(c=2),
        SHIP,
        LEVEL,
        start=(first.x, first.y),
    )

    assert (resumed.x, resumed.y) == (first.x, first.y)
    assert (resumed.vx, resumed.vy) == (0.0, 0.0)
    assert resumed.trail == [(first.x, first.y)]

    while resumed.running:
        resumed.step()

    assert resumed.outcome is Outcome.REACHED


def test_fx_minus_1_leaves_screen():
    flight = fly(ForceField(c=-1))

    assert flight.outcome is Outcome.OUT_OF_BOUNDS
    assert flight.time == pytest.approx(6**0.5, abs=0.02)


def test_fast_ship_cannot_tunnel_through_target():
    flight = fly(ForceField(c=1e5))

    assert flight.steps == 2
    assert flight.x > config.WORLD_HALF_W
    assert flight.outcome is Outcome.REACHED


def test_huge_coefficient_diverges():
    flight = fly(ForceField(a=1e308))

    assert flight.outcome is Outcome.DIVERGED


def test_huge_finite_force_diverges_instead_of_tunneling():
    # tan(pi/2) ~= 1.6e16 is finite: without a clamp it tunnels to REACHED
    # in one step and then crashes the renderer with 1e12-scale coords.
    field = ForceField.from_exprs(
        ExpressionStub(lambda x, y: 1.633123935319537e16),
        ExpressionStub(lambda x, y: 0.0),
    )

    with pytest.raises(ArithmeticError):
        field.at(-7, 0)

    flight = fly(field)

    assert flight.outcome is Outcome.DIVERGED


def test_large_but_legit_force_still_flies():
    flight = fly(ForceField(c=1e5))

    assert flight.outcome is Outcome.REACHED


def test_force_at_exact_threshold_boundary():
    from vector_drift import config

    # Exactly at the ceiling: allowed. One ulp over: diverged.
    field = ForceField.from_exprs(
        ExpressionStub(lambda x, y: config.MAX_FORCE),
        ExpressionStub(lambda x, y: 0.0),
    )

    assert field.at(0, 0) == (config.MAX_FORCE, 0.0)

    over = ForceField.from_exprs(
        ExpressionStub(lambda x, y: config.MAX_FORCE * (1 + 1e-12)),
        ExpressionStub(lambda x, y: 0.0),
    )
    with pytest.raises(ArithmeticError):
        over.at(0, 0)


def test_step_displacement_boundary():
    from vector_drift import config

    assert config.MAX_STEP_M == 50.0
    # Sanity: 1e5 N moves ~14 m in a single step under dt=1/120, mass=1.
    dx = 1e5 * config.DT * config.DT

    assert dx < config.MAX_STEP_M


def test_mass_scales_arrival_time_not_path():
    heavy = SHIPS[LEVEL.ship_id].__class__(
        id="h",
        name="h",
        mass=4.0,
        hull_radius=0.2,
    )

    light_flight = fly(ForceField(c=2))

    heavy_flight = Flight(ForceField(c=8), heavy, LEVEL)
    while heavy_flight.running:
        heavy_flight.step()

    assert heavy_flight.outcome is Outcome.REACHED
    assert heavy_flight.steps == light_flight.steps


def test_general_expression_field_can_reach_target():
    field = ForceField.from_exprs(
        lambda x, y: 2,
        lambda x, y: 0,
    )

    flight = fly(field)

    assert flight.outcome is Outcome.REACHED


def test_level_2_is_reached_without_touching_the_bumper():
    level = get_level(2)
    field = ForceField.from_exprs(parse_expression("-y"), parse_expression("x + 6"))

    flight = Flight(field, SHIPS[level.ship_id], level)
    while flight.running:
        flight.step()

    assert flight.outcome is Outcome.REACHED
    assert flight.bounces == 0


# ---------------------------------------------------------------------------
# Divergence and invalid field results
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "exception",
    [
        ArithmeticError("arithmetic"),
        ValueError("value"),
        TypeError("type"),
        OverflowError("overflow"),
    ],
)
def test_flight_diverges_when_field_raises(exception):
    flight = Flight(BrokenField(exception), SHIP, LEVEL)

    outcome = flight.step()

    assert outcome is Outcome.DIVERGED
    assert flight.outcome is Outcome.DIVERGED
    assert flight.steps == 1
    assert (flight.x, flight.y) == LEVEL.start
    assert flight.trail == [LEVEL.start]
    assert flight.running is False


def test_flight_does_not_advance_after_divergence():
    flight = Flight(BrokenField(ValueError("invalid")), SHIP, LEVEL)

    flight.step()
    steps = flight.steps
    trail = list(flight.trail)

    flight.step()

    assert flight.steps == steps
    assert flight.trail == trail
    assert flight.outcome is Outcome.DIVERGED


def test_non_finite_force_causes_divergence():
    field = ForceField.from_exprs(
        lambda x, y: float("nan"),
        lambda x, y: 0,
    )

    flight = Flight(field, SHIP, LEVEL)

    assert flight.step() is Outcome.DIVERGED


# ---------------------------------------------------------------------------
# Fixed-step simulation and frame-rate independence
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("frame_dt", [1 / 30, 1 / 60, 1 / 144, 0.4])
def test_result_is_independent_of_frame_rate(frame_dt):
    field = ForceField(a=-0.3, b=0.1, c=2.0, d=0.2, e=-0.1, f=0.5)
    reference = fly(field)

    flight = Flight(field, SHIP, LEVEL)

    for _ in range(100_000):
        if not flight.running:
            break
        flight.advance(frame_dt)

    assert flight.outcome is reference.outcome
    assert flight.steps == reference.steps
    assert flight.trail == reference.trail


def test_advance_zero_does_not_step():
    flight = Flight(ForceField(c=2), SHIP, LEVEL)

    flight.advance(0)

    assert flight.steps == 0
    assert flight.time == pytest.approx(0.0)


@pytest.mark.parametrize("frame_dt", [-1, float("nan"), float("inf"), float("-inf")])
def test_advance_rejects_invalid_frame_dt(frame_dt):
    flight = Flight(ForceField(), SHIP, LEVEL)

    with pytest.raises(
        ValueError,
        match="frame_dt must be a finite non-negative number",
    ):
        flight.advance(frame_dt)


def test_advance_accumulates_partial_steps():
    flight = Flight(ForceField(), SHIP, LEVEL)

    flight.advance(flight.dt / 2)
    assert flight.steps == 0

    flight.advance(flight.dt / 2)
    assert flight.steps == 1


def test_advance_does_not_step_after_timeout():
    flight = Flight(ForceField(), SHIP, LEVEL)

    while flight.running:
        flight.step()

    steps = flight.steps
    flight.advance(1.0)

    assert flight.steps == steps
    assert flight.outcome is Outcome.TIMEOUT


def test_abort():
    flight = Flight(ForceField(c=2), SHIP, LEVEL)

    flight.advance(0.5)
    flight.abort()

    assert flight.outcome is Outcome.ABORTED

    steps = flight.steps
    position = (flight.x, flight.y)
    trail = list(flight.trail)

    flight.advance(0.5)
    flight.step()

    assert flight.steps == steps
    assert (flight.x, flight.y) == position
    assert flight.trail == trail


def test_abort_does_not_override_finished_outcome():
    flight = fly(ForceField())

    assert flight.outcome is Outcome.TIMEOUT

    flight.abort()

    assert flight.outcome is Outcome.TIMEOUT


def test_time_left_counts_down():
    flight = Flight(ForceField(), SHIP, LEVEL)

    assert flight.time_left == pytest.approx(10.0)

    for _ in range(120):
        flight.step()

    assert flight.time_left == pytest.approx(9.0)


def test_time_left_never_becomes_negative():
    flight = fly(ForceField())

    assert flight.time_left == 0.0


# ---------------------------------------------------------------------------
# Segment-circle collision
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "p0, p1, hit",
    [
        ((0, 0), (10, 0), True),       # Passes through the center.
        ((0, 2), (10, 2), False),      # Passes 2 m away.
        ((0, 1.2), (10, 1.2), True),   # Tangent to the circle.
        ((0, 0), (3, 0), False),       # Stops short.
        ((5, 0), (5, 0), True),        # Zero-length segment inside.
        ((0, 0), (10, 0), True),       # Circle center lies on segment.
        ((0, 0), (1, 0), False),       # Segment outside circle.
        ((4.0, 0), (4.0, 0), True),
        ((3.0, 0), (3.0, 0), False),
    ],
)
def test_segment_hits_circle(p0, p1, hit):
    assert segment_hits_circle(p0, p1, (5, 0), 1.2) is hit


def test_segment_hits_circle_is_direction_independent():
    p0 = (0, 0)
    p1 = (10, 0)
    center = (5, 0)

    assert segment_hits_circle(p0, p1, center, 1.2)
    assert segment_hits_circle(p1, p0, center, 1.2)


def test_segment_hits_circle_with_center_at_endpoint():
    assert segment_hits_circle(
        (0, 0),
        (5, 0),
        (5, 0),
        1.2,
    )


def test_segment_hits_circle_with_zero_radius():
    assert segment_hits_circle(
        (0, 0),
        (10, 0),
        (5, 0),
        0,
    )


def test_segment_misses_circle_with_zero_radius():
    assert not segment_hits_circle(
        (0, 0),
        (10, 0),
        (5, 1),
        0,
    )


# ---------------------------------------------------------------------------
# Starting inside a bumper
# ---------------------------------------------------------------------------

def test_flight_starting_inside_a_bumper_coasts_out_without_bouncing():
    # E.g. a launch resumed after a timeout where penetrate had carried the
    # ship into a bumper. No force, 2 m/s: it must leave the bumper as if it
    # were not there, without bounces or extra trail points.
    from vector_drift.data import LevelSpec, ObstacleSpec
    bumper = ObstacleSpec(center=(0.0, 0.0), radius=1.0)
    level = LevelSpec(id=990, name="Inside", start=(0.0, 0.0), target_center=(9.0, 6.0),
                      target_radius=0.5, ship_id=LEVEL.ship_id, obstacles=(bumper,))
    flight = Flight(ForceField(), SHIP, level)
    flight.vx = 2.0
    reach = bumper.radius + SHIP.hull_radius
    while flight.running and math.dist((flight.x, flight.y), bumper.center) < reach:
        flight.step()
    assert flight.running
    assert flight.bounces == 0
    assert (flight.vx, flight.vy) == (2.0, 0.0)
    assert len(flight.trail) == flight.steps + 1
