"""XP progress on the Session and in the saved profile."""

import json

from vector_drift.account.integration import (_apply_profile_stats, apply_profile_to_session,
                                              profiles_equal, reset_session_to_guest,
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


# --- local / cloud compare and "Delete local data" -------------------------------
def test_an_old_profile_without_xp_matches_a_new_one_with_default_xp():
    new = session_to_profile(Session(), "u")
    old = session_to_profile(Session(), "u")
    for key in XP_KEYS:
        old.stats.pop(key)
    assert profiles_equal(new, old)
    assert profiles_equal(old, new)


def test_the_same_xp_matches_after_a_trip_through_json():
    profile = session_to_profile(_session_with_xp(), "u")
    assert profiles_equal(profile, _through_json(profile))


def test_profiles_differ_when_the_xp_differs():
    a = Session()
    a.xp_total = 40
    a.xp_achievements = {"kaboom"}
    assert not profiles_equal(session_to_profile(a, "u"), session_to_profile(Session(), "u"))
    b = Session()
    b.fixed_clear_counts = {1: 1}
    assert not profiles_equal(session_to_profile(b, "u"), session_to_profile(Session(), "u"))


def test_reset_session_to_guest_clears_the_xp():
    session = _session_with_xp()
    reset_session_to_guest(session)
    _assert_defaults(session)


# --- task 18: cleared random maps in the profile -----------------------------------
def _random_profile(maps=None, records=None, drop_key=False):
    session = Session()
    if maps is not None:
        session.random_maps_cleared = maps
    session.records = dict(records or {})
    profile = session_to_profile(session, "u")
    if drop_key:
        profile.stats.pop("random_maps_cleared")
    return profile


def test_cleared_random_maps_survive_a_save_and_load():
    profile = _through_json(_random_profile(maps=7))
    assert profile.stats["random_maps_cleared"] == 7
    loaded = Session()
    apply_profile_to_session(loaded, profile, "u")
    assert loaded.random_maps_cleared == 7
    assert "random_maps_cleared" not in loaded.stats


def test_applying_a_profile_replaces_the_cleared_random_maps():
    session = Session()
    session.random_maps_cleared = 9
    apply_profile_to_session(session, _through_json(_random_profile(maps=2)), "u")
    assert session.random_maps_cleared == 2


def test_an_old_profile_with_a_random_record_counts_one_map():
    from vector_drift.level_presets import RANDOM_LEVEL_ID
    profile = _through_json(_random_profile(records={RANDOM_LEVEL_ID: 3.5}, drop_key=True))
    session = Session()
    session.random_maps_cleared = 9
    apply_profile_to_session(session, profile, "u")
    assert session.random_maps_cleared == 1


def test_an_old_profile_without_a_random_record_counts_none():
    profile = _through_json(_random_profile(records={1: 3.5}, drop_key=True))
    session = Session()
    session.random_maps_cleared = 9
    apply_profile_to_session(session, profile, "u")
    assert session.random_maps_cleared == 0


def test_a_broken_random_map_count_loads_like_a_missing_one():
    from vector_drift.level_presets import RANDOM_LEVEL_ID
    for broken in (-1, "3", True, None, 2.0):
        for records, expected in (({RANDOM_LEVEL_ID: 3.5}, 1), ({1: 3.5}, 0)):
            session = Session()
            session.records = dict(records)
            _apply_profile_stats(session, {"random_maps_cleared": broken})
            assert session.random_maps_cleared == expected, (broken, records)


def test_an_old_profile_with_a_random_record_matches_a_new_one_with_one_map():
    from vector_drift.level_presets import RANDOM_LEVEL_ID
    old = _random_profile(records={RANDOM_LEVEL_ID: 3.5}, drop_key=True)
    new = _random_profile(maps=1, records={RANDOM_LEVEL_ID: 3.5})
    assert profiles_equal(old, new) and profiles_equal(new, old)
    assert profiles_equal(_random_profile(drop_key=True), _random_profile(maps=0))
    assert not profiles_equal(_random_profile(maps=2), _random_profile(maps=1))


def test_reset_session_to_guest_clears_the_random_map_count():
    session = Session()
    session.random_maps_cleared = 4
    reset_session_to_guest(session)
    assert session.random_maps_cleared == 0
