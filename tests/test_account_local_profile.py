import json

import pytest

from vector_drift.account.local_profile_manager import LocalProfileManager
from vector_drift.account.models import PlayerProfile


def test_local_profile_manager_roundtrip(tmp_path):
    mgr = LocalProfileManager(tmp_path / "p.json")
    assert mgr.exists() is False
    assert mgr.load() is None

    p = PlayerProfile(user_id="g", money=5, display_name="Guest")
    mgr.save(p)
    assert mgr.exists() is True
    loaded = mgr.load()
    assert loaded is not None
    assert loaded.money == 5
    assert loaded.display_name == "Guest"

    mgr.save_profile(p)
    mgr.save_session(None)  # None -> no-op
    mgr.clear()
    assert mgr.exists() is False
    assert mgr.load() is None


def test_local_profile_manager_load_variants(tmp_path):
    path = tmp_path / "p.json"
    mgr = LocalProfileManager(path)

    # bad json
    path.write_text("{not json", encoding="utf-8")
    assert mgr.load() is None

    # non-dict
    path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    assert mgr.load() is None

    # load_profile alias
    path.write_text(json.dumps({"money": 9}), encoding="utf-8")
    assert mgr.load_profile().money == 9


def test_local_profile_manager_coerce_and_session_save(tmp_path, monkeypatch):
    from vector_drift.account import integration as integ

    def _session_to_profile(session, uid):
        return PlayerProfile(user_id=uid, money=11)

    monkeypatch.setattr(integ, "session_to_profile", _session_to_profile)

    mgr = LocalProfileManager(tmp_path / "p.json")

    # session-like object
    class S:
        money = 1
        records = {}

    mgr.save(S())
    assert mgr.load().money == 11

    # dict
    mgr2 = LocalProfileManager(tmp_path / "p2.json")
    mgr2.save({"money": 7})
    assert mgr2.load().money == 7

    # None -> no-op
    mgr3 = LocalProfileManager(tmp_path / "p3.json")
    mgr3.save(None)
    assert not (tmp_path / "p3.json").exists()


def test_delete_aliases(tmp_path):
    mgr = LocalProfileManager(tmp_path / "p.json")
    mgr.save(PlayerProfile(user_id="g", money=1))
    for method in ("delete", "delete_profile", "reset"):
        getattr(mgr, method)()
        # recreate for next
        mgr.save(PlayerProfile(user_id="g", money=1))
    mgr.clear()
    assert mgr.load() is None
