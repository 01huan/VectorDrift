"""Experience points and player levels: constants and the pure formulas."""

from vector_drift import achievements, config


def test_every_campaign_level_has_a_first_clear_xp():
    # A new fixed level added without an XP value fails here.
    missing = [lid for lid in achievements.campaign_level_ids()
               if lid not in config.XP_FIXED_LEVEL_BASE]
    assert missing == []


def test_xp_constants():
    assert config.XP_RANDOM_MAP == 150
    assert config.XP_PER_ACHIEVEMENT == 40
    assert config.XP_LEVEL_FIRST == 100
    assert config.XP_LEVEL_STEP == 50
    assert config.LEVEL_UP_COINS == 5
    assert config.LEVEL_MILESTONE_EVERY == 5
    assert config.LEVEL_MILESTONE_COINS == 10


# --- replay decay ---------------------------------------------------------------
def test_xp_for_clear_decays_with_integer_division():
    from vector_drift.xp import xp_for_clear
    assert [xp_for_clear(260, k) for k in range(1, 9)] == [260, 130, 86, 65, 52, 43, 37, 32]


def test_xp_for_clear_never_drops_to_zero():
    from vector_drift.xp import xp_for_clear
    assert xp_for_clear(100, 200) == 1


def test_xp_for_clear_rejects_k_below_one():
    import pytest
    from vector_drift.xp import xp_for_clear
    with pytest.raises(ValueError):
        xp_for_clear(100, 0)


# --- level thresholds -----------------------------------------------------------
def test_xp_to_next_grows_by_the_step():
    from vector_drift.xp import xp_to_next
    assert [xp_to_next(level) for level in (1, 2, 3, 9, 10)] == [100, 150, 200, 500, 550]


def test_xp_to_next_rejects_levels_below_one():
    import pytest
    from vector_drift.xp import xp_to_next
    with pytest.raises(ValueError):
        xp_to_next(0)


def test_level_progress_table():
    from vector_drift.xp import level_progress
    rows = {0: (1, 0, 100), 99: (1, 99, 100), 100: (2, 0, 150),
            2699: (9, 499, 500), 2700: (10, 0, 550)}
    for total, expected in rows.items():
        progress = level_progress(total)
        assert (progress.level, progress.into, progress.needed) == expected, total


def test_level_progress_rejects_negative_xp():
    import pytest
    from vector_drift.xp import level_progress
    with pytest.raises(ValueError):
        level_progress(-1)
