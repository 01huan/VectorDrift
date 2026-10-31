import importlib

import pytest

from vector_drift.account.models import PlayerProfile


ALIAS_MODULES = [
    "vector_drift.account.guest_manager",
    "vector_drift.account.guest_profile",
    "vector_drift.account.guest_profile_manager",
    "vector_drift.account.guest_session",
    "vector_drift.account.local_data",
    "vector_drift.account.local_manager",
    "vector_drift.account.local_profile",
    "vector_drift.account.local_store",
]


@pytest.mark.parametrize("modname", ALIAS_MODULES)
def test_alias_module_storage_roundtrip(modname, tmp_path, monkeypatch):
    mod = importlib.import_module(modname)
    monkeypatch.setattr(mod, "_storage_path", lambda: tmp_path / f"{modname.split('.')[-1]}.json")
    mgr = mod.LocalProfileManager()
    assert mgr.load() is None
    mgr.save(PlayerProfile(user_id="g", money=7, display_name="Alias"))
    assert mgr.exists() is True
    loaded = mgr.load()
    assert loaded is not None
    assert loaded.money == 7
    assert loaded.display_name == "Alias"
    mgr.save_profile(PlayerProfile(user_id="g", money=9))
    assert mgr.load().money == 9
    # session-like save
    class S:
        money = 3
        records = {}

    from vector_drift.account import integration as integ

    monkeypatch.setattr(integ, "session_to_profile", lambda s, uid: PlayerProfile(user_id=uid, money=11))
    mgr.save_session(S())
    assert mgr.load().money == 11
    mgr.clear()
    assert mgr.load() is None
    # delete aliases
    mgr.save(PlayerProfile(user_id="g", money=1))
    for method in ("delete", "delete_profile", "reset", "delete_local_records" if hasattr(mgr, "delete_local_records") else "clear"):
        if hasattr(mgr, method):
            getattr(mgr, method)()
            mgr.save(PlayerProfile(user_id="g", money=1))
    mgr.clear()


@pytest.mark.parametrize("modname", ALIAS_MODULES)
def test_alias_module_bad_paths(modname, tmp_path, monkeypatch):
    mod = importlib.import_module(modname)
    path = tmp_path / f"bad_{modname.split('.')[-1]}.json"
    monkeypatch.setattr(mod, "_storage_path", lambda: path)
    mgr = mod.LocalProfileManager()
    path.write_text("{bad", encoding="utf-8")
    assert mgr.load() is None
    path.write_text("[1,2,3]", encoding="utf-8")
    assert mgr.load() is None
    # coerce None
    assert mgr._coerce(None) is None
