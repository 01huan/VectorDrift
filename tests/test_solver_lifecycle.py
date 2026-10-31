"""AI Solver jobs keep optimizing while the level is open and stop on leave/quit."""

import functools
import multiprocessing
import time
from types import SimpleNamespace

import pytest

from vector_drift.scenes import game as game_module
from vector_drift.scenes.base import SceneManager
from vector_drift.scenes.game import GameScene
from vector_drift.scenes.menu import MenuScene
from vector_drift.solver import PSOConfig, run_solver_async
from vector_drift.solver import pso as pso_module

pytestmark = pytest.mark.usefixtures("pygame_display")


def _manager():
    audio = SimpleNamespace(play=lambda *a, **k: None, start_loop=lambda *a, **k: None,
                            stop_loop=lambda *a, **k: None, toggle_mute=lambda: None)
    return SceneManager(audio)


def _random_scene(manager):
    manager.session.level_id = 7
    manager.session.random_seed = 123
    scene = GameScene(manager)
    manager.switch(scene)
    return scene


@pytest.fixture
def small_pool(monkeypatch):
    """Real PSO with two worker processes, so the test stays cheap."""
    monkeypatch.setattr(game_module, "PSOConfig", functools.partial(PSOConfig, n_workers=2))


def _wait_for_children(before, timeout_s=30.0):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if set(multiprocessing.active_children()) - before:
            return True
        time.sleep(0.05)
    return False


def _stops_within(job, timeout_s):
    deadline = time.monotonic() + timeout_s
    while job.running and time.monotonic() < deadline:
        time.sleep(0.05)
    return not job.running


@pytest.mark.parametrize("leave", ["switch", "quit"])
def test_leaving_game_scene_stops_solver_and_workers(small_pool, leave):
    before = set(multiprocessing.active_children())
    manager = _manager()
    scene = _random_scene(manager)
    job = scene.ai_job
    assert job is not None and job.running
    assert _wait_for_children(before), "solver worker processes never started"

    if leave == "switch":
        manager.switch(MenuScene(manager))
    else:
        manager.quit()

    assert _stops_within(job, 5.0)
    assert not (set(multiprocessing.active_children()) - before)


def test_game_scene_solver_job_has_no_budgets(monkeypatch):
    calls = []

    def fake_run(solver, level, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(running=True, cancel=lambda: None, error=None, result=None)

    monkeypatch.setattr(game_module, "run_solver_async", fake_run)
    _random_scene(_manager())
    assert calls
    assert "time_budget_s" not in calls[0]
    assert "simulation_budget" not in calls[0]


def test_worker_watchdog_exits_when_parent_is_gone():
    exits = []
    pso_module._watch_parent(lambda: False, lambda code: exits.append(code), interval_s=0.0)
    assert exits == [0]
