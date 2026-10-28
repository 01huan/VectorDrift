"""Stress test: can PSO solve every randomly generated level?"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from vector_drift.data import LevelSpec, ObstacleSpec, PickupSpec, HoleSpec
from vector_drift.level_presets import dynamic_ids
from vector_drift.random_level import generate_random_level
from vector_drift.solver import PSOSolver, PSOConfig

HERE = Path(__file__).resolve().parent
UNSOLVABLE_PATH = HERE / "data" / "pso_unsolvable_levels.jsonl"


def _obstacle_to_dict(o: ObstacleSpec) -> dict[str, Any]:
    return {
        "center": [float(o.center[0]), float(o.center[1])],
        "radius": float(o.radius),
        "restitution": float(o.restitution),
        "kind": str(o.kind),
    }


def _pickup_to_dict(p: PickupSpec) -> dict[str, Any]:
    return {
        "center": [float(p.center[0]), float(p.center[1])],
        "radius": float(p.radius),
        "kind": str(p.kind),
    }


def _hole_to_dict(h: HoleSpec) -> dict[str, Any]:
    return {
        "black_center": [float(h.black_center[0]), float(h.black_center[1])],
        "white_center": [float(h.white_center[0]), float(h.white_center[1])],
        "radius": float(h.radius),
    }
def level_to_record(level: LevelSpec, seed: int) -> dict[str, Any]:
    return {
        "seed": int(seed),
        "level": {
            "id": int(level.id),
            "name": str(level.name),
            "start": [float(level.start[0]), float(level.start[1])],
            "target_center": [float(level.target_center[0]), float(level.target_center[1])],
            "target_radius": float(level.target_radius),
            "ship_id": str(level.ship_id),
            "time_limit": float(level.time_limit),
            "lives": int(level.lives),
            "obstacles": [_obstacle_to_dict(o) for o in (level.obstacles or ())],
            "pickups": [_pickup_to_dict(p) for p in (level.pickups or ())],
            "holes": [_hole_to_dict(h) for h in (level.holes or ())],
            "portals": [_hole_to_dict(h) for h in (level.portals or ())],
            "wormholes": [_hole_to_dict(h) for h in (level.wormholes or ())],
        },
    }


def record_to_level(rec: dict[str, Any]) -> LevelSpec:
    L = rec["level"]
    obstacles = tuple(
        ObstacleSpec(
            center=(float(o["center"][0]), float(o["center"][1])),
            radius=float(o["radius"]),
            restitution=float(o.get("restitution", 1.0)),
            kind=str(o.get("kind", "bumper")),
        )
        for o in L.get("obstacles", [])
    )
    pickups = tuple(
        PickupSpec(
            center=(float(p["center"][0]), float(p["center"][1])),
            radius=float(p.get("radius", 0.45)),
            kind=str(p.get("kind", "shockwave")),
        )
        for p in L.get("pickups", [])
    )
    def _holes(key):
        return tuple(
            HoleSpec(
                black_center=(float(h["black_center"][0]), float(h["black_center"][1])),
                white_center=(float(h["white_center"][0]), float(h["white_center"][1])),
                radius=float(h.get("radius", 0.5)),
            )
            for h in L.get(key, [])
        )
    return LevelSpec(
        id=int(L["id"]),
        name=str(L["name"]),
        start=(float(L["start"][0]), float(L["start"][1])),
        target_center=(float(L["target_center"][0]), float(L["target_center"][1])),
        target_radius=float(L["target_radius"]),
        ship_id=str(L["ship_id"]),
        time_limit=float(L["time_limit"]),
        lives=int(L["lives"]),
        obstacles=obstacles,
        pickups=pickups,
        holes=_holes("holes"),
        portals=_holes("portals"),
        wormholes=_holes("wormholes"),
    )


def _load_unsolvable() -> list[dict[str, Any]]:
    if not UNSOLVABLE_PATH.exists():
        return []
    out: list[dict[str, Any]] = []
    for line in UNSOLVABLE_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        out.append(json.loads(line))
    return out


def _save_unsolvable(records: list[dict[str, Any]]) -> None:
    UNSOLVABLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with UNSOLVABLE_PATH.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _record_key(rec: dict[str, Any]) -> tuple[int, int]:
    return (int(rec["level"]["id"]), int(rec["seed"]))


def test_pso_solves_random_levels():
    solver = PSOSolver(PSOConfig())

    existing = _load_unsolvable()
    still_unsolved: list[dict[str, Any]] = []
    for rec in existing:
        level = record_to_level(rec)
        seed = int(rec["seed"])
        result = solver.solve(level, rng_seed=seed)
        if not result.success:
            still_unsolved.append(rec)

    ids = list(dynamic_ids())
    assert ids, "no dynamic/random levels registered"
    count = int(os.environ.get("PSO_RANDOM_LEVEL_COUNT", "10"))
    base_seed = int(os.environ.get("PSO_RANDOM_LEVEL_BASE_SEED", "900000"))
    new_unsolved: list[dict[str, Any]] = []
    seen_keys = {_record_key(r) for r in still_unsolved}
    for i in range(count):
        level_id = ids[i % len(ids)]
        seed = base_seed + i
        level = generate_random_level(level_id=level_id, seed=seed)
        result = solver.solve(level, rng_seed=seed)
        if not result.success:
            rec = level_to_record(level, seed)
            key = _record_key(rec)
            if key not in seen_keys:
                seen_keys.add(key)
                new_unsolved.append(rec)

    _save_unsolvable(still_unsolved + new_unsolved)

    problems = still_unsolved + new_unsolved
    assert not problems, (
        f"PSO could not solve {len(problems)} level(s); "
        f"details saved to {UNSOLVABLE_PATH}"
    )

