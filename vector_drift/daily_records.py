"""Daily challenge records: what the player did on each day's map.

``session.daily_records`` maps a day ("2026-11-19") to one record (a plain
dict, so it saves as JSON in the profile's stats unchanged):

* ``cleared``                -- the day's map was cleared
* ``first_clear_lives_used`` -- lives lost in the run of the first clear (None: not cleared)
* ``coins``                  -- coins paid by that day's map pickups (not the clear reward)
* ``best_time``              -- fastest total flight time of a clear (None: not cleared)
* ``answer_used``            -- the reference answer was shown (always False for now)
* ``coins_taken``            -- [x, y] of the coins already paid that day
* ``clear_rewarded``         -- the day's clear reward was paid

Pure data helpers: no pygame, no scenes.
"""

import math
from datetime import date


def new_record():
    """A day nothing has happened on yet."""
    return {
        "cleared": False,
        "first_clear_lives_used": None,
        "coins": 0,
        "best_time": None,
        "answer_used": False,
        "coins_taken": [],
        "clear_rewarded": False,
    }


def day_key(day):
    """The record key of ``day`` (a datetime.date): its ISO date."""
    return day.isoformat()


def get_record(session, day, create=False):
    """``day``'s record on ``session``; with ``create`` a new one is added if missing."""
    records = session.daily_records
    key = day_key(day)
    if key not in records and create:
        records[key] = new_record()
    return records.get(key)


def _is_day_key(key):
    if not isinstance(key, str):
        return False
    try:
        return date.fromisoformat(key).isoformat() == key
    except ValueError:
        return False


def _count(value):
    """A non-negative int, else None (a bool is not a count)."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _time(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) and value >= 0 else None


def _point(value):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in value):
        return None
    x, y = float(value[0]), float(value[1])
    return [x, y] if math.isfinite(x) and math.isfinite(y) else None


def _clean_record(raw):
    record = new_record()
    record["cleared"] = raw.get("cleared") is True
    record["first_clear_lives_used"] = _count(raw.get("first_clear_lives_used"))
    record["coins"] = _count(raw.get("coins")) or 0
    record["best_time"] = _time(raw.get("best_time"))
    record["answer_used"] = raw.get("answer_used") is True
    taken = raw.get("coins_taken")
    points = (_point(p) for p in (taken if isinstance(taken, (list, tuple)) else ()))
    record["coins_taken"] = [p for p in points if p is not None]
    record["clear_rewarded"] = raw.get("clear_rewarded") is True
    return record


def records_from_saved(raw):
    """Saved daily records as the Session holds them.

    Anything that is not a dict gives no records; an entry whose key is not
    an ISO day or whose value is not a dict is dropped, and each field of a
    kept record falls back to its default when broken.
    """
    if not isinstance(raw, dict):
        return {}
    return {key: _clean_record(value) for key, value in raw.items()
            if _is_day_key(key) and isinstance(value, dict)}


def records_to_saved(records):
    """A copy of ``records`` for the profile (no shared lists with the Session)."""
    return records_from_saved(records)


# --- coins and the clear reward ----------------------------------------------------

def taken_coins(session, day):
    """Centers (x, y) of the coins already paid on ``day``."""
    record = get_record(session, day)
    return {tuple(point) for point in record["coins_taken"]} if record else set()


def take_coin(session, day, center):
    """Mark the coin at ``center`` paid on ``day``; False if it was paid before."""
    point = [float(center[0]), float(center[1])]
    record = get_record(session, day, create=True)
    if point in record["coins_taken"]:
        return False
    record["coins_taken"].append(point)
    return True


def take_clear_reward(session, day):
    """Mark ``day``'s clear reward paid; False if it was paid before."""
    record = get_record(session, day, create=True)
    if record["clear_rewarded"]:
        return False
    record["clear_rewarded"] = True
    return True


# --- results ----------------------------------------------------------------------------

def add_coins(session, day, amount):
    """Count ``amount`` coins paid by ``day``'s map pickups."""
    get_record(session, day, create=True)["coins"] += int(amount)


def record_clear(session, day, lives_used, total_time):
    """``day``'s map was cleared: lives lost in that run, total flight time (s)."""
    record = get_record(session, day, create=True)
    record["cleared"] = True
    if record["first_clear_lives_used"] is None:
        record["first_clear_lives_used"] = int(lives_used)
    if record["best_time"] is None or total_time < record["best_time"]:
        record["best_time"] = float(total_time)
    return record


def record_fail(session, day):
    """A run on ``day``'s map ended without a clear: the day gets a record, nothing more."""
    return get_record(session, day, create=True)
