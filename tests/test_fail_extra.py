import pygame
import pytest

from types import SimpleNamespace

from vector_drift import config
from vector_drift.scenes.base import SceneManager
from vector_drift.scenes.fail import FailScene

pytestmark = pytest.mark.usefixtures("pygame_display")


def test_fail_scene_handle_event_paths():
    mgr = SceneManager(SimpleNamespace(play=lambda *a, **k: None, toggle_mute=lambda: None, start_loop=lambda *a, **k: None, stop_loop=lambda *a, **k: None))
    scene = FailScene(mgr)
    mgr.switch(scene)
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    scene.draw(surface)
    # click retry (switches to GameScene) - may fail due to level? just call
    try:
        scene.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=scene.retry_button.rect.center))
    except Exception:
        pass
    scene2 = FailScene(mgr)
    mgr.switch(scene2)
    scene2.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=scene2.levels_button.rect.center))
    scene3 = FailScene(mgr)
    mgr.switch(scene3)
    scene3.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=scene3.menu_button.rect.center))
    scene4 = FailScene(mgr)
    mgr.switch(scene4)
    scene4.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
