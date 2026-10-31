from pathlib import Path

from vector_drift.solver.benchmark import (
    BenchmarkCase,
    BenchmarkResult,
    generate_benchmark_levels,
    run_benchmark,
)
from vector_drift.solver.interface import SolveResult, SimulationSpec


class FakeSolver:
    name = "fake"
    version = "0.1"

    def solve(self, level, *, time_budget_s=None, simulation_budget=None, rng_seed=None):
        best = SimulationSpec(template="t", fx_text="x", fy_text="y", params={"a": 1.0})
        return SolveResult(
            solver_name=self.name,
            solver_version=self.version,
            level_id=level.id,
            level_seed=rng_seed,
            success=True,
            best=best,
            best_score=1.0,
            total_simulations=3,
            solve_time_s=0.1,
        )


def test_generate_benchmark_levels():
    cases = generate_benchmark_levels(n=2, level_id=7)
    assert len(cases) == 2
    assert all(c.level_id == 7 for c in cases)
    assert cases[0].seed != cases[1].seed


def test_generate_benchmark_levels_invalid():
    try:
        generate_benchmark_levels(n=1, level_id=1)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")


def test_run_benchmark_and_result():
    cases = generate_benchmark_levels(n=2, level_id=7)
    res = run_benchmark(FakeSolver(), cases, time_budget_s=1.0, simulation_budget=5)
    assert res.n_cases == 2
    assert res.successes == 2
    assert res.success_rate == 1.0
    assert res.mean_simulations == 3
    assert res.mean_params == 1.0
    d = res.to_dict()
    assert d["solver_name"] == "fake"
    assert "stability_success_rate_std" in d
    # save_json
    dest = Path("tmp_bench.json")
    try:
        res.save_json(dest)
        assert dest.exists()
    finally:
        if dest.exists():
            dest.unlink()


def test_benchmark_result_empty_cases():
    res = BenchmarkResult(
        solver_name="x", solver_version="1", n_cases=0, successes=0,
        success_rate=0.0, mean_solve_time_s=0.0, mean_simulations=0, mean_params=0.0,
    )
    assert res.to_dict()["stability_success_rate_std"] == 0.0
