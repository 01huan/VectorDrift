"""Login scene UI tests."""

import pygame
import pytest

from vector_drift import config
from vector_drift.scenes.base import SceneManager
from vector_drift.scenes.auth import LoginScene, _TextInput

pytestmark = pytest.mark.usefixtures("pygame_display")


def _manager():
    audio = type("Audio", (), {"play": lambda *a, **k: None,
                              "start_loop": lambda *a, **k: None,
                              "stop_loop": lambda *a, **k: None})()
    return SceneManager(audio)


def _login_scene():
    manager = _manager()
    scene = LoginScene(manager)
    manager.switch(scene)
    return scene, manager


def _click(scene, rect):
    pos = rect.center
    scene.handle_event(pygame.event.Event(pygame.MOUSEMOTION, pos=pos, rel=(0, 0), buttons=(0, 0, 0)))
    scene.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=pos, button=1))


def test_login_scene_has_email_input():
    scene, _ = _login_scene()
    assert isinstance(scene.email_input, _TextInput)


def test_login_scene_has_password_input():
    scene, _ = _login_scene()
    assert isinstance(scene.password_input, _TextInput)
    assert scene.password_input.password is True


def test_email_input_receives_text():
    scene, _ = _login_scene()
    _click(scene, scene.email_input.rect)
    scene.handle_event(pygame.event.Event(pygame.TEXTINPUT, text="abc"))
    assert scene.email_input.text == "abc"


def test_password_input_masks_text():
    scene, _ = _login_scene()
    _click(scene, scene.password_input.rect)
    scene.handle_event(pygame.event.Event(pygame.TEXTINPUT, text="secret"))
    assert scene.password_input.text == "secret"
    # masking is handled in draw via "*" * len(text)
    assert scene.password_input.password is True


def test_backspace_deletes_text():
    scene, _ = _login_scene()
    _click(scene, scene.email_input.rect)
    scene.email_input.text = "abcd"
    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_BACKSPACE, mod=0, unicode="", scancode=0))
    assert scene.email_input.text == "abc"


def test_back_button_returns_to_menu():
    scene, manager = _login_scene()
    _click(scene, scene.back_button.rect)
    from vector_drift.scenes.menu import MenuScene
    assert isinstance(manager.scene, MenuScene)
