"""Daily challenge: one generated map per day, the same for every player.

The map is built answer first: pick a simple force field, fly it on an
empty map, take a point of its path as the target and only then place the
rocks outside that path. So every daily map is solvable by construction and
the chosen force field is its reference answer.

Generation is decided by the day's seed alone (same day + same
DAILY_GENERATOR_VERSION -> the same map on every computer): it only uses a
``random.Random(seed)`` and the game's own Flight with config.DT. No global
``random``, clock or ``hash()``.

Pure logic: no Session, pygame or drawing.
"""

from datetime import datetime, timedelta, timezone

from . import config

# Fixed offset, not zoneinfo: Windows without tzdata has no "Asia/Taipei",
# and Taiwan has no daylight saving time.
DAILY_TIMEZONE = timezone(timedelta(hours=config.DAILY_UTC_OFFSET_HOURS))


def daily_today(now=None):
    """Today's date in the daily-challenge time zone (UTC+8).

    ``now`` is an aware datetime (for tests); default is the current time.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    return now.astimezone(DAILY_TIMEZONE).date()


def daily_seed(day):
    """Seed of ``day``'s map: YYYYMMDD * 100 + DAILY_GENERATOR_VERSION."""
    return (day.year * 10000 + day.month * 100 + day.day) * 100 + config.DAILY_GENERATOR_VERSION
