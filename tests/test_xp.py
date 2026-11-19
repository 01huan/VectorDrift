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
