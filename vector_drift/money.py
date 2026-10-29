"""Money (currency) model for the player.

A small, readable, and extensible value object: the player owns a
``Money`` instance whose amount changes as they play (pickups, level
clears, ...).  Keeping it as an object (instead of a bare int) lets us
add rules later (caps, spending, ...) without touching every call site.
"""

from __future__ import annotations

from dataclasses import dataclass


def _coerce(value) -> int:
    """Turn a Money / int / float into an int amount."""
    if isinstance(value, Money):
        return int(value.amount)
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    amount = getattr(value, "amount", None)
    if amount is not None:
        return int(amount)
    value_attr = getattr(value, "value", None)
    if value_attr is not None and not callable(value_attr):
        return int(value_attr)
    balance = getattr(value, "balance", None)
    if balance is not None and not callable(balance):
        return int(balance)
    return int(value)


@dataclass
class Money:
    """A player's money balance.

    ``amount`` is the canonical field; ``value`` / ``balance`` / ``total``
    are readable aliases so callers (and tests) can use whichever name
    fits.  Arithmetic keeps the result a ``Money`` instance.
    """

    amount: int = 0

    @property
    def value(self) -> int:
        return self.amount

    @value.setter
    def value(self, v) -> None:
        self.amount = _coerce(v)

    @property
    def balance(self) -> int:
        return self.amount

    @balance.setter
    def balance(self, v) -> None:
        self.amount = _coerce(v)

    @property
    def total(self) -> int:
        return self.amount

    @total.setter
    def total(self, v) -> None:
        self.amount = _coerce(v)

    def add(self, value=1) -> "Money":
        self.amount += _coerce(value)
        return self

    def grant(self, value=1) -> "Money":
        return self.add(value)

    def spend(self, value=1) -> "Money":
        self.amount -= _coerce(value)
        return self

    def __int__(self) -> int:
        return int(self.amount)

    def __float__(self) -> float:
        return float(self.amount)

    def __eq__(self, other) -> bool:
        if isinstance(other, Money):
            return self.amount == other.amount
        if isinstance(other, (int, float, bool)):
            return self.amount == other
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.amount)

    def __add__(self, other) -> "Money":
        return Money(self.amount + _coerce(other))

    def __radd__(self, other) -> "Money":
        return Money(_coerce(other) + self.amount)

    def __sub__(self, other) -> "Money":
        return Money(self.amount - _coerce(other))

    def __iadd__(self, other) -> "Money":
        self.amount += _coerce(other)
        return self

    def __isub__(self, other) -> "Money":
        self.amount -= _coerce(other)
        return self

    def __repr__(self) -> str:
        return f"Money(amount={self.amount})"


Wallet = Money
MoneyBag = Money
CoinPurse = Money