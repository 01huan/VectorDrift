import pygame
import pytest

from types import SimpleNamespace

from vector_drift import config
from vector_drift.scenes.base import SceneManager
from vector_drift.scenes.game import GameScene, SETUP, FLIGHT

pytestmark = pytest.mark.usefixtures("pygame_display")


def _manager():
    audio = SimpleNamespace(play=lambda *a, **k: None, toggle_mute=lambda: None, start_loop=lambda *a, **k: None, stop_loop=lambda *a, **k: None)
    return SceneManager(audio)


def test_game_scene_construction_and_draw():
    mgr = _manager()
    mgr.session.level_id = 1
    scene = GameScene(mgr)
    mgr.switch(scene)
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    scene.draw(surface)
    assert scene.state in (SETUP, FLIGHT)


def test_game_scene_handle_event_smoke():
    mgr = _manager()
    mgr.session.level_id = 1
    scene = GameScene(mgr)
    mgr.switch(scene)
    for event in (
        pygame.event.Event(pygame.MOUSEMOTION, pos=(10, 10)),
        pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN),
        pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE),
    ):
        scene.handle_event(event)
