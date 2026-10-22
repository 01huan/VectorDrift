"""Candidate evaluation engine.

Turns a (template, parameters) pair into force-field formulas, runs the
formal game physics (``Flight``), and returns a fully documented
:class:`~solver.data.SimulationRecord`.  A candidate is successful *only*
when ``Outcome.REACHED`` under the real rules -- fitness alone never counts
as a solution.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable

from ..data import LevelSpec, SHIPS
from ..expr_parser import parse_expression
from ..physics import Flight, ForceField, Outcome
from .data import (
    SimulationRecord,
    TrajectoryPoint,
    record_from_flight,
)
from .templates import FieldTemplate, get_template

WORLD_DIAGONAL = math.hypot(2 * 10.0, 2 * 7.5)  # WORLD_HALF_W/H from config


@dataclass
class EvalConfig:
    """Controls how a candidate is simulated and scored."""

    dt: float | None = None          # None -> config.DT
    max_steps: int | None = None     # None -> level time_limit / dt
    record_trajectory: bool = True   # full trace (memory cost)
    ship_id: str = "drifter"


@dataclass
class EvalResult:
    """Outcome of evaluating one candidate."""

    record: SimulationRecord
    field: ForceField
    fx_text: str
    fy_text: str


def _default_ship() -> object:
    return SHIPS["drifter"]


def _score(outcome: Outcome, steps: int, max_steps: int,
           min_dist: float) -> float:
    """Score a finished flight.

    Any REACHED outranks any non-REACHED.  Among REACHED, faster is better.
    Among non-REACHED, closer to target is better (partial credit).
    """
    if max_steps <= 0:
        max_steps = 1
    if outcome is Outcome.REACHED:
        return 1.5 + (1.0 - steps / max_steps) * 0.5  # (1.5, 2.0]
    # Non-reached: partial credit in [0, 0.5).
    closeness = max(0.0, 1.0 - min(min_dist, WORLD_DIAGONAL) / WORLD_DIAGONAL)
    return 0.5 * closeness


def evaluate_candidate(
    level: LevelSpec,
    template: FieldTemplate,
    params: dict[str, float],
    *,
    iteration: int = 0,
    particle_id: int | None = None,
    swarm_best_score: float = 0.0,
    source: str = "solver",
    config: EvalConfig | None = None,
    run_id: str | None = None,
    record_id: str | None = None,
) -> EvalResult:
    """Simulate one candidate under formal game rules.

    Returns :class:`EvalResult` with a populated :class:`SimulationRecord`.
    Raises on parse/simulation errors; callers should catch and record a
    failed record instead.
    """
    cfg = config or EvalConfig()
    fx_text, fy_text = template.render(level, params)

    fx_expr = parse_expression(fx_text)
    fy_expr = parse_expression(fy_text)
    field = ForceField.from_exprs(fx_expr, fy_expr)

    ship = _default_ship()
    dt = cfg.dt
    if dt is None:
        from .. import config as _cfg
        dt = _cfg.DT
    max_steps = cfg.max_steps
    if max_steps is None:
        max_steps = round(level.time_limit / dt)

    flight = Flight(
        field=field,
        ship=ship,
        level=level,
        dt=dt,
    )
    # Cap steps manually so long runs stay bounded even if time_limit is large.
    flight.max_steps = max_steps

    trajectory: list[TrajectoryPoint] = []
    min_dist = math.inf
    tx, ty = level.target_center

    # Initial state.
    if cfg.record_trajectory:
        trajectory.append(TrajectoryPoint(
            x=flight.x, y=flight.y, vx=flight.vx, vy=flight.vy, step=0))
    min_dist = min(min_dist, math.dist((flight.x, flight.y), (tx, ty)))

    while flight.running:
        flight.step()
        if cfg.record_trajectory:
            trajectory.append(TrajectoryPoint(
                x=flight.x, y=flight.y,
                vx=flight.vx, vy=flight.vy, step=flight.steps))
        min_dist = min(min_dist, math.dist((flight.x, flight.y), (tx, ty)))
        if flight.steps >= max_steps:
            # Defensive: Flight already caps via max_steps/time_limit, but be safe.
            break

    score = _score(flight.outcome, flight.steps, max_steps, min_dist)

    import uuid as _uuid
    record = record_from_flight(
        record_id=record_id or _uuid.uuid4().hex,
        run_id=run_id or _uuid.uuid4().hex,
        source=source,
        level=level,
        template=template.key,
        fx_text=fx_text,
        fy_text=fy_text,
        params=dict(params),
        outcome=flight.outcome,
        steps=flight.steps,
        final_pos=(flight.x, flight.y),
        final_vel=(flight.vx, flight.vy),
        min_dist_to_target=min_dist,
        score=score,
        trajectory=trajectory if cfg.record_trajectory else None,
        iteration=iteration,
        particle_id=particle_id,
        swarm_best_score=swarm_best_score,
    )
    # Override the rough time estimate with the real one.
    record.time = flight.time
    record.ship_mass = float(ship.mass)
    record.ship_hull_radius = float(ship.hull_radius)

    return EvalResult(record=record, field=field, fx_text=fx_text, fy_text=fy_text)
