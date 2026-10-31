import pytest

from vector_drift import shop as shop_module
from vector_drift.shop import (
    ShopItem,
    Shop,
    register_item,
    unregister_item,
    get_item,
    all_items,
    items_for,
    can_purchase,
    purchase_item,
    _coerce_money,
    _owned_ship_ids,
    buy_item,
    buy,
    purchase,
)


class FakeSession:
    def __init__(self, money=0, owned=None, purchased=None):
        self.money = money
        self.owned_ships = set(owned or {"ship01"})
        self.purchased_items = set(purchased or set())


def test_coerce_money_variants():
    from vector_drift.money import Money

    assert _coerce_money(Money(7)) == 7
    assert _coerce_money(FakeSession(money=Money(3)).money) == 3
    # object with .value
    class V:
        value = 9

    assert _coerce_money(V()) == 9
    assert _coerce_money(5) == 5
    assert _coerce_money("4") == 4


def test_owned_ship_ids_variants():
    s = FakeSession()
    assert _owned_ship_ids(s) is s.owned_ships

    class S2:
        unlocked_ships = ["ship02", "ship03"]

    assert _owned_ship_ids(S2()) == {"ship02", "ship03"}

    class S3:
        purchased_ships = ("ship04",)

    assert _owned_ship_ids(S3()) == {"ship04"}

    class S4:
        owned_ship_ids = None
        owned_ships = None
        unlocked_ships = None
        purchased_ships = None


    s4 = S4()
    owned = _owned_ship_ids(s4)
    assert owned == {"ship01"}
    assert s4.owned_ships == {"ship01"}


def test_shop_item_defaults():
    item = ShopItem(id="x", name="X")
    s = FakeSession(money=10)
    assert item.available(s) is True
    assert item.owned(s) is False
    assert item.purchase(s) is None


def test_register_unregister_and_lookup():
    item = ShopItem(id="__test_item__", name="T", price=1)
    register_item(item)
    try:
        assert get_item("__test_item__") is item
        assert item in all_items()
    finally:
        unregister_item("__test_item__")
    assert get_item("__test_item__") is None


def test_items_for_filters_available():
    item = ShopItem(id="__avail__", name="A", price=1, available=lambda s: False)
    register_item(item)
    try:
        s = FakeSession(money=10)
        assert item not in items_for(s)
    finally:
        unregister_item("__avail__")


def test_can_purchase():
    item = ShopItem(id="__cp__", name="C", price=5)
    s = FakeSession(money=5)
    assert can_purchase(item, s) is True
    s2 = FakeSession(money=4)
    assert can_purchase(item, s2) is False
    item2 = ShopItem(id="__cp2__", name="C2", price=1, owned=lambda s: True)
    assert can_purchase(item2, s) is False


def test_purchase_item_success_and_purchased_set():
    item = ShopItem(id="__buy__", name="B", price=3)
    s = FakeSession(money=5)
    assert purchase_item(item, s) is True
    assert s.money == 2
    assert "__buy__" in s.purchased_items


def test_purchase_item_calls_purchase_and_handles_owned():
    calls = []

    def _purchase(s):
        calls.append(s)

    item = ShopItem(id="__buy2__", name="B2", price=1, purchase=_purchase)
    s = FakeSession(money=2)
    assert purchase_item(item, s) is True
    assert calls == [s]
    # already owned -> cannot purchase
    s2 = FakeSession(money=2, purchased={"__buy2__"})
    item2 = ShopItem(id="__buy2__", name="B2", price=1, owned=lambda s: "__buy2__" in s.purchased_items)
    assert can_purchase(item2, s2) is False


def test_purchase_item_failure_paths():
    # purchase raises -> False
    item = ShopItem(id="__failbuy__", name="F", price=1, purchase=lambda s: (_ for _ in ()).throw(ValueError("boom")))
    s = FakeSession(money=2)
    assert purchase_item(item, s) is False

    # money without spend method -> fallback path
    class MoneyLike:
        def __init__(self, amount):
            self.amount = amount

    item2 = ShopItem(id="__fallback__", name="FB", price=2)
    s2 = FakeSession(money=MoneyLike(5))
    assert purchase_item(item2, s2) is True
    assert s2.money.amount == 3


def test_shop_class():
    item = ShopItem(id="__shopitem__", name="S", price=1)
    shop = Shop([item])
    assert shop.all() == [item]
    assert shop.get("__shopitem__") is item
    assert shop.get("__nope__") is None
    s = FakeSession(money=1)
    assert shop.can_buy("__shopitem__", s) is True
    assert shop.buy("__shopitem__", s) is True
    assert shop.buy("__missing__", s) is False


def test_aliases_callable():
    assert buy_item is purchase_item
    assert buy is purchase_item
    assert purchase is purchase_item


def test_register_ships_populated():
    # _register_ships ran at import; at least ship02 should exist
    item = get_item("ship02")
    assert item is not None
    assert item.category == "ship"
    assert item.price > 0


def test_owned_ship_ids_public():
    s = FakeSession(owned={"ship01", "ship02"})
    assert shop_module.owned_ship_ids(s) == s.owned_ships
