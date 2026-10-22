"""Unified solver interface.

Every solver (PSO, future regression model, neural network, genetic
programming, ...) implements :class:`Solver` and returns a
:class:`SolveResult`.  This keeps stages comparable: pure PSO remains the
baseline and later models can be swapped in behind the same call site.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from ..data import LevelSpec


class SolverError(RuntimeError):
    """Raised when a solver cannot produce a result."""


@dataclass(frozen=True)
class SimulationSpec:
    """Description of one force-field candidate to simulate.

    ``fx_text`` / ``fy_text`` are expression strings accepted by
    ``expr_parser.parse_expression``.  ``params`` are the free parameters
    searched by the solver (opaque to the interface).
    """

    template: str            # e.g. "attract_damp", "general_poly"
    fx_text: str
    fy_text: str
    params: dict[str, float] = field(default_factory=dict)
    source: str = "solver"   # "pso", "regression", "nn", "gp", "user", ...


@dataclass
class SolveResult:
    """Outcome of a :meth:`Solver.solve` call."""

    solver_name: str
    solver_version: str
    level_id: int
    level_seed: int | None
    success: bool
    best: SimulationSpec | None
    best_score: float
    simulations: list = field(default_factory=list)
    total_simulations: int = 0
    solve_time_s: float = 0.0
    pso_iterations: int = 0
    message: str = ""

    @property
    def best_outcome(self) -> str | None:
        if self.best is None:
            return None
        for sim in self.simulations:
            if sim.get("params") == self.best.params and sim.get("template") == self.best.template:
                return sim.get("outcome")
        return None


class Solver(ABC):
    """Abstract base for all offline solvers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable solver name."""

    @property
    @abstractmethod
    def version(self) -> str:
        """Solver implementation version (bumped when behaviour changes)."""

    @abstractmethod
    def solve(
        self,
        level: LevelSpec,
        *,
        time_budget_s: float | None = None,
        simulation_budget: int | None = None,
        rng_seed: int | None = None,
    ) -> SolveResult:
        """Search for a force field that solves ``level``.

        The returned :class:`SolveResult`` must contain *only* results
        verified with the formal game physics (see :mod:`vector_drift.physics`);
        a candidate is successful only if ``Outcome.REACHED``.
        """
