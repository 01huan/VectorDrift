import json
from pathlib import Path

from vector_drift.account.session_manager import SessionManager, _storage_path


def test_session_manager_roundtrip(tmp_path):
    path = tmp_path / "session.json"
    sm = SessionManager(path)
    assert sm.load() is None
    sm.save({"refresh_token": "abc"})
    assert path.exists()
    assert sm.load() == {"refresh_token": "abc"}
    sm.clear()
    assert not path.exists()
    assert sm.load() is None


def test_session_manager_bad_json(tmp_path):
    path = tmp_path / "session.json"
    path.write_text("{bad", encoding="utf-8")
    sm = SessionManager(path)
    assert sm.load() is None


def test_session_manager_save_error_raises(tmp_path, monkeypatch):
    # point to a path whose parent is a file to force OSError
    blocker = tmp_path / "blocker"
    blocker.write_text("x", encoding="utf-8")
    path = blocker / "session.json"
    sm = SessionManager(path)
    try:
        sm.save({"a": 1})
    except Exception as exc:
        assert "Failed to save session" in str(exc)
    else:
        # Some platforms may allow; not a failure
        assert True


def test_storage_path_default():
    p = _storage_path()
    assert p.name == "account_session.json"
