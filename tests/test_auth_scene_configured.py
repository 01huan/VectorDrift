import time

import pygame
import pytest

from types import SimpleNamespace

from vector_drift import config
from vector_drift.account.auth_manager import AccountManager
from vector_drift.account.models import PlayerProfile
from vector_drift.scenes.base import SceneManager
from vector_drift.scenes.auth import LoginScene, RegisterScene

pytestmark = pytest.mark.usefixtures("pygame_display")


def _wait(am):
    for _ in range(50):
        am.poll()
        if not am.is_busy:
            return
        time.sleep(0.02)
    am.poll()


def _fake_account(monkeypatch, tmp_path):
    import vector_drift.account.auth_manager as am_mod
    monkeypatch.setattr(am_mod, "is_configured", lambda: True)
    # patch get_client
    user = SimpleNamespace(id="u1", email="a@b.com", email_confirmed_at="2026")
    sess = SimpleNamespace(access_token="at", refresh_token="rt")
    client = SimpleNamespace(auth=SimpleNamespace(
        sign_up=lambda creds: SimpleNamespace(user=user, session=sess),
        sign_in_with_password=lambda creds: SimpleNamespace(user=user, session=sess),
    ))
    monkeypatch.setattr(am_mod, "get_client", lambda: client)
    am = AccountManager()
    am.session_manager = SimpleNamespace(save=lambda d: None, clear=lambda: None, load=lambda: None)
    am.profile_manager = SimpleNamespace(
        fetch=lambda uid: PlayerProfile(user_id=uid, money=5),
        ensure_exists=lambda uid, email=None: PlayerProfile(user_id=uid, money=5, display_name=email),
        upsert=lambda p: None,
    )
    return am


def test_auth_scenes_configured_flow(monkeypatch, tmp_path):
    am = _fake_account(monkeypatch, tmp_path)
    mgr = SceneManager(SimpleNamespace(play=lambda *a, **k: None, toggle_mute=lambda: None, start_loop=lambda *a, **k: None, stop_loop=lambda *a, **k: None), account_manager=am)
    # Login
    scene = LoginScene(mgr)
    mgr.switch(scene)
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    scene.email_input.text = "a@b.com"
    scene.password_input.text = "password"
    scene._try_login()
    _wait(am)
    scene.draw(surface)
    # Register
    scene2 = RegisterScene(mgr)
    mgr.switch(scene2)
    scene2.email_input.text = "a@b.com"
    scene2.password_input.text = "password123"
    scene2.confirm_input.text = "password123"
    scene2._try_register()
    _wait(am)
    scene2.draw(surface)
