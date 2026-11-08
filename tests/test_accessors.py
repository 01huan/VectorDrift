from types import SimpleNamespace

from vector_drift import accessors


def test_owned_ship_ids_none():
    assert accessors.owned_ship_ids(None) == {"ship01"}


def test_owned_ship_ids_attribute_set():
    session = SimpleNamespace(owned_ships={"a", "b"})
    assert accessors.owned_ship_ids(session) is session.owned_ships


def test_owned_ship_ids_fallback_attrs():
    session = SimpleNamespace(unlocked_ships=["ship02", "ship03"])
    assert accessors.owned_ship_ids(session) == {"ship02", "ship03"}

    session2 = SimpleNamespace(purchased_ships=("ship04",), owned_ship_ids=None)
    assert accessors.owned_ship_ids(session2) == {"ship04"}


def test_owned_ship_ids_missing_attr_defaults_and_caches():
    session = SimpleNamespace()
    owned = accessors.owned_ship_ids(session)
    assert owned == {"ship01"}
    class S:
        pass
    empty = S()
    owned = accessors.owned_ship_ids(empty)
    assert owned == {"ship01"}
    assert getattr(empty, "owned_ships", None) == {"ship01"}
