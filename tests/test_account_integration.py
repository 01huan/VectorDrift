from types import SimpleNamespace

from vector_drift.account.integration import (
    apply_profile_to_session,
    session_to_profile,
    reset_session_to_guest,
    apply_guest_profile_to_session,
    session_to_guest_profile,
    load_guest_profile_into_session,
    save_guest_profile,
    clear_guest_profile,
)
from vector_drift.account.models import PlayerProfile
from vector_drift.money import Money


def _session():
    return SimpleNamespace(
        money=Money(0),
        owned_ships={"ship01"},
        purchased_items=set(),
        records={},
        collected_money_pickups=set(),
        stats={},
        display_name=None,
        user_id=None,
        email=None,
        auth_status="guest",
        profile_loaded=False,
        sync_status="idle",
        last_sync_error=None,
        fx_text="x",
        fy_text="y",
        random_seed=1,
        level_id=2,
        ship_id="ship02",
        hint_answer_confirmed=True,
    )


def test_session_to_profile_and_apply_roundtrip():
    s = _session()
    s.money = Money(10)
    s.owned_ships = {"ship01", "ship02"}
    s.records = {1: 5.0}
    s.collected_money_pickups = {(1, (1.0, 2.0))}
    s.stats = {"k": "v"}
    s.display_name = "Bob"

    profile = session_to_profile(s, "u9")
    assert profile.user_id == "u9"
    assert profile.money == 10
    assert profile.records == {1: 5.0}

    s2 = _session()
    apply_profile_to_session(s2, profile, "u9", "bob@example.com")
    assert s2.money.amount == 10
    assert s2.owned_ships == {"ship01", "ship02"}
    assert s2.records == {1: 5.0}
    assert s2.collected_money_pickups == {(1, (1.0, 2.0))}
    assert s2.display_name == "Bob"
    assert s2.user_id == "u9"
    assert s2.email == "bob@example.com"
    assert s2.auth_status == "authenticated"
    assert s2.profile_loaded is True
    assert s2.sync_status == "idle"
    assert s2.last_sync_error is None


def test_reset_session_to_guest():
    s = _session()
    s.money = Money(10)
    s.auth_status = "authenticated"
    reset_session_to_guest(s)
    assert s.money.amount == 0
    assert s.owned_ships == {"ship01"}
    assert s.purchased_items == set()
    assert s.records == {}
    assert s.collected_money_pickups == set()
    assert s.stats == {}
    assert s.user_id is None
    assert s.email is None
    assert s.display_name is None
    assert s.auth_status == "guest"
    assert s.profile_loaded is False
    assert s.sync_status == "idle"
    assert s.last_sync_error is None
    assert s.fx_text == ""
    assert s.fy_text == ""
    assert s.random_seed is None
    assert s.level_id == 1
    assert s.ship_id is None
    assert s.hint_answer_confirmed is False


def test_guest_profile_helpers_with_tmp_path(tmp_path, monkeypatch):
    from vector_drift.account import local_profile_manager as lpm

    monkeypatch.setattr(lpm, "_storage_path", lambda: tmp_path / "guest.json")

    s = _session()
    s.money = Money(7)
    save_guest_profile(s)
    assert (tmp_path / "guest.json").exists()

    s2 = _session()
    assert load_guest_profile_into_session(s2) is True
    assert s2.money.amount == 7

    # apply guest profile (no auth)
    p = PlayerProfile(user_id="guest", money=3)
    s3 = _session()
    apply_guest_profile_to_session(s3, p)
    assert s3.money.amount == 3
    assert s3.auth_status == "guest"
    assert s3.profile_loaded is False

    assert session_to_guest_profile(s3).user_id == "guest"

    clear_guest_profile(s3)
    assert not (tmp_path / "guest.json").exists()
