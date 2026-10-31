import time
from types import SimpleNamespace

import pytest

from vector_drift.account.auth_manager import AccountManager, AccountUser
from vector_drift.account.models import PlayerProfile
from vector_drift.account.errors import AuthenticationError


def _wait(am, timeout=2.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        am.poll()
        if not am.is_busy:
            return
        time.sleep(0.02)
    am.poll()


def _fake_user():
    return SimpleNamespace(id="u1", email="a@b.com", email_confirmed_at="2026-01-01")


def _fake_session():
    return SimpleNamespace(access_token="at", refresh_token="rt")


def _setup(am, monkeypatch, client, session_data=None):
    monkeypatch.setattr(am, "is_configured", lambda: True)
    monkeypatch.setattr("vector_drift.account.auth_manager.get_client", lambda: client)
    am.session_manager = SimpleNamespace(
        save=lambda data: None,
        clear=lambda: None,
        load=lambda: session_data,
    )
    am.profile_manager = SimpleNamespace(
        fetch=lambda uid: PlayerProfile(user_id=uid, money=5),
        ensure_exists=lambda uid, email=None: PlayerProfile(user_id=uid, money=5, display_name=email),
        upsert=lambda profile: None,
    )


def test_sign_up_async_success(monkeypatch):
    user = _fake_user()
    sess = _fake_session()
    client = SimpleNamespace(auth=SimpleNamespace(
        sign_up=lambda creds: SimpleNamespace(user=user, session=sess),
    ))
    am = AccountManager()
    _setup(am, monkeypatch, client)
    successes = []
    am.sign_up_async("a@b.com", "pw", on_success=successes.append)
    _wait(am)
    assert am.current_user is not None
    assert am.current_user.id == "u1"
    assert am.status == "authenticated"
    assert successes and successes[0].id == "u1"


def test_sign_up_async_no_user(monkeypatch):
    client = SimpleNamespace(auth=SimpleNamespace(
        sign_up=lambda creds: SimpleNamespace(user=None, session=None),
    ))
    am = AccountManager()
    _setup(am, monkeypatch, client)
    errors = []
    am.sign_up_async("a@b.com", "pw", on_error=errors.append)
    _wait(am)
    assert errors
    assert "no user returned" in str(errors[0])


def test_sign_in_async_success(monkeypatch):
    user = _fake_user()
    sess = _fake_session()
    client = SimpleNamespace(auth=SimpleNamespace(
        sign_in_with_password=lambda creds: SimpleNamespace(user=user, session=sess),
    ))
    am = AccountManager()
    _setup(am, monkeypatch, client)
    successes = []
    am.sign_in_async("a@b.com", "pw", on_success=successes.append)
    _wait(am)
    assert am.status == "authenticated"
    assert successes


def test_sign_in_async_invalid(monkeypatch):
    client = SimpleNamespace(auth=SimpleNamespace(
        sign_in_with_password=lambda creds: SimpleNamespace(user=None, session=None),
    ))
    am = AccountManager()
    _setup(am, monkeypatch, client)
    errors = []
    am.sign_in_async("a@b.com", "pw", on_error=errors.append)
    _wait(am)
    assert errors


def test_sign_out_async(monkeypatch):
    user = _fake_user()
    sess = _fake_session()
    client = SimpleNamespace(auth=SimpleNamespace(sign_out=lambda: None))
    am = AccountManager()
    _setup(am, monkeypatch, client)
    am.current_user = AccountUser(id="u1", email="a@b.com", access_token="at", refresh_token="rt")
    am.status = "authenticated"
    successes = []
    am.sign_out_async(on_success=lambda: successes.append(True))
    _wait(am)
    assert successes
    assert am.current_user is None
    assert am.status == "guest"


def test_restore_session_no_saved(monkeypatch):
    client = SimpleNamespace(auth=SimpleNamespace())
    am = AccountManager()
    _setup(am, monkeypatch, client, session_data=None)
    errors = []
    am.restore_session_async(on_error=errors.append)
    _wait(am)
    assert errors
    assert "No saved session" in str(errors[0])


def test_restore_session_success(monkeypatch):
    user = _fake_user()
    sess = _fake_session()
    client = SimpleNamespace(auth=SimpleNamespace(
        set_session=lambda a, b: None,
        get_user=lambda: SimpleNamespace(user=user),
        refresh_session=lambda rt: SimpleNamespace(user=user, session=sess),
    ))
    am = AccountManager()
    _setup(am, monkeypatch, client, session_data={
        "access_token": "at", "refresh_token": "rt", "user_id": "u1", "email": "a@b.com",
    })
    successes = []
    am.restore_session_async(on_success=successes.append)
    _wait(am)
    assert am.status == "authenticated"
    assert successes


def test_load_profile_async_not_authenticated():
    am = AccountManager()
    errors = []
    am.load_profile_async(on_error=errors.append)
    assert errors
    assert "Not authenticated" in str(errors[0])


def test_load_profile_async_success(monkeypatch):
    client = SimpleNamespace(auth=SimpleNamespace())
    am = AccountManager()
    _setup(am, monkeypatch, client)
    am.current_user = AccountUser(id="u1", email="a@b.com")
    successes = []
    am.load_profile_async(on_success=successes.append)
    _wait(am)
    assert am.profile is not None
    assert successes


def test_save_profile_async_success(monkeypatch):
    client = SimpleNamespace(auth=SimpleNamespace())
    am = AccountManager()
    _setup(am, monkeypatch, client)
    successes = []
    profile = PlayerProfile(user_id="u1", money=9)
    am.save_profile_async(profile, on_success=lambda: successes.append(True))
    _wait(am)
    assert successes
    assert am.profile == profile


def test_save_profile_async_error(monkeypatch):
    client = SimpleNamespace(auth=SimpleNamespace())
    am = AccountManager()
    _setup(am, monkeypatch, client)
    am.profile_manager.upsert = lambda p: (_ for _ in ()).throw(RuntimeError("boom"))
    errors = []
    profile = PlayerProfile(user_id="u1", money=9)
    am.save_profile_async(profile, on_error=errors.append)
    _wait(am)
    assert errors
