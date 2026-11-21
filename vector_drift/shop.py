"""Shop system: extensible catalog of purchasable items.

The shop sells the active abilities only. Ships are no longer sold: each
level flies its own ship (data_models.level_ship_id); old saves keep their
owned-ship list, which is no longer used.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


from .accessors import owned_ship_ids as _owned_ship_ids


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


def _restore_money(session, amount: int) -> bool:
    """Set the session's balance back to ``amount`` (best effort)."""
    money = session.money
    if hasattr(money, "amount") and not isinstance(money, (int, float, bool, str, bytes)):
        try:
            money.amount = int(amount)
            return True
        except Exception:
            pass
    for attr in ("value", "balance", "total"):
        attr_value = getattr(money, attr, None)
        if attr_value is not None and not callable(attr_value):
            try:
                setattr(money, attr, int(amount))
                return True
            except Exception:
                pass
    try:
        session.money = int(amount)
        return True
    except Exception:
        return False


def purchase_item(item: ShopItem, session) -> bool:
    if not can_purchase(item, session):
        return False
    before = _coerce_money(session.money)
    try:
        session.money.spend(item.price)
    except Exception:
        new_amount = before - int(item.price)
        money = session.money
        updated = False
        if hasattr(money, "amount") and not isinstance(money, (int, float, bool, str, bytes)):
            try:
                money.amount = new_amount
                updated = True
            except Exception:
                updated = False
        if not updated:
            try:
                session.money = new_amount
            except Exception:
                pass
    try:
        item.purchase(session)
    except Exception:
        # Never charge for an item that was not granted.
        _restore_money(session, before)
        return False
    # Abilities manage their own ownership (charges or purchased_items via
    # their _purchase callback); recording every ability id here would pollute
    # purchased_items with consumable ability ids.  Ships and other items are
    # still tracked the generic way.
    if getattr(item, "category", None) != "ability":
        try:
            purchased = getattr(session, "purchased_items", None)
            if purchased is None:
                purchased = set()
                setattr(session, "purchased_items", purchased)
            purchased.add(item.id)
        except Exception:
            pass
    return True





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


def _register_abilities() -> None:
    from .abilities import ABILITIES

    for aid, ability in ABILITIES.items():
        if aid in ITEMS:
            continue

        def _owned(s, aid=aid, consumable=ability.consumable):
            if consumable:
                return False
            return aid in getattr(s, "purchased_items", set())

        def _purchase(s, aid=aid, consumable=ability.consumable):
            if consumable:
                charges = getattr(s, "ability_charges", None)
                if not isinstance(charges, dict):
                    charges = {}
                    setattr(s, "ability_charges", charges)
                charges[aid] = int(charges.get(aid, 0)) + 1
            else:
                purchased = getattr(s, "purchased_items", None)
                if not isinstance(purchased, set):
                    purchased = set()
                    setattr(s, "purchased_items", purchased)
                purchased.add(aid)

        register_item(ShopItem(
            id=aid,
            name=ability.name,
            description=ability.description,
            price=ability.price,
            category="ability",
            icon="ship",
            owned=_owned,
            purchase=_purchase,
        ))


_register_abilities()


def owned_ship_ids(session) -> set:
    return _owned_ship_ids(session)
