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


def test_random_and_custom_records_get_nothing():
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


# --- daily clears from before daily XP (task 36) -----------------------------------------------

def _daily_session():
    """Two cleared days, one played-not-cleared day and one already given XP."""
    from datetime import date
    from vector_drift.daily_records import get_record
    session = Session()
    for day in (date(2026, 11, 18), date(2026, 11, 19)):
        get_record(session, day, create=True).update(cleared=True, answer_used=day.day == 19)
    get_record(session, date(2026, 11, 17), create=True)                 # failed: no XP
    get_record(session, date(2026, 11, 20), create=True).update(cleared=True, xp_clears=2)
    return session


def test_old_daily_clears_get_xp_daily_once_each():
    session = _daily_session()
    assert progression.backfill_xp(session)
    assert session.xp_total == 2 * config.XP_DAILY == 600
    records = session.daily_records
    assert records["2026-11-18"]["xp_clears"] == 1 and records["2026-11-19"]["xp_clears"] == 1
    assert records["2026-11-17"]["xp_clears"] == 0
    assert records["2026-11-20"]["xp_clears"] == 2
    assert session.xp_rewarded_level == 4                   # 600 XP: Lv 4, its coins paid
    assert int(session.money) == 3 * config.LEVEL_UP_COINS


def test_backfilling_daily_clears_again_changes_nothing():
    session = _daily_session()
    progression.backfill_xp(session)
    before = (session.xp_total, int(session.money),
              {key: dict(record) for key, record in session.daily_records.items()})
    assert not progression.backfill_xp(session)
    assert (session.xp_total, int(session.money),
            {key: dict(record) for key, record in session.daily_records.items()}) == before


def test_daily_backfill_pops_no_level_up(monkeypatch):
    monkeypatch.setattr(integration, "save_progress", lambda account, session: None)
    manager = _manager()
    popped = []
    monkeypatch.setattr(manager.toasts, "push_level_up", lambda *a, **k: popped.append(a))
    manager.session.daily_records = _daily_session().daily_records
    manager.update(0.016)                                   # the regular check backfills
    assert manager.session.xp_total == 600
    assert manager.session.xp_rewarded_level == 4
    assert popped == []


def test_an_old_profile_with_daily_clears_backfills_on_load():
    profile = PlayerProfile.from_row(
        integration.session_to_profile(_daily_session(), "u").to_row(), "u")
    for key in integration.XP_KEYS:
        profile.stats.pop(key, None)
    raw = profile.stats.get(integration.DAILY_RECORDS_KEY) or {}
    for record in raw.values():
        record.pop("xp_clears", None)                       # a save from before the field
    session = Session()
    integration.apply_profile_to_session(session, profile, "u")
    assert session.xp_total == 3 * config.XP_DAILY          # 11/20 had no saved count either
