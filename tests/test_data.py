from types import SimpleNamespace

from vector_drift.data import (
    _owned_ship_ids,
    ship_unlocked,
    default_ship_id,
    get_level,
    HoleSpec,
    SHIPS,
)


def test_owned_ship_ids_variants():
    s = SimpleNamespace(owned_ships=["ship02", "ship03"])
    assert _owned_ship_ids(s) == {"ship02", "ship03"}
    s2 = SimpleNamespace()
    owned = _owned_ship_ids(s2)
    assert owned == {"ship01"}
    assert s2.owned_ships == {"ship01"}
    assert _owned_ship_ids(None) == {"ship01"}


def test_ship_unlocked_variants():
    ship = SimpleNamespace(id="ship02")
    assert ship_unlocked(ship, owned={"ship02"}) is True
    assert ship_unlocked(ship, owned={"ship01"}) is False
    assert ship_unlocked("ship02", owned={"ship02"}) is True
    assert ship_unlocked("ship02", owned="ship02") is False
    # list/tuple id
    assert ship_unlocked(SimpleNamespace(id=["ship03"]), owned={"ship03"}) is True
    # session path
    s = SimpleNamespace(owned_ships={"ship02"})
    assert ship_unlocked("ship02", session=s) is True
    assert ship_unlocked("ship09", session=s) is False
    assert ship_unlocked("ship01") is True


def test_default_ship_id():
    s = SimpleNamespace(owned_ships={"ship01"})
    assert default_ship_id(session=s) in SHIPS
    assert default_ship_id() in SHIPS


def test_get_level_static_and_unknown():
    lvl = get_level(1)
    assert lvl.id == 1
    try:
        get_level(999999)
    except KeyError:
        pass
    else:
        raise AssertionError("expected KeyError")


def test_hole_spec_parsing():
    h = HoleSpec(black_center=(1.0, 2.0), white_center=(3.0, 4.0), radius=0.7)
    assert h.black_center == (1.0, 2.0)
    assert h.white_center == (3.0, 4.0)
    assert h.radius == 0.7

    h2 = HoleSpec((5.0, 6.0), (7.0, 8.0), 0.9)
    assert h2.black_center == (5.0, 6.0)
    assert h2.white_center == (7.0, 8.0)
    assert h2.radius == 0.9

    h3 = HoleSpec(black=(1.0, 1.0), white=(2.0, 2.0))
    assert h3.black_center == (1.0, 1.0)
    assert h3.white_center == (2.0, 2.0)

    h4 = HoleSpec.from_centers((0.0, 0.0), (1.0, 1.0))
    assert h4.radius == 0.5
