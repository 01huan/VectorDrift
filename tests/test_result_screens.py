"""The fail and win screens open and draw after a real run."""

from types import SimpleNamespace

import pygame
import pytest

from vector_drift import config
from vector_drift.physics import Outcome
from vector_drift.scenes.base import SceneManager
from vector_drift.scenes.fail import FailScene
from vector_drift.scenes.game import GameScene
from vector_drift.scenes.win import WinScene
from vector_drift.story import all_seen_keys

pytestmark = pytest.mark.usefixtures("pygame_display")


def _scene(level_id):
    audio = SimpleNamespace(play=lambda *a: None, start_loop=lambda *a: None,
                            stop_loop=lambda *a: None)
    manager = SceneManager(audio)
    manager.session.story_seen = all_seen_keys()
    manager.session.level_id = level_id
    scene = GameScene(manager)
    manager.switch(scene)
    scene.editor.set_lines(["0", "0"])
    scene._on_text_change(scene.editor)
    return manager, scene


def test_losing_every_life_opens_a_fail_screen_that_draws():
    manager, scene = _scene(1)
    for _ in range(scene.level.lives):
        scene._try_launch()
        scene.flight.abort()
        scene._end_flight(Outcome.ABORTED)
    assert isinstance(manager.scene, FailScene)
    manager.scene.draw(pygame.Surface((config.WINDOW_W, config.WINDOW_H)))


def test_reaching_the_planet_opens_a_win_screen_that_draws():
    manager, scene = _scene(1)
    scene._try_launch()
    scene._end_flight(Outcome.REACHED)
    scene.update(config.WIN_DELAY + 0.1)
    assert isinstance(manager.scene, WinScene)
    manager.scene.draw(pygame.Surface((config.WINDOW_W, config.WINDOW_H)))
