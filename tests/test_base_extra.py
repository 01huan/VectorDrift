import pygame
import pytest

from types import SimpleNamespace

from vector_drift import config
from vector_drift.scenes.base import SceneManager, Session

pytestmark = pytest.mark.usefixtures("pygame_display")


def test_scene_manager_basic():
    audio = SimpleNamespace(play=lambda *a, **k: None, toggle_mute=lambda: None)
    am = SimpleNamespace(poll=lambda: None)
    mgr = SceneManager(audio, account_manager=am)
    assert mgr.session is not None
    assert isinstance(mgr.session, Session)
    mgr.time = 0.0
    mgr.scene = SimpleNamespace(update=lambda dt: None, handle_event=lambda e: None, draw=lambda s: None)
    mgr.update(0.1)
    assert mgr.time == pytest.approx(0.1)
    mgr.quit()
    assert mgr.running is False
    # handle_event QUIT
    mgr.running = True
    mgr.handle_event(pygame.event.Event(pygame.QUIT))
    assert mgr.running is False
    # mute shortcut
    mgr2 = SceneManager(audio)
    mgr2.running = True
    mgr2.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_m, mod=pygame.KMOD_CTRL))
