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
