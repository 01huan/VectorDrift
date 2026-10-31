import pygame
import pytest

from types import SimpleNamespace

from vector_drift import config
from vector_drift.scenes.base import SceneManager
from vector_drift.scenes.auth import LoginScene, RegisterScene

pytestmark = pytest.mark.usefixtures("pygame_display")


def _manager(account=None):
    audio = SimpleNamespace(play=lambda *a, **k: None, toggle_mute=lambda: None, start_loop=lambda *a, **k: None, stop_loop=lambda *a, **k: None)
    return SceneManager(audio, account_manager=account)


def test_auth_scene_validation_and_busy():
    # Unconfigured account (None)
    mgr = _manager(None)
    for Scene in (LoginScene, RegisterScene):
        scene = Scene(mgr)
        mgr.switch(scene)
        surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
        # empty submit
        if hasattr(scene, "_try_login"):
            scene._try_login()
        if hasattr(scene, "_try_register"):
            scene._try_register()
        # mismatch / short password for register
        if hasattr(scene, "email_input"):
            scene.email_input.text = "a@b.com"
        if hasattr(scene, "password_input"):
            scene.password_input.text = "123"
        if hasattr(scene, "confirm_input"):
            scene.confirm_input.text = "456"
        if hasattr(scene, "_try_register"):
            scene._try_register()
        if hasattr(scene, "password_input"):
            scene.password_input.text = "123456"
        if hasattr(scene, "confirm_input"):
            scene.confirm_input.text = "123456"
        if hasattr(scene, "_try_register"):
            scene._try_register()
        scene.draw(surface)

    # Busy account
    am = SimpleNamespace(is_configured=lambda: True, is_busy=True, is_authenticated=lambda: False)
    mgr2 = _manager(am)
    scene = LoginScene(mgr2)
    mgr2.switch(scene)
    scene.email_input.text = "a@b.com"
    scene.password_input.text = "password"
    scene._try_login()
    scene2 = RegisterScene(mgr2)
    mgr2.switch(scene2)
    scene2.email_input.text = "a@b.com"
    scene2.password_input.text = "password123"
    scene2.confirm_input.text = "password123"
    scene2._try_register()
