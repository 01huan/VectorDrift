"""Structured simulation data model (schema v1).

Every candidate evaluation produces one :class:`SimulationRecord`.  Records are
JSON-serializable and carry enough information to reproduce the result:

* level description + seed
* initial state (ship, start)
* force-field template + parameter values + generated formula text
* simulation outcome verified by the formal game physics
* score, success flag, PSO iteration info
* data source and version

``SCHEMA_VERSION`` / ``SCHEMA_NAME`` let future migrations detect old files.
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any

from ..data import LevelSpec
from ..physics import Outcome

SCHEMA_VERSION = 1
SCHEMA_NAME = "vectorsolver.simulation"


class SimulationOutcome(str):
    """Aliases mirroring ``vector_drift.physics.Outcome`` values."""

    RUNNING = "running"
    REACHED = "reached"
    TIMEOUT = "timeout"
    OUT_OF_BOUNDS = "out_of_bounds"
    DIVERGED = "diverged"
    ABORTED = "aborted"


@dataclass
class TrajectoryPoint:
    x: float
    y: float
    vx: float
    vy: float
    step: int


@dataclass
class SimulationRecord:
    """One fully-reproducible simulation of a force-field candidate."""

    # ---- identity / provenance -------------------------------------
    schema_version: int = SCHEMA_VERSION
    schema_name: str = SCHEMA_NAME
    record_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    source: str = "pso"  # pso | regression | nn | gp | user | baseline

    # ---- level description (enough to rebuild the level) -----------
    level_id: int = 0
    level_seed: int | None = None
    level_name: str = ""
    start: tuple[float, float] = (0.0, 0.0)
    target_center: tuple[float, float] = (0.0, 0.0)
    target_radius: float = 0.0
    time_limit: float = 0.0
    ship_id: str = ""
    ship_mass: float = 1.0
    ship_hull_radius: float = 0.2

    # ---- force field -----------------------------------------------
    template: str = ""
    fx_text: str = ""
    fy_text: str = ""
    params: dict[str, float] = field(default_factory=dict)

    # ---- simulation result (formal physics verification) -----------
    outcome: str = SimulationOutcome.RUNNING
    steps: int = 0
    time: float = 0.0
    final_pos: tuple[float, float] = (0.0, 0.0)
    final_vel: tuple[float, float] = (0.0, 0.0)
    min_dist_to_target: float = math.inf
    trajectory: list[TrajectoryPoint] | None = None  # full trace (optional)

    # ---- scoring ----------------------------------------------------
    score: float = 0.0
    success: bool = False  # outcome == REACHED under formal rules

    # ---- solver metadata -------------------------------------------
    iteration: int = 0          # PSO iteration when this candidate was tested
    particle_id: int | None = None
    swarm_best_score: float = 0.0

    # -----------------------------------------------------------------
    def to_dict(self, include_trajectory: bool = True) -> dict[str, Any]:
        d = asdict(self)
        traj = d.pop("trajectory", None)
        # asdict already converts TrajectoryPoint dataclasses to dicts.
        if traj is not None and not include_trajectory:
            d["trajectory"] = None
        # else keep the converted list of dicts as-is.
        for key in ("start", "target_center", "final_pos", "final_vel"):
            val = d.get(key)
            if isinstance(val, tuple):
                d[key] = list(val)
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SimulationRecord":
        d = dict(d)
        traj = d.pop("trajectory", None)
        if traj:
            d["trajectory"] = [
                TrajectoryPoint(
                    x=p["x"], y=p["y"], vx=p["vx"], vy=p["vy"], step=p["step"]
                )
                for p in traj
            ]
        for key in ("start", "target_center", "final_pos", "final_vel"):
            val = d.get(key)
            if isinstance(val, list):
                d[key] = tuple(val)  # type: ignore[assignment]
        known = {f.name for f in cls.__dataclass_fields__.values()}
        d = {k: v for k, v in d.items() if k in known}
        return cls(**d)


def record_to_dict(record: SimulationRecord, include_trajectory: bool = True) -> dict:
    return record.to_dict(include_trajectory=include_trajectory)


def dict_to_record(d: dict) -> SimulationRecord:
    return SimulationRecord.from_dict(d)


def record_from_flight(
    *,
    record_id: str,
    run_id: str,
    source: str,
    level: LevelSpec,
    template: str,
    fx_text: str,
    fy_text: str,
    params: dict[str, float],
    outcome: Outcome,
    steps: int,
    final_pos: tuple[float, float],
    final_vel: tuple[float, float],
    min_dist_to_target: float,
    score: float,
    trajectory: list[TrajectoryPoint] | None,
    iteration: int = 0,
    particle_id: int | None = None,
    swarm_best_score: float = 0.0,
    timestamp: str | None = None,
) -> SimulationRecord:
    """Factory: build a :class:`SimulationRecord` from a finished :class:`Flight`."""
    import datetime as _dt

    return SimulationRecord(
        record_id=record_id,
        run_id=run_id,
        source=source,
        level_id=level.id,
        level_seed=getattr(level, "seed", None),
        level_name=getattr(level, "name", ""),
        start=tuple(level.start),
        target_center=tuple(level.target_center),
        target_radius=float(level.target_radius),
        time_limit=float(level.time_limit),
        ship_id=level.ship_id,
        ship_mass=1.0,
        ship_hull_radius=0.2,
        template=template,
        fx_text=fx_text,
        fy_text=fy_text,
        params=dict(params),
        outcome=outcome.value,
        steps=steps,
        time=steps * (level.time_limit / max(level.target_radius, 1e-6))
        if steps
        else 0.0,
        final_pos=tuple(final_pos),
        final_vel=tuple(final_vel),
        min_dist_to_target=float(min_dist_to_target),
        score=float(score),
        success=outcome is Outcome.REACHED,
        trajectory=list(trajectory) if trajectory is not None else None,
        iteration=int(iteration),
        particle_id=particle_id,
        swarm_best_score=float(swarm_best_score),
        timestamp=timestamp or _dt.datetime.now(_dt.timezone.utc).isoformat(),
    )

