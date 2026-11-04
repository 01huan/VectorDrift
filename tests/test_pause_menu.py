"""Esc in the level screen: closes the top popup first, otherwise opens the pause menu."""

from types import SimpleNamespace

import pygame
import pytest

from vector_drift.scenes.base import SceneManager
from vector_drift.scenes.game import FLIGHT, GameScene
from vector_drift.story import all_seen_keys

pytestmark = pytest.mark.usefixtures("pygame_display")


def _manager():
    sounds = []
    audio = SimpleNamespace(play=lambda *a, **k: sounds.append(("play",) + a),
                            start_loop=lambda name: sounds.append(("start", name)),
                            stop_loop=lambda name: sounds.append(("stop", name)))
    manager = SceneManager(audio)
    manager.session.story_seen = all_seen_keys()     # no story dialogue in the way
    manager.sounds = sounds
    return manager


def _scene(level_id, manager=None, seed=None):
    manager = manager or _manager()
    manager.session.level_id = level_id
    manager.session.random_seed = seed
    scene = GameScene(manager)
    manager.switch(scene)
    return scene


def _key(scene, key, unicode=""):
    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key, mod=0, unicode=unicode,
                                          scancode=0))


def _launch(scene, fx="1", fy="0"):
    scene.editor.set_lines([fx, fy])
    scene._on_text_change(scene.editor)
    scene._try_launch()
    assert scene.state == FLIGHT


# --- Task 1: Esc closes the AI Solver popup ------------------------------------------

def test_esc_closes_the_ai_solver_popup():
    scene = _scene(7, seed=123)
    scene._on_ai_click()
    assert scene.ai_popup

    _key(scene, pygame.K_ESCAPE)
    assert not scene.ai_popup


def test_esc_closes_the_ai_solver_popup_during_flight_without_aborting():
    scene = _scene(7, seed=123)
    _launch(scene, "0.1", "0")
    lives = scene.lives
    scene._on_ai_click()

    _key(scene, pygame.K_ESCAPE)
    assert not scene.ai_popup
    assert scene.state == FLIGHT and scene.flight.running
    assert scene.lives == lives
