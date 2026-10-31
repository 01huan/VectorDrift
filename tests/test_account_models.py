from vector_drift.account.models import PlayerProfile, AccountUser


def test_account_user_defaults():
    u = AccountUser(id="u1")
    assert u.email is None
    assert u.email_confirmed is False
    assert u.access_token is None


def test_player_profile_to_row_and_from_row_roundtrip():
    p = PlayerProfile(
        user_id="u1",
        display_name="Alice",
        money=42,
        owned_ships={"ship01", "ship02"},
        purchased_items={"boost"},
        records={1: 12.5, 2: 3.0},
        collected_money_pickups={(1, (1.0, 2.0))},
        stats={"a": 1},
        updated_at="2026-01-01T00:00:00Z",
    )
    row = p.to_row()
    restored = PlayerProfile.from_row(row, "u1")
    assert restored.user_id == "u1"
    assert restored.display_name == "Alice"
    assert restored.money == 42
    assert restored.owned_ships == {"ship01", "ship02"}
    assert restored.purchased_items == {"boost"}
    assert restored.records == {1: 12.5, 2: 3.0}
    assert restored.collected_money_pickups == {(1, (1.0, 2.0))}
    assert restored.stats == {"a": 1}
    assert restored.updated_at == "2026-01-01T00:00:00Z"


def test_from_row_defaults_and_malformed():
    row = {
        "money": None,
        "records": {"bad": "x", "2": "3.5"},
        "collected_money_pickups": [[1, [1.0, 2.0]], "junk", [2]],
        "owned_ships": None,
        "purchased_items": None,
    }
    p = PlayerProfile.from_row(row, "guest")
    assert p.money == 0
    assert p.records == {2: 3.5}
    assert p.collected_money_pickups == {(1, (1.0, 2.0))}
    assert p.owned_ships == {"ship01"}
    assert p.purchased_items == set()
