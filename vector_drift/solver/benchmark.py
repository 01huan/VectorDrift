"""Reproducible offline benchmark for solvers.

Generates never-before-seen random levels with independent seeds, runs a
solver on each, and reports:

* success rate
* mean solve time
* mean simulation count
* formula complexity (number of free parameters)
* stability (spread of success across seeds)

Pure PSO is the baseline; later models are compared against these numbers.
"""

from __future__ import annotations

import json
import math
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from ..data import LevelSpec
from ..level_presets import get_preset, is_dynamic_level
from ..random_level import generate_random_level
from .interface import Solver, SolveResult


@dataclass
class BenchmarkCase:
    """One level instance used in the benchmark."""

    level_id: int
    seed: int
    level: LevelSpec


@dataclass
class BenchmarkResult:
    """Aggregated statistics across benchmark cases."""

    solver_name: str
    solver_version: str
    n_cases: int
    successes: int
    success_rate: float
    mean_solve_time_s: float
    mean_simulations: int
    mean_params: float
    success_times_s: list[float] = field(default_factory=list)
    per_case: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "solver_name": self.solver_name,
            "solver_version": self.solver_version,
            "n_cases": self.n_cases,
            "successes": self.successes,
            "success_rate": self.success_rate,
            "mean_solve_time_s": self.mean_solve_time_s,
            "mean_simulations": self.mean_simulations,
            "mean_params": self.mean_params,
            "stability_success_rate_std": (
                statistics.pstdev(
                    [1.0 if c["success"] else 0.0 for c in self.per_case]
                )
                if self.per_case else 0.0
            ),
            "per_case": self.per_case,
        }

    def save_json(self, dest: Path | str) -> None:
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")


def generate_benchmark_levels(n: int = 12, level_id: int = 7,
                              base_seed: int = 20240101) -> list[BenchmarkCase]:
    """Generate ``n`` unseen random levels with independent seeds."""
    if not is_dynamic_level(level_id):
        raise ValueError(f"Level {level_id} is not a dynamic/random level")
    get_preset(level_id)  # validate preset exists
    cases = []
    for i in range(n):
        seed = base_seed + 1000 + i  # spaced seeds to avoid correlated layouts
        level = generate_random_level(level_id=level_id, seed=seed)
        cases.append(BenchmarkCase(level_id=level_id, seed=seed, level=level))
    return cases


def run_benchmark(solver: Solver, cases: list[BenchmarkCase],
                  time_budget_s: float | None = 30.0,
                  simulation_budget: int | None = None,
                  ) -> BenchmarkResult:
    """Run ``solver`` on every case and aggregate results."""
    per_case = []
    successes = 0
    total_time = 0.0
    total_sims = 0
    total_params = 0

    for case in cases:
        result: SolveResult = solver.solve(
            case.level,
            time_budget_s=time_budget_s,
            simulation_budget=simulation_budget,
            rng_seed=case.seed,
        )
        ok = bool(result.success)
        successes += 1 if ok else 0
        total_time += result.solve_time_s
        total_sims += result.total_simulations
        n_params = len(result.best.params) if result.best is not None else 0
        total_params += n_params
        per_case.append({
            "level_id": case.level_id,
            "seed": case.seed,
            "success": ok,
            "solve_time_s": result.solve_time_s,
            "simulations": result.total_simulations,
            "best_score": result.best_score,
            "n_params": n_params,
            "template": result.best.template if result.best else None,
            "message": result.message,
        })

    n = len(cases)
    return BenchmarkResult(
        solver_name=solver.name,
        solver_version=solver.version,
        n_cases=n,
        successes=successes,
        success_rate=(successes / n) if n else 0.0,
        mean_solve_time_s=(total_time / n) if n else 0.0,
        mean_simulations=(total_sims / n) if n else 0,
        mean_params=(total_params / n) if n else 0.0,
        success_times_s=[c["solve_time_s"] for c in per_case if c["success"]],
        per_case=per_case,
    )
