"""Experience and player levels applied to the Session.

Every place that gives XP goes through here; the formulas themselves are in
xp.py. Each reward remembers what it already paid (clear counts, achievement
keys, the highest level whose coins were paid), so running the same code again
pays nothing twice.
"""

from . import config, xp


def add_xp(session, amount: int) -> int:
    """Add ``amount`` XP to the session's total; returns it."""
    amount = max(0, int(amount))
    session.xp_total = int(getattr(session, "xp_total", 0) or 0) + amount
    return amount


def grant_clear_xp(session, base: int, count: int) -> int:
    """XP for clear number ``count`` (1 = the first) of a source worth ``base``.

    The caller keeps the count: fixed levels save theirs, random maps keep
    theirs for this launch only.
    """
    return add_xp(session, xp.xp_for_clear(base, count))


def fixed_level_clear_xp(session, level_id: int) -> int:
    """A fixed (campaign) level was cleared: count it and give its XP.

    A level missing from XP_FIXED_LEVEL_BASE gives nothing rather than break
    the clear (tests/test_xp.py makes sure every campaign level is listed).
    """
    base = config.XP_FIXED_LEVEL_BASE.get(level_id)
    if base is None:
        return 0
    counts = session.fixed_clear_counts
    count = int(counts.get(level_id, 0)) + 1
    counts[level_id] = count
    return grant_clear_xp(session, base, count)


def clear_xp(session, level_id: int, kind: str) -> int:
    """XP for clearing a level of ``kind`` (see GameScene._level_kind).

    Only campaign levels give XP here; the tutorial never gets this far, and
    custom, community and daily maps give none.
    """
    if kind == "campaign":
        return fixed_level_clear_xp(session, level_id)
    return 0
