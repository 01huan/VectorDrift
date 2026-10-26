"""Unit tests for the offline solver package (stage 1: PSO baseline).

Fully offline: no network, no API key, no cloud API.
"""

import json
import math
import os
import tempfile
from pathlib import Path

import pytest

from vector_drift import config
from vector_drift.data import get_level
from vector_drift.physics import ForceField, Outcome
from vector_drift.expr_parser import parse_expression

from vector_drift.solver import (
    PSOSolver,
    PSOConfig,
    EvalConfig,
    evaluate_candidate,
    JSONLStore,
    StoreConfig,
    SimulationRecord,
    SimulationOutcome,
    SCHEMA_VERSION,
    get_template,
    template_keys,
    run_solver_async,
)
from vector_drift.solver.engine import _score, _time_budget_steps
from vector_drift.solver.templates import FieldTemplate

# Force headless for any transitive pygame import.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

LEVEL = get_level(1)  # static, no seed needed


# --------------------------------------------------------------------------- #
# Templates
# --------------------------------------------------------------------------- #
def test_template_keys_nonempty():
    assert template_keys()
    for key in template_keys():
        tpl = get_template(key)
        assert isinstance(tpl, FieldTemplate)
        assert tpl.param_names
        assert len(tpl.param_bounds) == len(tpl.param_names)


def test_rendered_formulas_parse():
    level = get_level(1)
    for key in template_keys():
        tpl = get_template(key)
        params = dict(zip(tpl.param_names, tpl.param_defaults))
        fx, fy = tpl.render(level, params)
        # Must be accepted by the game's own parser.
        parse_expression(fx)
        parse_expression(fy)


# --------------------------------------------------------------------------- #
# Engine / scoring
# --------------------------------------------------------------------------- #
def test_evaluate_candidate_returns_record():
    tpl = get_template("attract_damp")
    params = dict(zip(tpl.param_names, tpl.param_defaults))
    result = evaluate_candidate(
        level=LEVEL, template=tpl, params=params, iteration=0, source="test",
        config=EvalConfig(record_trajectory=True),
    )
    assert isinstance(result.record, SimulationRecord)
    assert result.record.schema_version == SCHEMA_VERSION
    assert result.record.success is (result.record.outcome == SimulationOutcome.REACHED)
    assert result.record.min_dist_to_target >= 0
    assert result.record.score >= 0
    if result.record.trajectory:
        assert result.record.trajectory[0].step == 0


def test_score_reached_outranks_nonreached():
    max_steps = 100
    reached = _score(Outcome.REACHED, 10, max_steps, 5.0)
    timeout = _score(Outcome.TIMEOUT, max_steps, max_steps, 0.1)
    assert reached > timeout


def test_score_faster_reached_is_better():
    max_steps = 100
    fast = _score(Outcome.REACHED, 10, max_steps, 5.0)
    slow = _score(Outcome.REACHED, 90, max_steps, 5.0)
    assert fast > slow


# --------------------------------------------------------------------------- #
# Store
# --------------------------------------------------------------------------- #
def test_store_roundtrip_and_compact():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "sims.jsonl"
        store = JSONLStore(StoreConfig(path=path, max_records=10, keep_best_n=5,
                                       keep_success_n=5, summary_only_after=2,
                                       auto_compact=True))
        tpl = get_template("attract_damp")
        params = dict(zip(tpl.param_names, tpl.param_defaults))
        records = []
        for i in range(5):
            result = evaluate_candidate(
                level=LEVEL, template=tpl, params=params, iteration=i, source="test",
                config=EvalConfig(record_trajectory=True),
            )
            records.append(result.record)
        store.add_many(records, include_trajectory=True)
        assert store.count() == 5
        info = store.schema_info()
        assert info == {"schema_name": "vectorsolver.simulation",
                        "schema_version": SCHEMA_VERSION}
        full = store.all_records(include_trajectory=True)
        assert len(full) == 5
        summary = store.all_records(include_trajectory=False)
        assert len(summary) == 5
        store.close()
        store2 = JSONLStore(StoreConfig(path=path))
        assert store2.count() == 5
        exported = store2.export_json(Path(d) / "export.json")
        assert exported == 5
        data = json.loads(Path(d, "export.json").read_text())
        assert data[0]["schema_version"] == SCHEMA_VERSION
        store2.close()


# --------------------------------------------------------------------------- #
# PSO solver interface
# --------------------------------------------------------------------------- #
def test_pso_is_solver_and_runs():
    solver = PSOSolver()
    assert solver.name == "pso"
    assert solver.version == "1.0.0"
    result = solver.solve(
        LEVEL, time_budget_s=10.0, simulation_budget=30, rng_seed=1,
    )
    assert isinstance(result.success, bool)
    assert result.total_simulations > 0
    assert result.solve_time_s >= 0
    assert result.message


