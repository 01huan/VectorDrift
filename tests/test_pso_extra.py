from vector_drift.solver import PSOSolver, PSOConfig
from vector_drift.data import get_level

LEVEL = get_level(1)


def test_pso_tiny_budget():
    solver = PSOSolver(PSOConfig(n_particles=4, max_simulations=5, seed=1))
    result = solver.solve(LEVEL, simulation_budget=5, rng_seed=1)
    assert result.total_simulations <= 5
    assert result.pso_iterations >= 0


def test_pso_single_template():
    for key in ("trig_poly", "rich_combo", "general_poly"):
        solver = PSOSolver(PSOConfig(template_key=key, n_particles=4, max_simulations=8, seed=2))
        result = solver.solve(LEVEL, simulation_budget=8, rng_seed=2)
        assert isinstance(result.success, bool)


def test_pso_time_budget_zero():
    solver = PSOSolver(PSOConfig(n_particles=4, max_simulations=8, seed=3))
    result = solver.solve(LEVEL, time_budget_s=0.0, simulation_budget=8, rng_seed=3)
    assert result.total_simulations <= 8
