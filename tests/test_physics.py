import pytest

from vector_drift import config
from vector_drift.data import SHIPS, get_level
from vector_drift.physics import Flight, ForceField, Outcome, segment_hits_circle

LEVEL = get_level(1)
SHIP = SHIPS[LEVEL.ship_id]


def fly(field):
    flight = Flight(field, SHIP, LEVEL)
    while flight.running:
        flight.step()
    return flight


def test_zero_field_times_out_after_exactly_1200_steps():
    flight = fly(ForceField())
    assert flight.outcome is Outcome.TIMEOUT
    assert flight.steps == 1200
    assert flight.time == pytest.approx(10.0)
    assert (flight.x, flight.y) == (-7.0, 0.0)


def test_fx_2_reaches_target():
    flight = fly(ForceField(c=2))
    assert flight.outcome is Outcome.REACHED
    # Continuous solution: -7 + t^2 = 5.8  ->  t = sqrt(12.8) ~ 3.578 s
    assert flight.time == pytest.approx(12.8 ** 0.5, abs=0.02)


def test_fx_1_reaches_within_10_seconds():
    flight = fly(ForceField(c=1))
    assert flight.outcome is Outcome.REACHED
    # -7 + t^2/2 = 5.8  ->  t = sqrt(25.6) ~ 5.06 s
    assert flight.time == pytest.approx(25.6 ** 0.5, abs=0.02)


def test_fx_0_2_is_too_slow():
    # needs sqrt(2 * 12.8 / 0.2) ~ 11.3 s
    flight = fly(ForceField(c=0.2))
    assert flight.outcome is Outcome.TIMEOUT


def test_resume_from_custom_start_at_rest():
    first = fly(ForceField(c=0.2))
    resumed = Flight(ForceField(c=2), SHIP, LEVEL, start=(first.x, first.y))
    assert (resumed.x, resumed.y) == (first.x, first.y)
    assert (resumed.vx, resumed.vy) == (0.0, 0.0)
    assert resumed.trail == [(first.x, first.y)]
    while resumed.running:
        resumed.step()
    assert resumed.outcome is Outcome.REACHED


def test_fx_minus_1_leaves_screen():
    flight = fly(ForceField(c=-1))
    assert flight.outcome is Outcome.OUT_OF_BOUNDS
    # -7 - t^2/2 = -10  ->  t = sqrt(6) ~ 2.449 s
    assert flight.time == pytest.approx(6 ** 0.5, abs=0.02)


def test_fast_ship_cannot_tunnel_through_target():
    # Second step jumps from x~0 to x~13.8: past the target and off screen.
    flight = fly(ForceField(c=1e5))
    assert flight.steps == 2
    assert flight.x > config.WORLD_HALF_W
    assert flight.outcome is Outcome.REACHED


def test_huge_coefficient_diverges():
    flight = fly(ForceField(a=1e308))
    assert flight.outcome is Outcome.DIVERGED


def test_mass_scales_arrival_time_not_path():
    heavy = SHIPS[LEVEL.ship_id].__class__(id="h", name="h", mass=4.0, hull_radius=0.2)
    light_flight = fly(ForceField(c=2))
    heavy_flight = Flight(ForceField(c=8), heavy, LEVEL)
    while heavy_flight.running:
        heavy_flight.step()
    assert heavy_flight.outcome is Outcome.REACHED
    assert heavy_flight.steps == light_flight.steps


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


def test_abort():
    flight = Flight(ForceField(c=2), SHIP, LEVEL)
    flight.advance(0.5)
    flight.abort()
    assert flight.outcome is Outcome.ABORTED
    steps = flight.steps
    flight.advance(0.5)
    assert flight.steps == steps


def test_time_left_counts_down():
    flight = Flight(ForceField(), SHIP, LEVEL)
    assert flight.time_left == pytest.approx(10.0)
    for _ in range(120):
        flight.step()
    assert flight.time_left == pytest.approx(9.0)


@pytest.mark.parametrize("p0, p1, hit", [
    ((0, 0), (10, 0), True),         # passes through the center
    ((0, 2), (10, 2), False),        # passes 2 m away
    ((0, 1.2), (10, 1.2), True),     # grazes exactly at the radius
    ((0, 0), (3, 0), False),         # stops short
    ((5, 0), (5, 0), True),          # zero-length segment inside
])
def test_segment_hits_circle(p0, p1, hit):
    assert segment_hits_circle(p0, p1, (5, 0), 1.2) is hit
