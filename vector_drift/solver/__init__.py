"""Offline solver package for Vector Drift.

First stage: pure Particle Swarm Optimization (PSO) searching force-field
formula parameters. Fully offline: no cloud API, no network, no API key.

Later stages may add regression models, small neural networks, genetic
programming or reinforcement learning behind the same ``Solver`` interface.
"""

from .interface import Solver, SolveResult, SimulationSpec, SolverError
from .data import (
    SimulationRecord,
    SimulationOutcome,
    SCHEMA_VERSION,
    SCHEMA_NAME,
    record_to_dict,
    dict_to_record,
)
from .store import JSONLStore, StoreConfig
from .pso import PSOSolver, PSOConfig
from .engine import EvalConfig, EvalResult, evaluate_candidate
from .runner import SolverJob, run_solver_async
from .templates import FieldTemplate, get_template, template_keys
from .benchmark import BenchmarkCase, BenchmarkResult, generate_benchmark_levels, run_benchmark

__all__ = [
    "Solver",
    "SolveResult",
    "SimulationSpec",
    "SolverError",
    "SimulationRecord",
    "SimulationOutcome",
    "SCHEMA_VERSION",
    "SCHEMA_NAME",
    "record_to_dict",
    "dict_to_record",
    "JSONLStore",
    "StoreConfig",
    "PSOSolver",
    "PSOConfig",
    "EvalConfig",
    "EvalResult",
    "evaluate_candidate",
    "SolverJob",
    "run_solver_async",
    "FieldTemplate",
    "get_template",
    "template_keys",
    "BenchmarkCase",
    "BenchmarkResult",
    "generate_benchmark_levels",
    "run_benchmark",
]
