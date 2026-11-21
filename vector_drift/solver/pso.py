"""Particle Swarm Optimization solver (stage-1 baseline).

Pure offline, deterministic given a seed.  Searches the numeric parameters of
a force-field template; the formal game physics decides success.

This remains the baseline against which later models (regression, NN, GP, ...)
are compared.
"""

from __future__ import annotations

import math
import multiprocessing
import os
import random
import threading
import time
import concurrent.futures
from dataclasses import dataclass

from ..data import LevelSpec
from .data import SimulationOutcome
from .engine import EvalConfig, evaluate_candidate
from .interface import Solver, SolveResult, SimulationSpec, SolverError
from .templates import get_template


@dataclass
class PSOConfig:
    """Hyper-parameters for the PSO search.

    The solver keeps searching until a candidate reaches the target
    (``Outcome.REACHED``) or ``max_simulations`` simulations have been run,
    whichever comes first.  This avoids ``"too many failures"``: a hard cap
    (e.g. 100 000) bounds the cost while the search keeps going.
    """

    template_key: str = "all_in_one"
    n_particles: int = 150
    max_simulations: int = 100000
    inertia: float = 0.5
    cognitive: float = 1.5
    social: float = 1.5
    velocity_scale: float = 0.15
    time_budget_s: float | None = None
    simulation_budget: int | None = None
    early_stop_on_success: bool = False
    seed: int | None = None
    # Evaluation cap: limits steps per flight (None = the level's full limit)
    # and whether trajectories are recorded. The validator uses a short cap
    # so a "plausible solution" probe never dominates generation time.
    max_steps: int | None = None
    record_trajectory: bool = False
    # Stall recovery: if the global best does not improve for this many
    # iterations, re-scatter part of the swarm to escape local optima.
    stall_limit: int = 25
    restart_on_stall: bool = True
    n_workers: int | None = None  # None -> os.cpu_count() (multiprocessing)


class Particle:
    __slots__ = ("pos", "vel", "best_pos", "best_score", "score")

    def __init__(self, pos: list[float], vel: list[float]):
        self.pos = pos
        self.vel = vel
        self.best_pos = list(pos)
        self.best_score = -math.inf
        self.score = -math.inf


# Worker-global state, populated once per pool by the initializer so the level
# (and template key) are pickled a single time instead of once per task.
_WORKER_LEVEL = None
_WORKER_TEMPLATE_KEY = None
_WORKER_TEMPLATE = None
_WORKER_MAX_STEPS = None
_WORKER_RECORD_TRAJECTORY = True


class _Cancelled(Exception):
    """Raised inside a solve when its job is cancelled."""


def _watch_parent(is_alive, exit_fn=os._exit, interval_s: float = 1.0):
    """Block until ``is_alive()`` turns false, then call ``exit_fn(0)``."""
    while is_alive():
        time.sleep(interval_s)
    exit_fn(0)


def _init_worker(level, template_key, max_steps=None, record_trajectory=True):
    global _WORKER_LEVEL, _WORKER_TEMPLATE_KEY, _WORKER_TEMPLATE
    global _WORKER_MAX_STEPS, _WORKER_RECORD_TRAJECTORY
    _WORKER_LEVEL = level
    _WORKER_TEMPLATE_KEY = template_key
    _WORKER_MAX_STEPS = max_steps
    _WORKER_RECORD_TRAJECTORY = record_trajectory
    from .templates import get_template
    _WORKER_TEMPLATE = get_template(template_key)
    # If the game is killed outright it cannot shut the pool down, so each
    # worker ends itself once its parent process is gone.
    parent = multiprocessing.parent_process()
    if parent is not None:
        threading.Thread(target=_watch_parent, args=(parent.is_alive,),
                         name="solver-parent-watchdog", daemon=True).start()


