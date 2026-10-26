"""Particle Swarm Optimization solver (stage-1 baseline).

Pure offline, deterministic given a seed.  Searches the numeric parameters of
a force-field template; the formal game physics decides success.

This remains the baseline against which later models (regression, NN, GP, ...)
are compared.
"""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass

from ..data import LevelSpec
from .data import SimulationOutcome
from .engine import EvalConfig, evaluate_candidate
from .interface import Solver, SolveResult, SimulationSpec, SolverError
from .templates import FieldTemplate, get_template


@dataclass
class PSOConfig:
    """Hyper-parameters for the PSO search.

    The solver keeps searching until a candidate reaches the target
    (``Outcome.REACHED``) or ``max_simulations`` simulations have been run,
    whichever comes first.  This avoids ``"too many failures"``: a hard cap
    (e.g. 100 000) bounds the cost while the search keeps going.
    """

    template_key: str = "rich_combo"
    n_particles: int = 50
    max_simulations: int = 100_000
    inertia: float = 0.5
    cognitive: float = 1.5
    social: float = 1.5
    velocity_scale: float = 0.15
    time_budget_s: float | None = None
    simulation_budget: int | None = None
    early_stop_on_success: bool = True
    seed: int | None = None
    # Stall recovery: if the global best does not improve for this many
    # iterations, re-scatter part of the swarm to escape local optima.
    stall_limit: int = 25
    restart_on_stall: bool = True


class Particle:
    __slots__ = ("pos", "vel", "best_pos", "best_score", "score")

    def __init__(self, pos: list[float], vel: list[float]):
        self.pos = pos
        self.vel = vel
        self.best_pos = list(pos)
        self.best_score = -math.inf
        self.score = -math.inf


