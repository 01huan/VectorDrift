"""Experience points and player levels: constants and the pure formulas."""

from vector_drift import achievements, config


def test_every_campaign_level_has_a_first_clear_xp():
    # A new fixed level added without an XP value fails here.
    missing = [lid for lid in achievements.campaign_level_ids()
               if lid not in config.XP_FIXED_LEVEL_BASE]
    assert missing == []


def test_xp_constants():
    assert config.XP_RANDOM_MAP == 150
    assert config.XP_ACHIEVEMENT_TIERS == (10, 20, 30, 40)
    assert config.XP_ACHIEVEMENT_SINGLE == 40
    assert not hasattr(config, "XP_PER_ACHIEVEMENT")
    assert config.XP_LEVEL_FIRST == 100
    assert config.XP_LEVEL_STEP == 50
    assert config.LEVEL_UP_COINS == 5
    assert config.LEVEL_MILESTONE_EVERY == 5
    assert config.LEVEL_MILESTONE_COINS == 10


def test_daily_xp_constants():
    assert config.XP_DAILY == 300
    assert config.XP_DAILY_STREAK_STEP == 30
    assert config.XP_DAILY_STREAK_CAP == 5


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


# --- level-up coins -------------------------------------------------------------
def test_coins_for_levels():
    from vector_drift.xp import coins_for_levels
    assert coins_for_levels(1, 9) == 50       # 8 levels x 5, plus 10 at Lv 5
    assert coins_for_levels(1, 10) == 65
    assert coins_for_levels(4, 5) == 15


def test_coins_for_levels_pays_nothing_without_a_new_level():
    from vector_drift.xp import coins_for_levels
    assert coins_for_levels(5, 5) == 0
    assert coins_for_levels(6, 3) == 0


def test_coins_for_levels_never_pays_for_level_one():
    from vector_drift.xp import coins_for_levels
    assert coins_for_levels(0, 2) == 5


# --- achievements -----------------------------------------------------------------
def test_a_single_achievement_is_worth_40_hidden_or_not():
    from vector_drift.xp import xp_for_achievement_key
    assert xp_for_achievement_key("is_anyone_out_there") == 40
    assert xp_for_achievement_key("houston") == 40              # hidden


def test_each_tier_is_worth_its_own_xp():
    from vector_drift.xp import xp_for_achievement_key
    assert [xp_for_achievement_key(f"bounce_house.{t}") for t in (1, 2, 3, 4)] == [10, 20, 30, 40]
    assert xp_for_achievement_key("lost_in_space.1") == 10      # hidden tiered


def test_unknown_keys_are_worth_nothing():
    from vector_drift.xp import xp_for_achievement_key
    assert xp_for_achievement_key("we_have_liftoff") == 0       # a deleted achievement
    assert xp_for_achievement_key("bounce_house") == 0          # the old untiered form
    assert xp_for_achievement_key("bounce_house.5") == 0
    assert xp_for_achievement_key("is_anyone_out_there.1") == 0


# --- daily challenge ---------------------------------------------------------------
def test_daily_first_clear_grows_with_the_streak_up_to_the_cap():
    from vector_drift.xp import daily_clear_xp
    assert [daily_clear_xp(1, s) for s in range(1, 7)] == [300, 330, 360, 390, 420, 420]
    assert daily_clear_xp(1, 3) == 360
    assert daily_clear_xp(1, 12) == 420


def test_daily_later_clears_decay_without_the_streak():
    from vector_drift.xp import daily_clear_xp
    assert daily_clear_xp(2, 5) == 150
    assert daily_clear_xp(3, 1) == 100
    assert daily_clear_xp(4, 9) == 75
    assert daily_clear_xp(400, 1) == 1


def test_daily_streak_below_one_counts_as_one():
    from vector_drift.xp import daily_clear_xp
    assert daily_clear_xp(1, 0) == 300
    assert daily_clear_xp(1, -3) == 300


def test_daily_clear_xp_rejects_k_below_one():
    import pytest
    from vector_drift.xp import daily_clear_xp
    for k in (0, -1):
        with pytest.raises(ValueError):
            daily_clear_xp(k, 3)
