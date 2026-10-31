import pygame
import pytest
import time

from types import SimpleNamespace

from vector_drift import config
from vector_drift.scenes.base import SceneManager
from vector_drift.scenes.account import AccountScene
from vector_drift.account.auth_manager import AccountManager
from vector_drift.account.models import PlayerProfile

pytestmark = pytest.mark.usefixtures("pygame_display")


def _account():
    am = AccountManager()
    am.current_user = SimpleNamespace(id="u1", email="a@b.com")
    am.profile = PlayerProfile(user_id="u1", money=5)
    am.status = "authenticated"
    am.is_configured = lambda: True
    am.is_authenticated = lambda: True
    am.is_busy = False
    am.load_profile_async = lambda on_success=None, on_error=None: (on_success(am.profile) if on_success else None)
    am.sign_out_async = lambda on_success=None, on_error=None: (on_success() if on_success else None)
    am.delete_local_data = lambda session=None: None
    return am


def test_account_scene_authenticated_flow():
    am = _account()
    mgr = SceneManager(SimpleNamespace(play=lambda *a, **k: None, toggle_mute=lambda: None, start_loop=lambda *a, **k: None, stop_loop=lambda *a, **k: None), account_manager=am)
    scene = AccountScene(mgr)
    mgr.switch(scene)
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    scene.draw(surface)
    scene.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=scene.refresh_button.rect.center))
    scene.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=scene.delete_local_button.rect.center))
    scene.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=scene.logout_button.rect.center))
    scene.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=scene.back_button.rect.center))