class PSOSolver(Solver):
    """Standard PSO over force-field template parameters."""

    def __init__(self, config: PSOConfig | None = None):
        self._config = config or PSOConfig()

    @property
    def name(self) -> str:
        return "pso"

    @property
    def version(self) -> str:
        return "1.0.0"

    def solve(
        self,
        level: LevelSpec,
        *,
        time_budget_s: float | None = None,
        simulation_budget: int | None = None,
        rng_seed: int | None = None,
    ) -> SolveResult:
        cfg = self._config
        if time_budget_s is not None:
            cfg.time_budget_s = time_budget_s
        if simulation_budget is not None:
            cfg.simulation_budget = simulation_budget
        seed = rng_seed if rng_seed is not None else cfg.seed
        rng = random.Random(seed)

        template = get_template(cfg.template_key)
        bounds = list(template.param_bounds)
        n_dim = len(bounds)
        if n_dim == 0:
            raise SolverError(f"Template {cfg.template_key} has no parameters")

        start = time.perf_counter()
        simulations: list = []
        best_spec: SimulationSpec | None = None
        best_score = -math.inf
        iterations = 0
        total_simulations = 0

        particles: list[Particle] = []
        for _ in range(cfg.n_particles):
            pos = [rng.uniform(lo, hi) for lo, hi in bounds]
            vel = [rng.uniform(-1.0, 1.0) * (hi - lo) * cfg.velocity_scale
                   for lo, hi in bounds]
            particles.append(Particle(pos, vel))

        global_best_pos: list[float] | None = None
        global_best_score = -math.inf

        def _evaluate(particle: Particle, iteration: int):
            nonlocal total_simulations
            params = dict(zip(template.param_names, particle.pos))
            result = evaluate_candidate(
                level=level,
                template=template,
                params=params,
                iteration=iteration,
                source="pso",
                config=EvalConfig(record_trajectory=True),
            )
            simulations.append(result.record)
            total_simulations += 1
            return result.record.score, result.record

        # Evaluate initial swarm.
        for p in particles:
            score, rec = _evaluate(p, 0)
            p.score = score
            p.best_score = score
            p.best_pos = list(p.pos)
            if score > global_best_score:
                global_best_score = score
                global_best_pos = list(p.pos)

        iterations = 0
        success_found = False
        stall_count = 0
        prev_global_best = -math.inf
        # Hard cap on simulations: never run forever.  Caller may pass a
        # smaller simulation_budget; otherwise fall back to max_simulations.
        max_sim = (cfg.simulation_budget
                   if cfg.simulation_budget is not None
                   else cfg.max_simulations)

        while total_simulations < max_sim and not success_found:
            iterations += 1
            # Budget / time guards.
            if cfg.simulation_budget is not None and \
                    total_simulations >= cfg.simulation_budget:
                break
            if cfg.time_budget_s is not None and \
                    (time.perf_counter() - start) >= cfg.time_budget_s:
                break

            r1 = [rng.random() for _ in range(n_dim)]
            r2 = [rng.random() for _ in range(n_dim)]
            for p in particles:
                for i in range(n_dim):
                    cognitive_v = (cfg.cognitive * r1[i] *
                                   (p.best_pos[i] - p.pos[i]))
                    social_v = (cfg.social * r2[i] *
                                (global_best_pos[i] - p.pos[i]))
                    p.vel[i] = (cfg.inertia * p.vel[i] + cognitive_v +
                                social_v)
                    lo, hi = bounds[i]
                    vmax = (hi - lo) * cfg.velocity_scale
                    p.vel[i] = max(-vmax, min(vmax, p.vel[i]))
                    p.pos[i] = p.pos[i] + p.vel[i]
                    p.pos[i] = max(lo, min(hi, p.pos[i]))

            for p in particles:
                score, rec = _evaluate(p, iterations)
                p.score = score
                if score > p.best_score:
                    p.best_score = score
                    p.best_pos = list(p.pos)
                if score > global_best_score:
                    global_best_score = score
                    global_best_pos = list(p.pos)

                if rec.outcome == SimulationOutcome.REACHED:
                    success_found = True
                    if cfg.early_stop_on_success:
                        break

            # Stall detection & recovery: if the global best does not improve
            # for stall_limit iterations, re-scatter part of the swarm so the
            # search does not stall on "too many failures".
            if global_best_score > prev_global_best:
                prev_global_best = global_best_score
                stall_count = 0
            else:
                stall_count += 1
                if (cfg.restart_on_stall and stall_count >= cfg.stall_limit
                        and not success_found):
                    elite = list(global_best_pos) if global_best_pos is not None else None
                    for p in particles:
                        if rng.random() < 0.5:
                            p.pos = [rng.uniform(lo, hi) for lo, hi in bounds]
                            p.vel = [rng.uniform(-1.0, 1.0) * (hi - lo) *
                                     cfg.velocity_scale for lo, hi in bounds]
                            p.best_pos = list(p.pos)
                            p.best_score = -math.inf
                    if elite is not None and particles:
                        particles[0].pos = list(elite)
                        particles[0].best_pos = list(elite)
                    stall_count = 0

        if global_best_pos is not None:
            params = dict(zip(template.param_names, global_best_pos))
            fx_text, fy_text = template.render(level, params)
            best_spec = SimulationSpec(
                template=template.key,
                fx_text=fx_text,
                fy_text=fy_text,
                params=params,
                source="pso",
            )
            best_score = global_best_score

        solve_time = time.perf_counter() - start
        success = any(r.success for r in simulations)
        best_outcome = None
        for r in simulations:
            if r.success:
                best_outcome = r.outcome
                break

        message = (f"{total_simulations} simulations over {iterations} "
                   f"iterations in {solve_time:.2f}s; "
                   f"best score {best_score:.4f}")
        if success:
            message += "; SOLVED"

        return SolveResult(
            solver_name=self.name,
            solver_version=self.version,
            level_id=level.id,
            level_seed=getattr(level, "seed", None),
            success=success,
            best=best_spec,
            best_score=float(best_score),
            simulations=simulations,
            total_simulations=total_simulations,
            solve_time_s=solve_time,
            pso_iterations=iterations,
            message=message,
        )
