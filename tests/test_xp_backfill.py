"""Progress from before XP existed gets its XP (and level-up coins) when a save is loaded."""

from types import SimpleNamespace

import pytest

from vector_drift import config, progression
from vector_drift.account import integration
from vector_drift.account.models import PlayerProfile
from vector_drift.level_presets import RANDOM_LEVEL_ID
from vector_drift.scenes.base import SceneManager, Session

pytestmark = pytest.mark.usefixtures("pygame_display")

OLD_ACHIEVEMENTS = {"is_anyone_out_there": "2026-11-01T00:00:00+00:00",
                    "bounce_house.1": "2026-11-01T00:00:00+00:00",
                    "bounce_house.2": "2026-11-02T00:00:00+00:00"}


def _old_session():
    session = Session()
    session.records = {1: 12.5, 2: 9.0}
    session.achievements = dict(OLD_ACHIEVEMENTS)
    return session


def _numbers(session):
    return (session.xp_total, dict(session.fixed_clear_counts), set(session.xp_achievements),
            session.xp_rewarded_level, int(session.money))


def test_old_clears_and_achievements_get_their_xp_and_coins():
    session = _old_session()
    assert progression.backfill_xp(session)
    assert session.xp_total == 100 + 120 + 40 + 10 + 20 == 290
    assert session.xp_rewarded_level == 3
    assert int(session.money) == 10
    assert session.fixed_clear_counts == {1: 1, 2: 1}
    assert session.xp_achievements == set(OLD_ACHIEVEMENTS)


def test_a_deleted_achievement_gives_nothing():
    session = Session()
    session.achievements = {"we_have_liftoff": "2026-10-01T00:00:00+00:00"}
    assert not progression.backfill_xp(session)
    assert session.xp_total == 0 and session.xp_achievements == set()


def test_backfilling_again_changes_nothing():
    session = _old_session()
    progression.backfill_xp(session)
    before = _numbers(session)
    assert not progression.backfill_xp(session)
    assert _numbers(session) == before


def test_a_level_already_counted_gets_nothing_more():
    session = Session()
    session.records = {1: 12.5}
    session.fixed_clear_counts = {1: 2}
    session.xp_total = 150
    session.xp_rewarded_level = 2
    assert not progression.backfill_xp(session)
    assert session.xp_total == 150 and session.fixed_clear_counts == {1: 2}


def test_random_daily_and_custom_records_get_nothing():
    session = Session()
    session.records = {RANDOM_LEVEL_ID: 3.0, 1000: 4.0, -5: 2.0}
    assert not progression.backfill_xp(session)
    assert session.xp_total == 0 and session.fixed_clear_counts == {}


def test_record_keys_saved_as_text_still_count():
    session = Session()
    session.records = {"1": 12.5}
    progression.backfill_xp(session)
    assert session.fixed_clear_counts == {1: 1}
    assert session.xp_total == 100


def test_backfill_leaves_the_win_stats_alone():
    session = _old_session()
    session.stats = {"time": 1.0}
    progression.backfill_xp(session)
    assert session.stats == {"time": 1.0}


def _old_profile():
    return PlayerProfile.from_row(integration.session_to_profile(_old_session(), "u").to_row(), "u")


def _strip_xp(profile):
    for key in integration.XP_KEYS:
        profile.stats.pop(key, None)
    return profile


def test_applying_an_old_profile_backfills_it():
    session = Session()
    integration.apply_profile_to_session(session, _strip_xp(_old_profile()), "u")
    assert session.xp_total == 290 and int(session.money) == 10


def test_loading_an_old_guest_save_backfills_and_saves_it():
    integration.save_guest_profile(_old_session())          # an old save on disk (tmp)
    session = Session()
    assert integration.load_guest_profile_into_session(session)
    assert session.xp_total == 290

    again = Session()                                       # the next launch reads it saved
    from vector_drift.account.local_profile_manager import LocalProfileManager
    assert LocalProfileManager().load().stats[integration.XP_TOTAL_KEY] == 290
    integration.load_guest_profile_into_session(again)
    assert int(again.money) == 10                           # paid once, not twice


def _manager():
    audio = SimpleNamespace(play=lambda *a, **k: None, start_loop=lambda *a, **k: None,
                            stop_loop=lambda *a, **k: None, update=lambda *a, **k: None)
    manager = SceneManager(audio)
    manager.scene = SimpleNamespace(update=lambda dt: None, counts_for_progress=True)
    return manager


def test_the_regular_check_backfills_migrated_achievements_and_saves(monkeypatch):
    saved = []
    monkeypatch.setattr(integration, "save_progress",
                        lambda account, session: saved.append(session.xp_total))
    manager = _manager()
    # The first version's untiered key: check_state makes it tier I without
    # unlock(), so only the backfill can give its XP.
    manager.session.achievements = {"bounce_house": "2026-10-01T00:00:00+00:00"}
    manager.update(0.016)
    assert "bounce_house.1" in manager.session.achievements
    assert manager.session.xp_total == 10
    assert saved and saved[-1] == 10

    saved.clear()
    manager.update(2.0)                                     # nothing new: no save
    assert saved == []
