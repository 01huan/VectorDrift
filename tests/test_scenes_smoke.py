import pygame
import pytest

from types import SimpleNamespace

from vector_drift import config
from vector_drift.scenes.base import SceneManager
from vector_drift.scenes.account import AccountScene
from vector_drift.scenes.fail import FailScene
from vector_drift.scenes.shop import ShopScene
from vector_drift.scenes.menu import MenuScene
from vector_drift.scenes.levels import LevelSelectScene

pytestmark = pytest.mark.usefixtures("pygame_display")


def _manager():
    audio = SimpleNamespace(play=lambda *a, **k: None, toggle_mute=lambda: None)
    return SceneManager(audio)


def test_scene_construction_and_draw_smoke():
    mgr = _manager()
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    for Scene in (AccountScene, ShopScene, MenuScene, LevelSelectScene):
        scene = Scene(mgr)
        mgr.switch(scene)
        scene.draw(surface)
    # FailScene needs background optional
    fail = FailScene(mgr)
    mgr.switch(fail)
    fail.draw(surface)


def test_scene_handle_event_smoke():
    mgr = _manager()
    scene = MenuScene(mgr)
    mgr.switch(scene)
    # ESC / mouse events should not crash
    for event in (
        pygame.event.Event(pygame.MOUSEMOTION, pos=(1, 1)),
        pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE),
    ):
        scene.handle_event(event)