def _eval_worker(payload):
    """Top-level (picklable) worker for multiprocessing particle evaluation."""
    params, iteration = payload
    level = _WORKER_LEVEL
    template = _WORKER_TEMPLATE
    from .engine import evaluate_candidate, EvalConfig
    result = evaluate_candidate(
        level=level,
        template=template,
        params=params,
        iteration=iteration,
        source="pso",
        config=EvalConfig(record_trajectory=_WORKER_RECORD_TRAJECTORY,
                          max_steps=_WORKER_MAX_STEPS),
    )
    return result.record


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
        progress_callback=None,
        cancel_event: threading.Event | None = None,
    ) -> SolveResult:
        cfg = self._config

        def _check_cancel():
            if cancel_event is not None and cancel_event.is_set():
                raise _Cancelled
        # Budgets are local to this call: the solver instance may be reused
        # across calls and must not inherit stale budgets from earlier ones.
        time_budget = cfg.time_budget_s if time_budget_s is None else time_budget_s
        simulation_budget = (cfg.simulation_budget
                             if simulation_budget is None
                             else simulation_budget)

        seed = rng_seed if rng_seed is not None else cfg.seed
        if seed is None:
            # Avoid None-typed seeds so restart bookkeeping can always advance.
            import random as _rng_seed_helper
            seed = _rng_seed_helper.randrange(1 << 32)
        run_seed = seed
        rng = random.Random(run_seed)

        template = get_template(cfg.template_key)
        bounds = list(template.param_bounds)
        n_dim = len(bounds)
        if n_dim == 0:
            raise SolverError(f"Template {cfg.template_key} has no parameters")

        start = time.perf_counter()
        simulations: list = []
        best_spec: SimulationSpec | None = None
        best_score = -math.inf
        best_coins = 0
        iterations = 0
        total_simulations = 0

        # Total gold coins available on this level (best possible collection).
        total_money = 0
        for _p in getattr(level, "pickups", ()) or ():
            if getattr(_p, "kind", None) == "money":
                total_money += int(getattr(_p, "amount", 1) or 1)
        for _s in getattr(level, "sections", ()) or ():
            for _p in getattr(_s, "pickups", ()) or ():
                if getattr(_p, "kind", None) == "money":
                    total_money += int(getattr(_p, "amount", 1) or 1)

        particles: list[Particle] = []
        for _ in range(cfg.n_particles):
            pos = [rng.uniform(lo, hi) for lo, hi in bounds]
            vel = [
                rng.uniform(-1.0, 1.0) * (hi - lo) * cfg.velocity_scale
                for lo, hi in bounds
            ]
            particles.append(Particle(pos, vel))

        global_best_pos: list[float] | None = None
        global_best_score = -math.inf
        global_best_money = 0
        # Tracks whether ANY candidate was ever verified REACHED, across the
        # restarts the search does after a success (which clear ``simulations``).
        any_success = False

        def _evaluate(particle: Particle, iteration: int):
            nonlocal total_simulations

            params = dict(zip(template.param_names, particle.pos))
            result = evaluate_candidate(
                level=level,
                template=template,
                params=params,
                iteration=iteration,
                source="pso",
                config=EvalConfig(record_trajectory=cfg.record_trajectory,
                                  max_steps=cfg.max_steps),
            )
            simulations.append(result.record)
            total_simulations += 1
            return result.record.score, result.record

        workers = cfg.n_workers or (os.cpu_count() or 1)

        # Default to the configured simulation cap; ``simulation_budget``
        # overrides it. ``time_budget_s`` is an independent wall-clock cap
        # applied in the loop below. (Previously the cap applied only when
        # a time budget was set, which made it dead code on the game's
        # un-budgeted AI-assistant path.)
        max_sim = (
            simulation_budget
            if simulation_budget is not None
            else cfg.max_simulations
        )
        if max_sim is not None and max_sim < 0:
            # A negative simulation budget means no simulations at all (the
            # particles[:max_sim] slices below would otherwise cut from the
            # end of the swarm).
            max_sim = 0

        success_found = False
        stall_count = 0
        prev_global_best = -math.inf

        def _publish_progress():
            if progress_callback is None or global_best_pos is None:
                return
            try:
                params = dict(zip(template.param_names, global_best_pos))
                fx_text, fy_text = template.render(level, params)
                spec = SimulationSpec(
                    template=template.key,
                    fx_text=fx_text,
                    fy_text=fy_text,
                    params=params,
                    source="pso",
                )
                res = SolveResult(
                    solver_name=self.name,
                    solver_version=self.version,
                    level_id=level.id,
                    level_seed=getattr(level, "seed", None),
                    success=False,
                    best=spec,
                    best_score=float(global_best_score),
                    simulations=[],
                    total_simulations=total_simulations,
                    solve_time_s=time.perf_counter() - start,
                    pso_iterations=iterations,
                    message=f"{total_simulations} simulations; best coins {global_best_money}",
                )
                progress_callback(res)
            except Exception:
                pass
        pool = None

        try:
            # Create the process pool once and reuse it for the entire solve.
            if workers > 1 and (max_sim is None or max_sim > 0):
                pool = concurrent.futures.ProcessPoolExecutor(
                    max_workers=workers,
                    initializer=_init_worker,
                    initargs=(level, cfg.template_key, cfg.max_steps,
                              cfg.record_trajectory),
                )

            def _evaluate_batch(
                batch_particles: list[Particle],
                iteration: int,
            ):
                nonlocal total_simulations

                if not batch_particles:
                    return []

                # Split the batch into one chunk per worker to reduce IPC overhead.
                n = len(batch_particles)
                n_chunks = min(workers*8, n)
                chunk_size = (n + n_chunks - 1) // n_chunks
                chunk_payloads = []
                for lo in range(0, n, chunk_size):
                    params_list = [dict(zip(template.param_names, p.pos))
                                   for p in batch_particles[lo:lo + chunk_size]]
                    chunk_payloads.append((params_list, iteration))

                if pool is not None:
                    futures = [pool.submit(_eval_chunk, payload) for payload in chunk_payloads]
                    # Wait in short slices so a cancel does not sit behind the batch.
                    pending = set(futures)
                    while pending:
                        _check_cancel()
                        if (time_budget is not None
                                and time.perf_counter() - start >= time_budget):
                            raise _Cancelled
                        _, pending = concurrent.futures.wait(pending, timeout=0.1)
                    records = [rec for f in futures for rec in f.result()]
                    simulations.extend(records)
                    total_simulations += len(records)
                    return [(rec.score, rec) for rec in records]

                results = []
                for p in batch_particles:
                    _check_cancel()
                    score, rec = _evaluate(p, iteration)
                    results.append((score, rec))
                return results

            # Evaluate the initial swarm, respecting the simulation budget.
            initial_count = len(particles) if max_sim is None else min(len(particles), max_sim)
            initial_particles = particles[:initial_count]

            initial_results = _evaluate_batch(initial_particles, 0)

            for p, (score, rec) in zip(initial_particles, initial_results):
                p.score = score
                p.best_score = score
                p.best_pos = list(p.pos)

                if rec.outcome == SimulationOutcome.REACHED:
                    any_success = True
                if score > global_best_score:
                    global_best_score = score
                    global_best_pos = list(p.pos)
                    global_best_money = int(getattr(rec, "money", 0))
                    _publish_progress()
                    _publish_progress()

                # Note: do not mark success_found here; the optimization loop
                # below still runs at least one iteration so the search/cap
                # behaviour is exercised even if the initial swarm already
                # reaches the target. Early stopping then applies from the
                # first optimization iteration onward.
            # Run PSO iterations until success, budget exhaustion, or timeout.
            while (max_sim is None or total_simulations < max_sim):
                _check_cancel()
                optimal_found = False
                if (
                    time_budget is not None
                    and time.perf_counter() - start >= time_budget
                ):
                    break

                if (
                    simulation_budget is not None
                    and total_simulations >= simulation_budget
                ):
                    break

                remaining = None if max_sim is None else (max_sim - total_simulations)
                if remaining is not None and remaining <= 0:
                    break

                iterations += 1

                r1 = [rng.random() for _ in range(n_dim)]
                r2 = [rng.random() for _ in range(n_dim)]

                for p in particles:
                    vel, pos, best = p.vel, p.pos, p.best_pos
                    for i in range(n_dim):
                        lo, hi = bounds[i]
                        vmax = (hi - lo) * cfg.velocity_scale
                        v = (cfg.inertia * vel[i]
                             + cfg.cognitive * r1[i] * (best[i] - pos[i])
                             + cfg.social * r2[i] * (global_best_pos[i] - pos[i]))
                        vel[i] = max(-vmax, min(vmax, v))
                        pos[i] = max(lo, min(hi, pos[i] + vel[i]))

                # Never submit more evaluations than the remaining budget.
                batch_particles = (particles if remaining is None
                                   else particles[:min(len(particles), remaining)])
                batch_results = _evaluate_batch(batch_particles, iterations)

                for p, (score, rec) in zip(batch_particles, batch_results):
                    p.score = score

                    if score > p.best_score:
                        p.best_score = score
                        p.best_pos = list(p.pos)

                    if rec.outcome == SimulationOutcome.REACHED:
                        any_success = True

                    if score > global_best_score:
                        global_best_score = score
                        global_best_pos = list(p.pos)
                        global_best_money = int(getattr(rec, "money", 0))

                    if rec.outcome == SimulationOutcome.REACHED:
                        success_found = True
                        if int(getattr(rec, "money", 0)) >= total_money:
                            optimal_found = True

                        # Preserve the original sequential early-stop behavior.
                        # Parallel batches may already have completed additional
                        # simulations before their results are collected.
                        if cfg.early_stop_on_success or optimal_found:
                            break

                # When the best possible solution (all gold coins + reached) is
                # found, stop the whole search.
                if optimal_found:
                    _publish_progress()
                    if max_sim is None:
                        max_sim = total_simulations
                    else:
                        max_sim = min(max_sim, total_simulations)
                    success_found = False
                    continue

                # When a solution is found, record best and restart PSO with a
                # new seed to keep exploring for potentially better solutions.
                if success_found:
                    _publish_progress()
                    run_seed += 1
                    rng = random.Random(run_seed)
                    particles = []
                    for _ in range(cfg.n_particles):
                        pos = [rng.uniform(lo, hi) for lo, hi in bounds]
                        vel = [
                            rng.uniform(-1.0, 1.0) * (hi - lo) * cfg.velocity_scale
                            for lo, hi in bounds
                        ]
                        particles.append(Particle(pos, vel))
                    stall_count = 0
                    prev_global_best = global_best_score
                    simulations = []
                    success_found = False
                    continue
                if global_best_score > prev_global_best:
                    prev_global_best = global_best_score
                    stall_count = 0
                else:
                    stall_count += 1

                    if (
                        cfg.restart_on_stall
                        and stall_count >= cfg.stall_limit
                        ):
                        elite = (
                            list(global_best_pos)
                            if global_best_pos is not None
                            else None
                        )

                        for p in particles:
                            if rng.random() < 0.5:
                                p.pos = [
                                    rng.uniform(lo, hi)
                                    for lo, hi in bounds
                                ]
                                p.vel = [
                                    rng.uniform(-1.0, 1.0)
                                    * (hi - lo)
                                    * cfg.velocity_scale
                                    for lo, hi in bounds
                                ]
                                p.best_pos = list(p.pos)
                                p.best_score = -math.inf

                        if elite is not None and particles:
                            particles[0].pos = list(elite)
                            particles[0].best_pos = list(elite)

                        stall_count = 0

        except _Cancelled:
            pass        # keep the best found so far
        finally:
            if pool is not None:
                pool.shutdown(wait=True, cancel_futures=True)

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
            best_coins = global_best_money
        else:
            best_coins = 0

        solve_time = time.perf_counter() - start
        success = any_success

        message = (
            f"{total_simulations} simulations over {iterations} "
            f"iterations in {solve_time:.2f}s; "
            f"best coins {best_coins}"
        )
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

def _eval_chunk(payload):
    """Evaluate a chunk of particles in one worker task (reduces IPC overhead)."""
    params_list, iteration = payload
    level = _WORKER_LEVEL
    template = _WORKER_TEMPLATE
    from .engine import evaluate_candidate, EvalConfig
    out = []
    for params in params_list:
        result = evaluate_candidate(
            level=level,
            template=template,
            params=params,
            iteration=iteration,
            source="pso",
            config=EvalConfig(record_trajectory=_WORKER_RECORD_TRAJECTORY,
                              max_steps=_WORKER_MAX_STEPS),
        )
        out.append(result.record)
    return out
