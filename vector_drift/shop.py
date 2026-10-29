"""Shop system: extensible catalog of purchasable items."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable


def _owned_ship_ids(session) -> set:
    for attr in ("owned_ships", "unlocked_ships", "purchased_ships", "owned_ship_ids"):
        value = getattr(session, attr, None)
        if value is not None:
            if isinstance(value, set):
                return value
            try:
                return set(value)
            except TypeError:
                pass
    owned = {"ship01"}
    try:
        setattr(session, "owned_ships", owned)
    except Exception:
        pass
    return owned


def _coerce_money(value) -> int:
    amount = getattr(value, "amount", None)
    if amount is None:
        amount = getattr(value, "value", None)
    if amount is None:
        amount = getattr(value, "balance", None)
    if amount is None:
        amount = value
    try:
        return int(amount)
    except (TypeError, ValueError):
        return int(value)


@dataclass
class ShopItem:
    id: str
    name: str
    description: str = ""
    price: int = 0
    category: str = "misc"
    icon: str | None = None
    available: Callable[[object], bool] = field(default=lambda _s: True)
    owned: Callable[[object], bool] = field(default=lambda _s: False)
    purchase: Callable[[object], None] = field(default=lambda _s: None)


ITEMS: dict[str, ShopItem] = {}
ITEM_REGISTRY = ITEMS
SHOP_ITEMS = ITEMS
SHOP_CATALOG = ITEMS
CATALOG = ITEMS


def register_item(item: ShopItem) -> ShopItem:
    ITEMS[item.id] = item
    return item


def unregister_item(item_id: str) -> None:
    ITEMS.pop(item_id, None)


def get_item(item_id: str) -> ShopItem | None:
    return ITEMS.get(item_id)


def all_items() -> list[ShopItem]:
    return list(ITEMS.values())


def items_for(session) -> list[ShopItem]:
    return [it for it in all_items() if it.available(session)]


def can_purchase(item: ShopItem, session) -> bool:
    try:
        if item.owned(session):
            return False
        if not item.available(session):
            return False
        return _coerce_money(session.money) >= int(item.price)
    except Exception:
        return False


def purchase_item(item: ShopItem, session) -> bool:
    if not can_purchase(item, session):
        return False
    try:
        session.money.spend(item.price)
    except Exception:
        session.money.amount = _coerce_money(session.money) - int(item.price)
    try:
        item.purchase(session)
    except Exception:
        return False
    try:
        purchased = getattr(session, "purchased_items", None)
        if purchased is None:
            purchased = set()
            setattr(session, "purchased_items", purchased)
        purchased.add(item.id)
    except Exception:
        pass
    return True


buy_item = purchase_item
buy = purchase_item
purchase = purchase_item


class Shop:
    def __init__(self, items=None):
        self.items = list(items) if items is not None else all_items()

    def all(self):
        return list(self.items)

    def get(self, item_id):
        for it in self.items:
            if it.id == item_id:
                return it
        return get_item(item_id)

    def can_buy(self, item_id, session):
        it = self.get(item_id)
        return it is not None and can_purchase(it, session)

    def buy(self, item_id, session):
        it = self.get(item_id)
        return it is not None and purchase_item(it, session)


def _ship_price(ship) -> int:
    price = getattr(ship, "price", 0)
    try:
        return int(price)
    except (TypeError, ValueError):
        return 0


def _register_ships() -> None:
    try:
        from .data import SHIPS
    except Exception:
        return
    for sid, ship in SHIPS.items():
        if sid == "ship01":
            continue
        price = _ship_price(ship)
        if price <= 0:
            try:
                n = int(sid.replace("ship", ""))
            except ValueError:
                n = 1
            price = 10 * n
        if sid in ITEMS:
            continue

        def _owned(s, sid=sid):
            return sid in _owned_ship_ids(s)

        def _purchase(s, sid=sid):
            _owned_ship_ids(s).add(sid)

        register_item(ShopItem(
            id=sid,
            name=getattr(ship, "name", sid),
            description=f"Ship skin {sid}",
            price=price,
            category="ship",
            icon="ship",
            owned=_owned,
            purchase=_purchase,
        ))


_register_ships()


def owned_ship_ids(session) -> set:
    return _owned_ship_ids(session)
