"""Daily challenge records: one per day on the Session, saved with the profile."""

import json
from datetime import date

from vector_drift.account.integration import (_apply_profile_stats, apply_profile_to_session,
                                              profiles_equal, reset_session_to_guest,
                                              session_to_profile)
from vector_drift.account.models import PlayerProfile
from vector_drift.daily_records import day_key, get_record, new_record, records_from_saved
from vector_drift.scenes.base import Session

DAY = date(2026, 11, 19)


def _through_json(profile):
    """The profile as it comes back from the save file or the cloud."""
    return PlayerProfile.from_row(json.loads(json.dumps(profile.to_row())), profile.user_id)


def _session_with_records():
    session = Session()
    record = get_record(session, DAY, create=True)
    record.update(cleared=True, first_clear_lives_used=2, coins=1, best_time=7.25,
                  coins_taken=[[-3.125, 4.5]], clear_rewarded=True)
    get_record(session, date(2026, 11, 20), create=True)["coins"] = 0
    return session


def test_a_new_record_has_every_field():
    assert new_record() == {
        "cleared": False, "first_clear_lives_used": None, "coins": 0, "best_time": None,
        "answer_used": False, "coins_taken": [], "clear_rewarded": False,
    }


def test_records_are_keyed_by_the_iso_day():
    session = Session()
    assert day_key(DAY) == "2026-11-19"
    assert get_record(session, DAY) is None
    record = get_record(session, DAY, create=True)
    assert session.daily_records == {"2026-11-19": record}
    assert get_record(session, DAY) is record


def test_sessions_do_not_share_daily_records():
    a, b = Session(), Session()
    get_record(a, DAY, create=True)
    assert b.daily_records == {}


def test_daily_records_survive_a_save_and_load():
    saved = _session_with_records()
    loaded = Session()
    apply_profile_to_session(loaded, _through_json(session_to_profile(saved, "u")), "u")

    assert loaded.daily_records == saved.daily_records
    assert "daily_records" not in loaded.stats


def test_an_old_profile_without_daily_records_loads_empty():
    session = _session_with_records()
    _apply_profile_stats(session, {"clear_rewarded_levels": [1]})
    assert session.daily_records == {}


def test_applying_a_profile_replaces_the_records():
    other = Session()
    get_record(other, date(2026, 1, 1), create=True)["coins"] = 2
    session = _session_with_records()
    apply_profile_to_session(session, _through_json(session_to_profile(other, "u")), "u")
    assert session.daily_records == other.daily_records


def test_an_empty_record_list_equals_an_old_profile():
    new = session_to_profile(Session(), "u")
    old = session_to_profile(Session(), "u")
    old.stats.pop("daily_records")

    assert new.stats["daily_records"] == {}
    assert profiles_equal(new, old)
    assert profiles_equal(_through_json(new), old)


def test_different_daily_records_are_a_difference():
    plain = session_to_profile(Session(), "u")
    played = session_to_profile(_session_with_records(), "u")
    assert not profiles_equal(plain, played)


def test_reset_to_guest_clears_the_records():
    session = _session_with_records()
    reset_session_to_guest(session)
    assert session.daily_records == {}


def test_broken_saved_records_are_cleaned():
    raw = {
        "2026-11-19": {"cleared": True, "first_clear_lives_used": 1, "coins": 2, "best_time": 5.5,
                       "answer_used": False, "coins_taken": [[1.5, 2.0], ["x", 1], [3, 4, 5]],
                       "clear_rewarded": True},
        "2026-11-20": {"cleared": "yes", "coins": -4, "best_time": float("nan"),
                       "first_clear_lives_used": True},
        "not a day": {"cleared": True},
        "2026-02-30": {"cleared": True},
        "2026-11-21": ["not", "a", "record"],
    }

    records = records_from_saved(raw)

    assert set(records) == {"2026-11-19", "2026-11-20"}
    assert records["2026-11-19"]["coins_taken"] == [[1.5, 2.0]]
    assert records["2026-11-20"] == new_record()
    assert records_from_saved(None) == {} and records_from_saved([1, 2]) == {}
