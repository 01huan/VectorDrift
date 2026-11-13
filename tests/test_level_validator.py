"""Tests for the Procedural Level Validator (level_validator)."""

import json
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from dataclasses import replace

from vector_drift.data import LevelSpec, ObstacleSpec, PickupSpec, get_level
from vector_drift.level_presets import PRESET_8, RandomPreset
from vector_drift.level_validator import (
    ValidationCheck,
    ValidationReport,
    validate_level,
)

# The bomb theme is not part of the random level rotation any more; this
# preset keeps the bomb-only checks covered.
BOMB = RandomPreset(
    level_id=8,
    name="Random Drift Bomb",
    generator="bomb",
    time_limit=10.0,
    lives=4,
    target_radius=0.8,
    min_start_target_dist=10.0,
    num_hidden_points=0,
    num_obstacles_min=3,
    num_obstacles_max=6,
    num_direct_blockers=0,
    required_pickup_kinds=("shockwave",),
    pickup_groups=(("money", (1, 2), 0.5), ("life", (1, 1), 0.5)),
)


def _fixed_level():
    return get_level(1)


def _sealed_level():
    """Start and target split by a sealed wall of rocks (level-4 style)."""
    return LevelSpec(
        id=991,
        name="Sealed",
        start=(-7.0, 0.0),
        target_center=(7.0, 0.0),
        target_radius=1.0,
        ship_id="ship01",
        time_limit=10.0,
        lives=3,
        obstacles=tuple(ObstacleSpec(center=(0.0, y), radius=0.9)
                        for y in range(-8, 9)),
    )


def _validate(level, **kwargs):
    kwargs.setdefault("run_solver", False)
    return validate_level(level, **kwargs)


def test_valid_fixed_level_has_no_errors():
    report = _validate(_fixed_level())
    assert report.ok
    assert not report.errors
    assert not report.warnings or all(c.severity == "warning" for c in report.warnings)


def test_sealed_level_is_rejected():
    report = _validate(_sealed_level())
    assert not report.ok
    assert "path_exists" in [c.name for c in report.errors]


def test_endpoint_too_close_is_rejected():
    level = LevelSpec(
        id=992, name="Cramped", start=(-1.0, 0.0), target_center=(1.0, 0.0),
        target_radius=1.0, ship_id="ship01", time_limit=10.0, lives=3,
        obstacles=(),
    )
    report = _validate(level)
    assert not report.ok
    assert "endpoint_distance" in [c.name for c in report.errors]


def test_required_pickup_missing_is_rejected():
    preset = replace(BOMB, templates=(), required_pickup_kinds=("shockwave",))
    level = LevelSpec(
        id=993, name="NoShockwave", start=(-7.0, 0.0), target_center=(7.0, 0.0),
        target_radius=0.8, ship_id="ship01", time_limit=10.0, lives=3,
        obstacles=(),
    )
    report = _validate(level, preset=preset, generator="bomb")
    assert not report.ok
    assert "required_pickup_present" in [c.name for c in report.errors]


def test_required_pickup_unreachable_is_rejected():
    """A shockwave sealed inside an isolated rock pocket can never be reached."""
    preset = replace(BOMB, templates=(), required_pickup_kinds=("shockwave",))
    shock = PickupSpec(center=(0.0, 0.0), radius=0.5, kind="shockwave")
    pocket = tuple(ObstacleSpec(center=(0.0, y), radius=0.75)
                   for y in (-3.0, -1.6, -0.75, 0.0, 0.75, 1.6, 3.0))
    ring = tuple(ObstacleSpec(center=(x, y), radius=0.75)
                 for x in (-2.6, -1.3, 1.3, 2.6) for y in (-2.6, 2.6))
    level = LevelSpec(
        id=994, name="UnreachableShock", start=(-7.0, 0.0), target_center=(7.0, 0.0),
        target_radius=0.8, ship_id="ship01", time_limit=10.0, lives=3,
        obstacles=pocket + ring, pickups=(shock,),
    )
    report = _validate(level, preset=preset, generator="corridor")
    assert not report.ok
    assert "required_pickup_reachable" in [c.name for c in report.errors]


