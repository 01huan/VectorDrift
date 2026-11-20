"""Daily challenge records: one per day on the Session, saved with the profile."""

import json
from datetime import date

import pytest

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


# --- the reference answer ----------------------------------------------------------

def test_daily_answer_has_its_own_price():
    from vector_drift import config
    assert config.DAILY_ANSWER_COST == 10


def test_marking_the_answer_used_creates_a_missing_record():
    from vector_drift.daily_records import mark_answer_used
    session = Session()
    mark_answer_used(session, DAY)
    assert get_record(session, DAY) == dict(new_record(), answer_used=True)


def test_marking_the_answer_used_keeps_the_other_fields():
    from vector_drift.daily_records import mark_answer_used
    session = _session_with_records()
    before = dict(get_record(session, DAY))
    mark_answer_used(session, DAY)
    assert get_record(session, DAY) == dict(before, answer_used=True)
    assert get_record(session, date(2026, 11, 20))["answer_used"] is False


def test_a_used_answer_survives_a_save_and_load():
    from vector_drift.daily_records import mark_answer_used
    saved = _session_with_records()
    mark_answer_used(saved, DAY)
    loaded = Session()
    apply_profile_to_session(loaded, _through_json(session_to_profile(saved, "u")), "u")
    assert get_record(loaded, DAY)["answer_used"] is True
    assert loaded.daily_records == saved.daily_records


# --- streaks --------------------------------------------------------------------------


TODAY = date(2026, 11, 20)


def _records(cleared=(), answered=(), failed=()):
    """Records with the given November days cleared / cleared with the answer / failed."""
    session = Session()
    for d in cleared:
        get_record(session, date(2026, 11, d), create=True)["cleared"] = True
    for d in answered:
        get_record(session, date(2026, 11, d), create=True).update(cleared=True, answer_used=True)
    for d in failed:
        get_record(session, date(2026, 11, d), create=True)
    return session.daily_records


@pytest.mark.parametrize("records, current, longest", [
    (_records(), 0, 0),
    (_records(cleared=[20]), 1, 1),
    (_records(cleared=[18, 19]), 2, 2),                     # today not cleared yet
    (_records(cleared=[18, 19, 20]), 3, 3),
    (_records(cleared=[17, 19, 20]), 2, 2),                 # 11/18 missed
    (_records(cleared=[1, 2, 3, 4, 5, 19, 20]), 2, 5),
    (_records(cleared=[20], answered=[19]), 2, 2),          # the answer day still counts
    (_records(cleared=[20], failed=[19]), 1, 1),            # a fail breaks it
])
def test_streaks(records, current, longest):
    from vector_drift.daily_records import current_streak, longest_streak
    assert current_streak(records, TODAY) == current
    assert longest_streak(records) == longest


def test_a_streak_runs_across_months():
    from vector_drift.daily_records import current_streak, longest_streak
    session = Session()
    for day in (date(2026, 10, 30), date(2026, 10, 31), date(2026, 11, 1)):
        get_record(session, day, create=True)["cleared"] = True
    assert current_streak(session.daily_records, date(2026, 11, 2)) == 3
    assert longest_streak(session.daily_records) == 3


def test_a_streak_that_ended_before_yesterday_is_not_current():
    from vector_drift.daily_records import current_streak
    assert current_streak(_records(cleared=[17, 18]), TODAY) == 0
