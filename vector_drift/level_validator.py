"""Procedural Level Validator.

Every generated level is checked *before it is handed to the player*. The
checks come in two flavours:

* **Fast path analysis** -- pure geometry, always runs. A coarse occupancy
  grid plus A* decides whether a route exists at all, whether the intended
  route legs are clear, whether required pickups (e.g. the bomb module's
  shockwave) are reachable, and whether the wormhole walls are really sealed.
  This is what catches "everything is blocked" and "the required pickup is
  unreachable".
* **AI Solver probe** -- a short, deterministic PSO run (small budget) asks
  whether a non-trivial force field can actually fly the level under the
  formal game physics. Passing confirms solvability; failing only marks the
  report as *unconfirmed* because the geometric checks already guarantee a
  path (the generator builds one), so a failed probe never rejects a level
  by itself -- unless ``require_solver_confirmed`` is set in the preset (see
  ``ValidationProfile``) or forced with ``require_solver=True``.

Difficulty heuristics (route length vs time limit, obstacle density) are
warnings: they flag levels that are likely too easy or too hard, but they are
never a hard error because players -- and the AI Solver -- still get to try.

The implementation is split into ``validation_report`` (result objects),
``validation_grid`` (A* reachability), ``validation_checks`` (geometry and
heuristics) and ``validation_probe`` (AI Solver). This module keeps the
public ``validate_level`` entry point and re-exports the old names.
"""

from __future__ import annotations

import dataclasses

from .validation_checks import (
    _bomb_checks,
    _difficulty_checks,
    _direct_blocker_checks,
    _endpoint_checks,
    _grid_checks,
    _required_pickup_checks,
    _route_checks,
    _trivial_field_checks,
    _wormhole_checks,
)
from .validation_grid import (
    _RESOLUTION,
    _as_discs,
    _astar,
    _build_grid,
    _cell,
    _inflated,
    _nearest_free,
    _reachable,
)
from .validation_probe import _solver_probe
from .validation_report import ValidationCheck, ValidationReport, _check


def validate_level(level, *, preset=None, route=None, segments=None,
                   teleports=None, walls=None, generator=None, seed=None,
                   run_solver=None, require_solver=None):
    """Validate one generated (or fixed) level.

    Pass the intended ``route``/``segments``/``teleports``/``walls`` from the
    generator whenever available; the geometric checks use them.  ``preset``
    supplies the difficulty knobs and the AI Solver probe settings.
    """
    from .level_presets import PRESETS, ValidationProfile

    if preset is None:
        preset = PRESETS.get(getattr(level, "id", None))
    profile = getattr(preset, "validation", ValidationProfile())
    if run_solver is not None:
        profile = dataclasses.replace(profile, run_solver=bool(run_solver))
    if require_solver is not None:
        profile = dataclasses.replace(profile,
                                      require_solver_confirmed=bool(require_solver))

    module = generator or getattr(preset, "generator", "corridor")
    checks = []
    metrics = {"module": module, "time_limit": level.time_limit,
               "lives": level.lives, "target_radius": level.target_radius}
    teleports = teleports or ()
    walls = walls or ()

    _endpoint_checks(level, preset, checks)
    if module == "wormhole_network":
        _wormhole_checks(level, walls, teleports, checks)
        _grid_checks(level, level.obstacles, checks, metrics, expect_blocked=True)
    elif module == "bomb":
        _grid_checks(level, level.obstacles, checks, metrics, expect_blocked=True)
    else:
        _grid_checks(level, level.obstacles, checks, metrics)
    if segments:
        _route_checks(level, route, segments, checks, metrics, module)
    _difficulty_checks(level, metrics.get("route_length"), preset, checks,
                       metrics, a_star=metrics.get("a_star_length_m"),
                       module=module)
    _direct_blocker_checks(level, preset, checks)
    _required_pickup_checks(level, preset, checks)
    if module == "bomb":
        _bomb_checks(level, checks)
    _trivial_field_checks(level, checks)
    solver_confirmed, solver_result = _solver_probe(level, preset, checks,
                                                    profile, seed)

    return ValidationReport(
        level_id=getattr(level, "id", 0),
        seed=seed,
        generator=module,
        checks=checks,
        metrics=metrics,
        solver_confirmed=solver_confirmed,
        solver_result=solver_result,
        route=tuple(route) if route else None,
        segments=tuple(segments) if segments else None,
    )


__all__ = [
    "ValidationCheck", "ValidationReport", "validate_level",
    "_RESOLUTION", "_as_discs", "_inflated", "_build_grid", "_cell",
    "_nearest_free", "_astar", "_reachable",
    "_check", "_endpoint_checks", "_grid_checks", "_route_checks",
    "_difficulty_checks", "_direct_blocker_checks", "_required_pickup_checks",
    "_bomb_checks", "_wormhole_checks", "_trivial_field_checks",
    "_solver_probe",
]
