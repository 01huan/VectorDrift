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
