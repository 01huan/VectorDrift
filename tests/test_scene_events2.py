import pygame
import pytest

from types import SimpleNamespace

from vector_drift import config
from vector_drift.scenes.base import SceneManager
from vector_drift.scenes.auth import LoginScene, RegisterScene
from vector_drift.hints import get_hint
from vector_drift.scenes.hint_popup import HintPopup

pytestmark = pytest.mark.usefixtures("pygame_display")


def _manager(account=None):
    audio = SimpleNamespace(play=lambda *a, **k: None, toggle_mute=lambda: None, start_loop=lambda *a, **k: None, stop_loop=lambda *a, **k: None)
    return SceneManager(audio, account_manager=account)


def test_auth_scenes_events():
    mgr = _manager()
    for Scene in (LoginScene, RegisterScene):
        scene = Scene(mgr)
        mgr.switch(scene)
        surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
        scene.draw(surface)
        if hasattr(scene, "email_input"):
            scene.email_input.active = True
            scene.email_input.handle_event(pygame.event.Event(pygame.TEXTINPUT, text="a@b.com"))
        if hasattr(scene, "password_input"):
            scene.password_input.active = True
            scene.password_input.handle_event(pygame.event.Event(pygame.TEXTINPUT, text="password"))
        if hasattr(scene, "confirm_input"):
            scene.confirm_input.active = True
            scene.confirm_input.handle_event(pygame.event.Event(pygame.TEXTINPUT, text="password"))
        if hasattr(scene, "_try_login"):
            scene._try_login()
        if hasattr(scene, "_try_register"):
            scene._try_register()
        if hasattr(scene, "back_button"):
            scene.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=scene.back_button.rect.center))
        scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))


def test_hint_popup_events():
    hint = get_hint(1)
    popup = HintPopup(hint)
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    popup.draw(surface)
    popup.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RIGHT))
    popup.draw(surface)
    popup.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
    popup.draw(surface)
    popup.confirming = True
    popup.draw(surface)
    popup.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
    popup.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
    if popup.apply_buttons:
        b = popup.apply_buttons[0]
        popup.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=b.rect.center))
