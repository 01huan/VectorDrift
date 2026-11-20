"""Experience points and player levels: pure formulas.

Only numbers in, numbers out -- nothing here touches the Session, pygame or
the saves. The values live in config.py (XP_* and LEVEL_* constants).
"""

from dataclasses import dataclass

from . import config


def xp_for_clear(base: int, k: int) -> int:
    """XP for the ``k``-th clear (k >= 1) of a source worth ``base`` the first time.

    Integer division on purpose: round() rounds halves to even, so the
    direction would change from one value to the next.
    """
    if k < 1:
        raise ValueError(f"clear count must be at least 1, got {k}")
    return max(1, base // k)


def daily_streak_bonus(streak: int) -> int:
    """Extra XP a day's first clear gets for a streak of ``streak`` days (today included)."""
    days = min(max(1, streak), config.XP_DAILY_STREAK_CAP)
    return config.XP_DAILY_STREAK_STEP * (days - 1)


def daily_clear_xp(k: int, streak: int) -> int:
    """XP for the ``k``-th clear (k >= 1) of one day's daily map.

    The first clear gets XP_DAILY plus the streak bonus (``streak``: days
    cleared in a row with that day included; below 1 counts as 1). Later
    clears that day decay like any other source and get no bonus.
    """
    if k < 1:
        raise ValueError(f"clear count must be at least 1, got {k}")
    if k == 1:
        return config.XP_DAILY + daily_streak_bonus(streak)
    return xp_for_clear(config.XP_DAILY, k)


@dataclass(frozen=True)
class LevelProgress:
    """Where a total XP puts the player."""
    level: int      # current level (starts at 1)
    into: int       # XP gathered inside this level
    needed: int     # XP this level needs to reach the next one


def xp_to_next(level: int) -> int:
    """XP needed to go from ``level`` to ``level + 1``."""
    if level < 1:
        raise ValueError(f"level must be at least 1, got {level}")
    return config.XP_LEVEL_FIRST + config.XP_LEVEL_STEP * (level - 1)


def level_progress(total_xp: int) -> LevelProgress:
    """The level reached with ``total_xp`` and the progress inside it."""
    if total_xp < 0:
        raise ValueError(f"total XP cannot be negative, got {total_xp}")
    level, into = 1, total_xp
    while into >= xp_to_next(level):
        into -= xp_to_next(level)
        level += 1
    return LevelProgress(level, into, xp_to_next(level))


def coins_for_levels(from_level: int, to_level: int) -> int:
    """Coins for reaching every level after ``from_level`` up to ``to_level``.

    Each level from 2 up pays LEVEL_UP_COINS, and every multiple of
    LEVEL_MILESTONE_EVERY pays LEVEL_MILESTONE_COINS on top. Nothing when
    ``to_level <= from_level``.
    """
    coins = 0
    for level in range(max(from_level, 1) + 1, to_level + 1):
        coins += config.LEVEL_UP_COINS
        if level % config.LEVEL_MILESTONE_EVERY == 0:
            coins += config.LEVEL_MILESTONE_COINS
    return coins


def xp_for_achievement_key(key) -> int:
    """XP for one achievement unlock key: a single id or "<id>.<tier>".

    A key achievements.split_key does not know (a deleted achievement, the
    untiered form from before the tiers) is worth nothing.
    """
    from .achievements import split_key
    achievement, tier = split_key(key)
    if achievement is None:
        return 0
    if tier:
        return config.XP_ACHIEVEMENT_TIERS[tier - 1]
    return config.XP_ACHIEVEMENT_SINGLE
