"""XP progress on the Session and in the saved profile."""

import json

from vector_drift.account.integration import (_apply_profile_stats, apply_profile_to_session,
                                              session_to_profile)
from vector_drift.account.models import PlayerProfile
from vector_drift.scenes.base import Session

XP_KEYS = ("xp_total", "fixed_clear_counts", "xp_achievements", "xp_rewarded_level")


def _session_with_xp():
    session = Session()
    session.xp_total = 345
    session.fixed_clear_counts = {1: 3, 9: 1}
    session.xp_achievements = {"kaboom", "hole_in_one"}
    session.xp_rewarded_level = 3
    return session


def _through_json(profile):
    """The profile as it comes back from the save file or the cloud."""
    return PlayerProfile.from_row(json.loads(json.dumps(profile.to_row())), profile.user_id)


def _assert_defaults(session):
    assert session.xp_total == 0
    assert session.fixed_clear_counts == {}
    assert session.xp_achievements == set()
    assert session.xp_rewarded_level == 1


def test_a_new_session_starts_without_xp():
    session = Session()
    assert session.xp_total == 0
    assert session.fixed_clear_counts == {}
    assert session.xp_achievements == set()
    assert session.xp_rewarded_level == 1


def test_sessions_do_not_share_xp_containers():
    a, b = Session(), Session()
    a.fixed_clear_counts[1] = 2
    a.xp_achievements.add("kaboom")
    assert b.fixed_clear_counts == {}
    assert b.xp_achievements == set()


# --- saved with the profile -----------------------------------------------------
def test_xp_progress_survives_a_save_and_load():
    profile = _through_json(session_to_profile(_session_with_xp(), "u"))
    loaded = Session()
    apply_profile_to_session(loaded, profile, "u")
    assert loaded.xp_total == 345
    assert loaded.fixed_clear_counts == {1: 3, 9: 1}
    assert all(type(key) is int for key in loaded.fixed_clear_counts)
    assert loaded.xp_achievements == {"kaboom", "hole_in_one"}
    assert loaded.xp_rewarded_level == 3


def test_xp_achievements_are_saved_as_a_sorted_list():
    stats = session_to_profile(_session_with_xp(), "u").stats
    assert stats["xp_achievements"] == ["hole_in_one", "kaboom"]


def test_the_xp_keys_do_not_stay_in_session_stats():
    loaded = Session()
    apply_profile_to_session(loaded, _through_json(session_to_profile(_session_with_xp(), "u")), "u")
    for key in XP_KEYS:
        assert key not in loaded.stats


def test_an_old_profile_without_xp_loads_the_defaults():
    session = _session_with_xp()
    _apply_profile_stats(session, {"clear_rewarded_levels": [1]})
    _assert_defaults(session)


def test_applying_a_profile_replaces_the_xp_progress():
    other = Session()
    other.xp_total = 40
    other.fixed_clear_counts = {2: 1}
    other.xp_achievements = {"bounce_house"}
    session = _session_with_xp()
    apply_profile_to_session(session, _through_json(session_to_profile(other, "u")), "u")
    assert session.xp_total == 40
    assert session.fixed_clear_counts == {2: 1}
    assert session.xp_achievements == {"bounce_house"}
    assert session.xp_rewarded_level == 1


def test_broken_xp_values_fall_back_to_the_defaults():
    session = _session_with_xp()
    _apply_profile_stats(session, {"xp_total": -5, "fixed_clear_counts": "oops",
                                   "xp_achievements": 7, "xp_rewarded_level": 0})
    _assert_defaults(session)
    session = _session_with_xp()
    _apply_profile_stats(session, {"xp_total": "12", "fixed_clear_counts": [1, 2],
                                   "xp_achievements": {"kaboom": 1}, "xp_rewarded_level": True})
    _assert_defaults(session)


def test_broken_xp_entries_are_dropped_one_by_one():
    session = Session()
    _apply_profile_stats(session, {
        "fixed_clear_counts": {"1": 2, "x": 3, "2": -1, "3": 0, "4": True, "5": "2", "6": 1},
        "xp_achievements": ["kaboom", 3, None, "hole_in_one"],
    })
    assert session.fixed_clear_counts == {1: 2, 6: 1}
    assert session.xp_achievements == {"kaboom", "hole_in_one"}
