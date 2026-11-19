"""Daily challenge generator: one map per day, the same for every player.

Everything is decided by the day's seed, so these tests can pin exact days.
"""

import random
import re
from datetime import date, datetime, timedelta, timezone

import pytest

from vector_drift import config
from vector_drift.daily_level import (CONSTANT_TERMS, NONZERO_COEFFS, TEMPLATES, daily_seed,
                                      daily_today, format_linear, pick_field)
from vector_drift.expr_parser import parse_expression


def test_today_switches_at_midnight_taiwan_time():
    before = datetime(2026, 11, 19, 15, 59, tzinfo=timezone.utc)
    after = datetime(2026, 11, 19, 16, 0, tzinfo=timezone.utc)

    assert daily_today(before) == date(2026, 11, 19)
    assert daily_today(after) == date(2026, 11, 20)


def test_today_accepts_any_aware_time():
    new_york = timezone(timedelta(hours=-5))

    assert daily_today(datetime(2026, 11, 19, 11, 0, tzinfo=new_york)) == date(2026, 11, 20)


def test_today_without_an_argument_is_a_date():
    assert isinstance(daily_today(), date)


def test_seed_is_the_date_and_generator_version():
    assert config.DAILY_GENERATOR_VERSION == 1
    assert daily_seed(date(2026, 11, 19)) == 2026111901
    assert daily_seed(date(2027, 1, 2)) == 2027010201


# --- Force field templates ---------------------------------------------------

PROBE_POINTS = [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0), (2.0, 3.0), (-1.5, 0.5), (-8.0, -4.0)]


def _linear(const, x_coeff, y_coeff, x, y):
    return const + x_coeff * x + y_coeff * y


def test_fields_from_1000_seeds_parse_to_the_chosen_coefficients():
    for seed in range(1000):
        field = pick_field(random.Random(seed))
        a, b, c, d, e, f = field.coeffs
        for text, (const, x_coeff, y_coeff) in ((field.fx, (a, b, c)), (field.fy, (d, e, f))):
            assert ".0" not in text, (seed, text)
            assert not re.search(r"(?<![\d.])1[xy]", text), (seed, text)
            assert not re.search(r"[+-]\s*[+-]", text), (seed, text)
            expr = parse_expression(text)
            for x, y in PROBE_POINTS:
                assert expr.evaluate(x, y) == _linear(const, x_coeff, y_coeff, x, y), (seed, text)


def test_template_coefficient_rules_hold():
    seen = set()
    for seed in range(1000):
        field = pick_field(random.Random(seed))
        a, b, c, d, e, f = field.coeffs
        seen.add(field.template)
        assert a in CONSTANT_TERMS and d in CONSTANT_TERMS
        if field.template == "swing":
            assert (b, c, e) == (0, 0, 0) and f < 0
        elif field.template == "side_swing":
            assert (c, e, f) == (0, 0, 0) and b < 0
        elif field.template == "parabola":
            assert (b, c, f) == (0, 0, 0) and e != 0
        elif field.template == "rotation":
            assert (b, f) == (0, 0) and c * e < 0
        else:
            assert field.template == "two_axis"
            assert (c, e) == (0, 0) and b in NONZERO_COEFFS and f in NONZERO_COEFFS
    assert seen == set(TEMPLATES)


def test_same_seed_gives_the_same_field():
    assert pick_field(random.Random(7)) == pick_field(random.Random(7))


@pytest.mark.parametrize("terms, text", [
    ((2, 0, -1), "-y + 2"),
    ((1, 0, -1), "-y + 1"),
    ((-3, 0.5, 0), "0.5x - 3"),
    ((0, -1, 0), "-x"),
    ((0, 1, 0), "x"),
    ((-0.5, 0, 0), "-0.5"),
    ((0, 0, 0), "0"),
    ((3, 0, 2), "2y + 3"),
    ((0.5, -0.25, 0), "-0.25x + 0.5"),
    ((-2, 0, 0.1), "0.1y - 2"),
])
def test_format_linear_writes_what_a_player_would_type(terms, text):
    assert format_linear(*terms) == text