def test_pso_success_means_reached():
    solver = PSOSolver(PSOConfig(template_key="target_attract",
                                 n_particles=8, max_simulations=40, seed=2))
    result = solver.solve(LEVEL, time_budget_s=10.0, simulation_budget=40, rng_seed=2)
    from vector_drift.data import SHIPS
    from vector_drift.physics import Flight
    if result.success:
        assert result.best is not None
        fx = parse_expression(result.best.fx_text)
        fy = parse_expression(result.best.fy_text)
        field = ForceField.from_exprs(fx, fy)
        flight = Flight(field, SHIPS[LEVEL.ship_id], LEVEL)
        while flight.running:
            flight.step()
        assert flight.outcome is Outcome.REACHED


def test_async_runner_returns_result():
    solver = PSOSolver(PSOConfig(n_particles=6, max_simulations=20, seed=3))
    job = run_solver_async(solver, LEVEL, time_budget_s=8.0,
                           simulation_budget=20, rng_seed=3)
    result = job.result_wait(timeout_s=20)
    assert result is not None
    assert isinstance(result.success, bool)
    assert job.running is False


# --------------------------------------------------------------------------- #
# Extended templates (compound nonlinear fields)
# --------------------------------------------------------------------------- #
def test_new_templates_registered_and_parse():
    for key in ("trig_poly", "rich_combo"):
        tpl = get_template(key)
        assert isinstance(tpl, FieldTemplate)
        assert len(tpl.param_bounds) == len(tpl.param_names)
        params = dict(zip(tpl.param_names, tpl.param_defaults))
        fx, fy = tpl.render(LEVEL, params)
        parse_expression(fx)
        parse_expression(fy)


def test_rich_combo_uses_nonlinear_terms():
    tpl = get_template("rich_combo")
    params = dict(zip(tpl.param_names, tpl.param_defaults))
    fx, fy = tpl.render(LEVEL, params)
    # Must contain the nonlinear building blocks the user asked for.
    assert "sin" in fx
    assert "log" in fy
    assert "x^2" in fx or "y^2" in fy
    assert "x*y" in fx


# --------------------------------------------------------------------------- #
# Extended search loop (high budget / cap / early stop)
# --------------------------------------------------------------------------- #
def test_high_budget_loop_respects_cap():
    # Small cap forces termination well before a solution is guaranteed.
    solver = PSOSolver(PSOConfig(template_key="target_attract",
                                 n_particles=8, max_simulations=24, seed=5))
    result = solver.solve(LEVEL, simulation_budget=24, rng_seed=5)
    assert result.total_simulations <= 24
    assert result.pso_iterations >= 1


def test_deep_budget_default_is_large():
    # The new baseline config must ask for a large simulation budget.
    assert PSOConfig().max_simulations >= 100_000



# --------------------------------------------------------------------------- #
# Scoring with add_time pickups: rank successes by absolute flight time
# --------------------------------------------------------------------------- #
def _score_level():
    """5 s limit, one add_time pickup at (0, 1): off the straight y = 0 path."""
    from vector_drift.data import LevelSpec, PickupSpec
    return LevelSpec(id=950, name="Score", start=(-7.0, 0.0), target_center=(7.0, 0.0),
                     target_radius=1.0, ship_id="ship01", time_limit=5.0,
                     pickups=(PickupSpec((0.0, 1.0), radius=0.6, kind="add_time"),))


def _poly_record(**coeffs):
    tpl = get_template("general_poly")
    params = dict(zip(tpl.param_names, tpl.param_defaults))
    params.update(coeffs)
    return evaluate_candidate(level=_score_level(), template=tpl, params=params,
                              config=EvalConfig(record_trajectory=False)).record


def test_faster_success_outscores_a_slower_one_that_took_extra_time():
    fast = _poly_record(c0=2.0)                        # straight along y = 0, misses the pickup
    slow = _poly_record(c0=0.9, d0=0.2266, d2=-0.412)  # bends through it and needs its 3 s
    assert fast.outcome == slow.outcome == SimulationOutcome.REACHED
    assert fast.time < 5.0 < slow.time
    assert fast.score > slow.score


def test_time_budget_is_the_limit_plus_every_add_time_pickup():
    from dataclasses import replace
    from vector_drift.data import PickupSpec
    from vector_drift.pickups import ADD_TIME_DURATION
    level = replace(_score_level(), time_limit=12.0, pickups=(
        PickupSpec((0.0, 3.0), kind="add_time"),
        PickupSpec((0.0, -3.0), kind="add_time"),
        PickupSpec((3.0, 0.0), kind="bomb"),
    ))
    expected = round((12.0 + 2 * ADD_TIME_DURATION) / config.DT)
    assert _time_budget_steps(level, round(12.0 / config.DT), config.DT) == expected
    assert _time_budget_steps(LEVEL, 1200, config.DT) == 1200   # no pickups: unchanged
