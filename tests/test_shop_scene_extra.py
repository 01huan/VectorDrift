import pygame
import pytest

from types import SimpleNamespace

from vector_drift import config
from vector_drift.scenes.base import SceneManager
from vector_drift.scenes.shop import ShopScene

pytestmark = pytest.mark.usefixtures("pygame_display")


def _manager():
    audio = SimpleNamespace(play=lambda *a, **k: None, toggle_mute=lambda: None, start_loop=lambda *a, **k: None, stop_loop=lambda *a, **k: None)
    mgr = SceneManager(audio)
    mgr.session.money.amount = 1000
    return mgr


def test_shop_scene_purchase_flow():
    mgr = _manager()
    scene = ShopScene(mgr)
    mgr.switch(scene)
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    scene.draw(surface)
    if scene.buy_buttons:
        btn = scene.buy_buttons[0][1]
        btn.enabled = True
        scene.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=btn.rect.center))
        scene.draw(surface)
    # escape
    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
