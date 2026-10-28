"""Level 4: a full-height rock wall at x = 0; the only way across is the wormhole."""

import dataclasses

import pytest

from vector_drift import config
from vector_drift.data import SHIPS, get_level
from vector_drift.expr_parser import parse_expression
from vector_drift.physics import Flight, ForceField, Outcome

BLACK, WHITE = (-3.0, 4.0), (2.0, 4.0)

# Reference solutions: up-right into the black hole, then bend down into the
# target after the white hole.
SMOOTH = ("2", "1 - 0.5*x - 2*y")
SPLIT = ("2", "2 - 6*max(x, 0)")


def _fly(level, fx, fy):
    field = ForceField.from_exprs(parse_expression(fx), parse_expression(fy))
    flight = Flight(field, SHIPS[level.ship_id], level)
    while flight.running:
        flight.step()
    return flight


def _hole(level):
    (pair,) = level.holes
    return pair


@pytest.mark.parametrize("solution", [SMOOTH, SPLIT])
def test_reference_solution_goes_through_the_wormhole_and_reaches(solution):
    flight = _fly(get_level(4), *solution)

    assert flight.outcome is Outcome.REACHED
    assert flight.bounces == 0
    assert WHITE in flight.trail                    # the teleport lands on the white hole


@pytest.mark.parametrize("solution", [SMOOTH, SPLIT])
def test_wall_is_closed_without_the_wormhole(solution):
    bare = dataclasses.replace(get_level(4), holes=())

    assert _fly(bare, *solution).outcome is not Outcome.REACHED


def test_wall_spans_the_world_with_no_gap_for_the_ship():
    level = get_level(4)
    rocks = sorted(level.obstacles, key=lambda o: o.center[1])

    assert all(o.center[0] == 0.0 for o in rocks)
    assert rocks[0].center[1] - rocks[0].radius < -config.WORLD_HALF_H
    assert rocks[-1].center[1] + rocks[-1].radius > config.WORLD_HALF_H
    for low, high in zip(rocks, rocks[1:]):
        # Discs touch or overlap (1e-9 for float noise), so no gap is left at all.
        assert high.center[1] - low.center[1] <= low.radius + high.radius + 1e-9


def test_holes_do_not_touch_rocks_start_or_target():
    level = get_level(4)
    black, white, radius = _hole(level)

    assert (black, white) == (BLACK, WHITE)
    for hole in (black, white):
        for rock in level.obstacles:
            gap = ((hole[0] - rock.center[0]) ** 2 + (hole[1] - rock.center[1]) ** 2) ** 0.5
            assert gap > radius + rock.radius
        tx, ty = level.target_center
        assert ((hole[0] - tx) ** 2 + (hole[1] - ty) ** 2) ** 0.5 > radius + level.target_radius
        assert hole != level.start


def test_no_constant_force_reaches_without_a_bounce():
    level = get_level(4)
    for i in range(-10, 11):
        for j in range(-10, 11):
            flight = _fly(level, str(i * 0.5), str(j * 0.5))
            assert not (flight.outcome is Outcome.REACHED and flight.bounces == 0), (i, j)
