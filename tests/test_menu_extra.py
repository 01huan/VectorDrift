import pygame
import pytest

from types import SimpleNamespace

from vector_drift import config
from vector_drift.scenes.base import SceneManager
from vector_drift.scenes.menu import MenuScene

pytestmark = pytest.mark.usefixtures("pygame_display")


def test_menu_scene_extra():
    am = SimpleNamespace(is_authenticated=lambda: True, is_busy=False, current_user=SimpleNamespace(email="a@b.com"))
    mgr = SceneManager(SimpleNamespace(play=lambda *a, **k: None, toggle_mute=lambda: None), account_manager=am)
    scene = MenuScene(mgr)
    mgr.switch(scene)
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    scene.draw(surface)
    # keyboard paths
    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
    # new scene after switch
    scene2 = MenuScene(mgr)
    mgr.switch(scene2)
    scene2.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_l))
    scene3 = MenuScene(mgr)
    mgr.switch(scene3)
    scene3.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
    # quit button
    scene4 = MenuScene(mgr)
    mgr.switch(scene4)
    scene4.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=scene4.quit_button.rect.center))