def test_report_serialises_to_json():
    report = _validate(_fixed_level())
    payload = json.dumps(report.to_dict())
    assert "checks" in payload
    assert '"ok": true' in payload


def test_trivial_field_is_flagged_on_level1():
    report = _validate(_fixed_level())
    warnings = [c for c in report.warnings if c.name == "trivial_field"]
    assert warnings, "Level 1 is solvable by a trivial field; it should be flagged"


def test_validator_works_without_preset():
    report = _validate(_fixed_level(), preset=None)
    assert report.ok


def test_solver_probe_check_is_present_when_enabled():
    report = _validate(_fixed_level(), preset=None, run_solver=True)
    names = [c.name for c in report.checks]
    assert "solver_confirms" in names


def test_errors_raise_the_report_flag():
    report = _validate(_sealed_level())
    assert report.errors
    assert not report.ok
    summary = report.summary()
    assert "REJECTED" in summary


def test_validation_report_ranking_helpers():
    level = _fixed_level()
    report = _validate(level)
    assert isinstance(report, ValidationReport)
    check = ValidationCheck(name="x", passed=False, severity="error", message="m")
    assert check.severity == "error"


def test_generator_retries_after_validation_failure(monkeypatch):
    """A hard validation error on the first candidate regenerates the map."""
    import vector_drift.level_validator as lv
    from vector_drift.random_level import generate_random_level

    real_validate = lv.validate_level
    state = {"n": 0}

    def flaky(level, **kwargs):
        state["n"] += 1
        kwargs.pop("run_solver", None)
        report = real_validate(level, run_solver=False, **kwargs)
        if state["n"] == 1:
            report.checks.append(ValidationCheck(
                name="forced_fail", passed=False, severity="error",
                message="rigged by the test"))
        return report

    monkeypatch.setattr(lv, "validate_level", flaky)
    level, report = generate_random_level(8, seed=123, run_solver=False,
                                          return_report=True)
    assert state["n"] >= 2
    assert report.ok


def test_generator_returns_best_candidate_when_validation_never_passes(monkeypatch):
    """require_solver=True keeps retrying, then falls back instead of hanging."""
    import vector_drift.level_validator as lv
    from vector_drift.random_level import generate_random_level

    real_validate = lv.validate_level

    def never(level, **kwargs):
        kwargs.pop("run_solver", None)
        report = real_validate(level, run_solver=False, **kwargs)
        report.checks.append(ValidationCheck(
            name="forced_fail", passed=False, severity="error",
            message="rigged by the test"))
        return report

    monkeypatch.setattr(lv, "validate_level", never)
    level, report = generate_random_level(8, seed=123,
                                          require_solver=True,
                                          return_report=True)
    assert level is not None
    assert report is not None
    assert not report.ok


def test_broken_wormhole_wall_gap_is_rejected():
    from vector_drift.level_modules import generate_layout

    template = [t for t in PRESET_8.templates if t.generator == "wormhole_network"][0]
    preset = replace(template, templates=(), name=PRESET_8.name)
    layout = generate_layout(5, preset)
    level = layout.level
    # Blow a gap in the first wall: drop every other wall rock.
    walls = layout.walls
    fixed = walls[0][1]
    thinned = tuple(
        ob for i, ob in enumerate(level.obstacles)
        if abs(ob.center[0] - fixed) >= 1e-6 or i % 3 != 1
    )
    level = replace(level, obstacles=thinned)
    report = _validate(level, preset=preset, route=layout.route,
                       segments=layout.segments, teleports=layout.teleports,
                       walls=layout.walls, generator="wormhole_network",
                       seed=5)
    assert "walls_sealed" in [c.name for c in report.errors]


def test_bomb_level_needs_blastable_ring():
    preset = replace(BOMB, templates=(), name=PRESET_8.name)
    from vector_drift.level_modules import generate_layout
    layout = generate_layout(5, preset)
    report = _validate(layout.level, preset=preset, route=layout.route,
                       segments=layout.segments,
                       generator="bomb", seed=5)
    assert report.ok
    assert "path_opens_after_blast" not in [c.name for c in report.errors]
