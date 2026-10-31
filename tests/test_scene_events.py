import pygame
import pytest

from types import SimpleNamespace

from vector_drift import config
from vector_drift.scenes.base import SceneManager
from vector_drift.scenes.account import AccountScene
from vector_drift.scenes.shop import ShopScene
from vector_drift.scenes.menu import MenuScene
from vector_drift.scenes.levels import LevelSelectScene
from vector_drift.scenes.fail import FailScene

pytestmark = pytest.mark.usefixtures("pygame_display")


def _manager(account=None):
    audio = SimpleNamespace(play=lambda *a, **k: None, toggle_mute=lambda: None, start_loop=lambda *a, **k: None, stop_loop=lambda *a, **k: None)
    return SceneManager(audio, account_manager=account)


def test_account_scene_events():
    mgr = _manager()
    scene = AccountScene(mgr)
    mgr.switch(scene)
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    scene.draw(surface)
    scene.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=scene.back_button.rect.center))
    scene2 = AccountScene(mgr)
    mgr.switch(scene2)
    scene2.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=scene2.refresh_button.rect.center))
    scene2.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=scene2.delete_local_button.rect.center))
    scene2.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))


def test_shop_scene_events():
    mgr = _manager()
    scene = ShopScene(mgr)
    mgr.switch(scene)
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    scene.draw(surface)
    scene.handle_event(pygame.event.Event(pygame.MOUSEMOTION, pos=(1, 1)))
    scene.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=scene.back_button.rect.center))
    if scene.buy_buttons:
        btn = scene.buy_buttons[0][1]
        scene2 = ShopScene(mgr)
        mgr.switch(scene2)
        scene2.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=btn.rect.center))
    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))

def test_menu_scene_events():
    mgr = _manager()
    scene = MenuScene(mgr)
    mgr.switch(scene)
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    scene.draw(surface)
    for attr in ("play_button", "levels_button", "shop_button", "account_button", "login_button"):
        btn = getattr(scene, attr, None)
        if btn is not None:
            scene.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=btn.rect.center))
    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))


def test_levels_scene_events_and_pages():
    mgr = _manager()
    scene = LevelSelectScene(mgr)
    mgr.switch(scene)
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    scene.draw(surface)
    scene.handle_event(pygame.event.Event(pygame.MOUSEMOTION, pos=(100, 100)))
    if scene.next_button is not None:
        scene.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=scene.next_button.rect.center))
        scene.draw(surface)
    if scene.prev_button is not None:
        scene.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=scene.prev_button.rect.center))
    scene.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=scene.shop_button.rect.center))
    scene.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=scene.menu_button.rect.center))


def test_fail_scene_events():
    mgr = _manager()
    scene = FailScene(mgr)
    mgr.switch(scene)
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    scene.draw(surface)
    for btn in (scene.retry_button, scene.levels_button, scene.menu_button):
        scene.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=btn.rect.center))
    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
