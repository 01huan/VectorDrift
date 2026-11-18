"""Random levels restart the AI Solver only for a state the player can launch from.

Every restart starts a new solve with its own pool of worker processes (one
per CPU) while the cancelled one is still shutting down. Restarting on every
pickup taken in flight and on the pan to the next section stacked several
pools on Level 8 and ran the machine out of memory. The answer is only
usable in SETUP, so the solver restarts there, once per new state.
"""

from types import SimpleNamespace

import pytest

from vector_drift.scenes.base import SceneManager
from vector_drift.scenes.game import FLIGHT, SETUP, GameScene

pytestmark = pytest.mark.usefixtures("pygame_display")


def _scene(seed=123):
    audio = SimpleNamespace(play=lambda *a, **k: None, start_loop=lambda *a, **k: None,
                            stop_loop=lambda *a, **k: None)
    manager = SceneManager(audio)
    manager.session.level_id = 8
    manager.session.random_seed = seed
    scene = GameScene(manager)
    manager.switch(scene)
    return scene


def _launch(scene, fx="0.1", fy="0"):
    scene.editor.set_lines([fx, fy])
    scene._on_text_change(scene.editor)
    scene._try_launch()
    assert scene.state == FLIGHT


def test_taking_a_pickup_in_flight_does_not_restart_the_solver(no_solver):
    scene = _scene()
    scene.update(1 / 60)
    assert len(no_solver) == 1                  # the solve for the launch state
    assert scene.pickups
    _launch(scene)
    scene.pickups[0].consumed = True            # taken mid-flight
    for _ in range(5):
        scene.update(1 / 60)
    assert scene.state == FLIGHT
    assert len(no_solver) == 1


def test_the_solver_restarts_once_back_in_setup_on_a_new_state(no_solver):
    scene = _scene()
    scene.update(1 / 60)
    _launch(scene)
    scene.pickups[0].consumed = True
    scene.update(1 / 60)
    scene._abort()
    assert scene.state == SETUP
    changed = scene._state_key() != scene.ai_job_state_key
    for _ in range(5):
        scene.update(1 / 60)
    assert len(no_solver) == (2 if changed else 1)
    assert scene.ai_job_state_key == scene._state_key()
