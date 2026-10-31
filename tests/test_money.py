from vector_drift.money import Money, Wallet, MoneyBag, CoinPurse, _coerce


class _HasAmount:
    def __init__(self, amount):
        self.amount = amount


class _HasValue:
    def __init__(self, value):
        self.value = value


class _HasBalance:
    def __init__(self, balance):
        self.balance = balance


def test_aliases_are_same_class():
    assert Wallet is Money
    assert MoneyBag is Money
    assert CoinPurse is Money


def test_default_and_repr():
    m = Money()
    assert m.amount == 0
    assert repr(m) == "Money(amount=0)"


def test_constructor_does_not_coerce():
    assert Money(2.9).amount == 2.9


def test_coerce_function():
    base = Money(5)
    assert _coerce(base) == 5
    assert _coerce(True) == 1
    assert _coerce(3) == 3
    assert _coerce(2.9) == 2
    assert _coerce(_HasAmount(7)) == 7
    assert _coerce(_HasValue(9)) == 9
    assert _coerce(_HasBalance(11)) == 11


def test_property_aliases_roundtrip():
    m = Money(4)
    assert m.value == 4 and m.balance == 4 and m.total == 4
    m.value = Money(2)
    assert m.amount == 2
    m.balance = 7
    assert m.amount == 7
    m.total = 1
    assert m.amount == 1


def test_add_grant_spend_and_chaining():
    m = Money(10)
    assert m.add(3) is m
    assert m.amount == 13
    assert m.grant(2).amount == 15
    assert m.spend(5).amount == 10


def test_add_defaults_to_one():
    m = Money(0)
    m.add()
    assert m.amount == 1
    m.grant()
    assert m.amount == 2
    m.spend()
    assert m.amount == 1


def test_int_float_eq_hash():
    m = Money(5)
    assert int(m) == 5
    assert float(m) == 5.0
    assert m == Money(5)
    assert m == 5
    assert m == 5.0
    assert m != Money(6)
    assert hash(m) == hash(5)


def test_arithmetic_operators():
    a = Money(4)
    b = Money(3)
    assert (a + b).amount == 7
    assert (a + 2).amount == 6
    assert (2 + a).amount == 6
    assert (a - b).amount == 1
    assert (a - 1).amount == 3
    assert (a - 10).amount == -6


def test_inplace_operators():
    m = Money(5)
    m += 3
    assert m.amount == 8
    m -= 2
    assert m.amount == 6
    m += Money(1)
    assert m.amount == 7


def test_coerce_callable_value_attr_falls_through():
    class _CallableValue:
        value = lambda self: 1

    import pytest

    with pytest.raises(TypeError):
        _coerce(_CallableValue())