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
from vector_drift.scenes.auth import LoginScene, RegisterScene
from vector_drift.hints import get_hint
from vector_drift.scenes.hint_popup import HintPopup

pytestmark = pytest.mark.usefixtures("pygame_display")


def _manager(account=None):
    audio = SimpleNamespace(play=lambda *a, **k: None, toggle_mute=lambda: None)
    return SceneManager(audio, account_manager=account)


def test_extended_scene_construction_and_draw():
    mgr = _manager()
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    for Scene in (AccountScene, ShopScene, MenuScene, LevelSelectScene, LoginScene, RegisterScene):
        scene = Scene(mgr)
        mgr.switch(scene)
        scene.draw(surface)
    fail = FailScene(mgr)
    mgr.switch(fail)
    fail.draw(surface)


def test_hint_popup_construction_and_draw():
    hint = get_hint(1)
    popup = HintPopup(hint)
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    popup.draw(surface)
    # event handling smoke
    for event in (
        pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RIGHT),
        pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE),
    ):
        popup.handle_event(event)
