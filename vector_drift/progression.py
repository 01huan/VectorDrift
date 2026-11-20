"""Experience and player levels applied to the Session.

Every place that gives XP goes through here; the formulas themselves are in
xp.py. Each reward remembers what it already paid (clear counts, achievement
keys, the highest level whose coins were paid), so running the same code again
pays nothing twice.
"""

from dataclasses import dataclass

from . import config, xp


@dataclass(frozen=True)
class LevelUp:
    """Levels reached at once and the coins they paid."""
    from_level: int     # the highest level paid before
    to_level: int       # the level reached now
    coins: int          # coins paid for every level in between

    def as_stats(self):
        """The form the win stats keep (session.stats["level_up"])."""
        return {"from": self.from_level, "to": self.to_level, "coins": self.coins}


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


def random_map_clear_xp(session, level_id: int, seed) -> int:
    """A random map was cleared: count it for this launch and give its XP.

    The count is not saved (like clear_rewarded_maps): after a restart the
    same map counts from 1 again.
    """
    counts = session.random_map_clears
    key = (level_id, seed)
    counts[key] = int(counts.get(key, 0)) + 1
    return grant_clear_xp(session, config.XP_RANDOM_MAP, counts[key])


def clear_xp(session, level_id: int, kind: str, seed=None) -> int:
    """XP for clearing a level of ``kind`` (see GameScene._level_kind).

    Campaign levels and random maps give XP here; the tutorial never gets this
    far, and custom, community and daily maps give none.
    """
    if kind == "campaign":
        return fixed_level_clear_xp(session, level_id)
    if kind == "random":
        return random_map_clear_xp(session, level_id, seed)
    return 0


def pay_level_ups(session):
    """Pay the coins of every level reached but not paid yet.

    Returns a LevelUp, or None when the current level was already paid.
    Safe to call any number of times: xp_rewarded_level remembers the payout.
    """
    level = xp.level_progress(int(getattr(session, "xp_total", 0) or 0)).level
    paid = int(getattr(session, "xp_rewarded_level", 1) or 1)
    if level <= paid:
        return None
    coins = xp.coins_for_levels(paid, level)
    session.money.add(coins)
    session.xp_rewarded_level = level
    return LevelUp(paid, level, coins)


def achievement_xp(session, key) -> int:
    """Give an unlock key's XP the first time; nothing for a key already paid."""
    paid = session.xp_achievements
    if key in paid:
        return 0
    amount = xp.xp_for_achievement_key(key)
    if amount <= 0:
        return 0
    paid.add(key)
    return add_xp(session, amount)


def _fixed_level_id(key):
    """A records key (an int, or digits saved as text) as a level id, else None."""
    if isinstance(key, bool):
        return None
    if isinstance(key, int):
        return key
    text = str(key)
    return int(text) if text.lstrip("-").isdigit() else None


def backfill_xp(session) -> bool:
    """Give the XP that progress from before XP existed has earned. True if any was given.

    A fixed level with a best time but no counted clear counts one clear and
    gives its first-clear XP; every known unlock key not paid yet gives its XP;
    then the coins of every level reached are paid. Random maps are not
    backfilled (nobody knows how many there were). Nothing here pops up or
    touches the win stats, and running it again gives nothing more.
    """
    from .achievements import campaign_level_ids
    campaign = set(campaign_level_ids())
    before = int(getattr(session, "xp_total", 0) or 0)
    counts = session.fixed_clear_counts
    for key in list((getattr(session, "records", None) or {}).keys()):
        level_id = _fixed_level_id(key)
        base = config.XP_FIXED_LEVEL_BASE.get(level_id)
        if level_id not in campaign or base is None or counts.get(level_id, 0) > 0:
            continue
        counts[level_id] = 1
        add_xp(session, base)
    for key in list((getattr(session, "achievements", None) or {}).keys()):
        achievement_xp(session, key)
    paid = pay_level_ups(session) is not None
    return paid or session.xp_total != before
