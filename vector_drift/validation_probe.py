"""Optional AI Solver probe used by the level validator."""

from __future__ import annotations

from .data import SHIPS
from .physics import Outcome
from .validation_report import _check


def _solver_probe(level, preset, checks, profile, seed):
    run_solver = getattr(profile, "run_solver", False)
    if not run_solver:
        _check(checks, "solver_confirms", True, "info",
               "AI Solver probe disabled for this preset")
        return None, None
    from .expr_parser import parse_expression
    from .physics import ForceField
    from .solver import PSOConfig, PSOSolver

    probe_seed = seed if seed is not None else 0
    solver = PSOSolver(PSOConfig(
        template_key=getattr(profile, "solver_template", "general_poly"),
        n_particles=getattr(profile, "solver_particles", 10),
        max_simulations=getattr(profile, "solver_simulations", 16),
        early_stop_on_success=True,
        n_workers=1,
        max_steps=getattr(profile, "solver_max_steps", 480),
        record_trajectory=False,
        seed=probe_seed,
    ))
    result = solver.solve(level,
                          simulation_budget=getattr(profile, "solver_simulations", 16),
                          rng_seed=probe_seed)
    confirmed = False
    flight_time = None
    best = getattr(result, "best", None)
    if best is not None:
        try:
            field = ForceField.from_exprs(parse_expression(best.fx_text),
                                          parse_expression(best.fy_text))
            from .physics import Flight
            ship = SHIPS.get(level.ship_id, SHIPS["ship01"])
            flight = Flight(field, ship, level)
            while flight.running:
                flight.step()
            confirmed = flight.outcome is Outcome.REACHED
            flight_time = flight.time
        except Exception:
            confirmed = False
    require = bool(getattr(profile, "require_solver_confirmed", False))
    message = ("AI Solver found a verified solution under the formal physics"
               if confirmed else
               "AI Solver found no solution within the probe budget "
               "(geometry still guarantees a path)")
    _check(checks, "solver_confirms", confirmed or not require, "info",
           message if not require else message,
           confirmed=confirmed, flight_time=flight_time,
           simulations=getattr(result, "total_simulations", None))
    return confirmed, result


__all__ = ["_solver_probe"]
