"""Level 3: the target sits in a closed ring of bumpers; a shockwave opens it."""

import dataclasses

import pytest

from vector_drift.data import SHIPS, get_level
from vector_drift.expr_parser import parse_expression
from vector_drift.physics import Flight, ForceField, Outcome
from vector_drift.pickups import SHOCKWAVE_BLAST_RADIUS, obstacles_hit_by_blast

TOP, BOTTOM = (3.2, 3.6), (3.2, -3.6)

# Reference solutions: the upper path takes the top shockwave, the mirrored
# lower path takes the bottom one.
UPPER = ("3", "-x - 2*y")
LOWER = ("3", "x - 2*y")

BLASTED = {
    TOP: {(3.9, 0.0), (4.51, 1.67), (6.05, 2.56)},
    BOTTOM: {(3.9, 0.0), (4.51, -1.67), (6.05, -2.56)},
}


def _fly(level, fx, fy):
    field = ForceField.from_exprs(parse_expression(fx), parse_expression(fy))
    flight = Flight(field, SHIPS[level.ship_id], level)
    while flight.running:
        flight.step()
    return flight


def _consumed(flight):
    return {p.center for p in flight.pickups if p.consumed}


@pytest.mark.parametrize("solution, taken", [(UPPER, TOP), (LOWER, BOTTOM)])
def test_reference_solution_takes_one_shockwave_and_reaches(solution, taken):
    flight = _fly(get_level(3), *solution)

    assert flight.outcome is Outcome.REACHED
    assert flight.bounces == 0
    assert _consumed(flight) == {taken}
    assert len(flight.obstacle_specs) == 6


@pytest.mark.parametrize("solution", [UPPER, LOWER])
def test_ring_is_closed_without_shockwaves(solution):
    bare = dataclasses.replace(get_level(3), pickups=())

    assert _fly(bare, *solution).outcome is not Outcome.REACHED


def test_each_shockwave_blasts_the_three_nearest_bumpers():
    level = get_level(3)

    assert {p.center for p in level.pickups} == {TOP, BOTTOM}
    for pickup in level.pickups:
        _, destroyed = obstacles_hit_by_blast(pickup.center, SHOCKWAVE_BLAST_RADIUS,
                                              level.obstacles)
        assert {ob.center for ob in destroyed} == BLASTED[pickup.center]
