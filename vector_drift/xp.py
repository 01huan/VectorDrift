"""Experience points and player levels: pure formulas.

Only numbers in, numbers out -- nothing here touches the Session, pygame or
the saves. The values live in config.py (XP_* and LEVEL_* constants).
"""


def xp_for_clear(base: int, k: int) -> int:
    """XP for the ``k``-th clear (k >= 1) of a source worth ``base`` the first time.

    Integer division on purpose: round() rounds halves to even, so the
    direction would change from one value to the next.
    """
    if k < 1:
        raise ValueError(f"clear count must be at least 1, got {k}")
    return max(1, base // k)
