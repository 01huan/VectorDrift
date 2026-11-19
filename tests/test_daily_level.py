"""Daily challenge generator: one map per day, the same for every player.

Everything is decided by the day's seed, so these tests can pin exact days.
"""

from datetime import date, datetime, timedelta, timezone

from vector_drift import config
from vector_drift.daily_level import daily_seed, daily_today


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
