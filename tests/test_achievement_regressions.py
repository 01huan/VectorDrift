"""Regressions of the achievement rules that the first version got wrong.

- A community level is not a campaign level: clearing one unlocks
  "Space Tourist" and does not count towards the campaign clean clears.
- A broken save (odd types in the progress lists) must not break the load.
- The achievements are progress like the rest: applying a copy replaces the
  session's, so they follow the player's choice (local or cloud).
"""

from types import SimpleNamespace

import pytest

from vector_drift import achievements as ach
from vector_drift import data
from vector_drift.account.integration import (_apply_profile_stats, apply_profile_to_session,
                                              profiles_equal, session_to_profile)
from vector_drift.scenes.base import SceneManager

pytestmark = pytest.mark.usefixtures("pygame_display")


def _manager():
    audio = SimpleNamespace(play=lambda *a, **k: None, start_loop=lambda *a, **k: None,
                             stop_loop=lambda *a, **k: None)
    return SceneManager(audio)


def _community_level(level_id=-98765):
    """A community level: it lives in the community registry, not in the
    player's own custom levels."""
    spec = data.LevelSpec(id=level_id, name="Community", start=(0.0, 0.0),
                           target_center=(5.0, 0.0), target_radius=1.0, ship_id="ship01")
    data.register_community_level(spec)
    return spec


# --- the kind of a level -------------------------------------------------------
def test_a_community_level_is_not_a_campaign_level():
    from vector_drift.scenes.game import GameScene

    spec = _community_level()
    manager = _manager()
    manager.session.level_id = spec.id
    manager.session.level_source = "community"
    scene = GameScene(manager)
    assert scene._level_kind() == "community"


def test_clearing_a_community_level_unlocks_space_tourist():
    from vector_drift.scenes.game import GameScene

    spec = _community_level()
    manager = _manager()
    manager.session.level_id = spec.id
    manager.session.level_source = "community"
    scene = GameScene(manager)
    scene._report_clear()
    assert ach.is_unlocked(manager.session, "space_tourist")
    # A community level is not a campaign level: it must not count towards
    # the campaign clean clears ("Look Ma, No Hints").
    assert ach.CLEAN_CLEARS not in manager.session.achievement_progress


def test_the_other_kinds_are_still_right():
    from vector_drift.scenes.game import GameScene

    manager = _manager()
    manager.session.level_id = 1
    assert GameScene(manager)._level_kind() == "campaign"

    custom = data.LevelSpec(id=4321, name="Mine", start=(0.0, 0.0), target_center=(5.0, 0.0),
                            target_radius=1.0, ship_id="ship01")
    data.register_custom_level(custom)
    manager = _manager()
    manager.session.level_id = custom.id
    manager.session.custom_level_ids.add(custom.id)
    manager.session.level_source = "level_editor"
    assert GameScene(manager)._level_kind() == "custom"


# --- broken saves --------------------------------------------------------------
def test_a_progress_list_with_mixed_types_does_not_crash():
    manager = _manager()
    manager.session.achievement_progress[ach.CLEAN_CLEARS] = [1, "2"]
    ach._add_to_list(manager.session, ach.CLEAN_CLEARS, 3)
    assert set(manager.session.achievement_progress[ach.CLEAN_CLEARS]) == {1, "2", 3}


def test_a_broken_saved_progress_does_not_break_the_load():
    manager = _manager()
    _apply_profile_stats(manager.session, {
        "achievements": {"kaboom": "2026-01-01T00:00:00+00:00"},
        "achievement_progress": {"out_of_bounds": 5, "clean_clears": [[1], 2],
                                 "abilities_used": "not-a-list"},
    })
    assert manager.session.achievements == {"kaboom": "2026-01-01T00:00:00+00:00"}
    assert manager.session.achievement_progress["out_of_bounds"] == 5
    assert 2 in manager.session.achievement_progress["clean_clears"]


# --- signing in ----------------------------------------------------------------
def test_the_chosen_copy_wins_so_no_unlock_is_merged_in():
    # The player picks local or cloud when the two differ; the achievements
    # follow that choice like every other progress field.
    local = _manager().session
    local.achievements = {"kaboom": "2026-01-01T00:00:00+00:00"}
    local_profile = session_to_profile(local, "u")

    cloud = _manager().session
    cloud.achievements = {"hole_in_one": "2026-02-02T00:00:00+00:00"}
    cloud_profile = session_to_profile(cloud, "u")

    session = _manager().session
    session.achievements = dict(local.achievements)
    apply_profile_to_session(session, local_profile, "u")
    assert set(session.achievements) == {"kaboom"}

    session = _manager().session
    session.achievements = dict(local.achievements)
    apply_profile_to_session(session, cloud_profile, "u")
    assert set(session.achievements) == {"hole_in_one"}


def test_a_profile_without_the_achievements_leaves_the_session_alone():
    session = _manager().session
    session.achievements = {"kaboom": "t"}
    _apply_profile_stats(session, {})
    assert session.achievements == {"kaboom": "t"}


def test_the_local_and_the_cloud_differ_when_the_unlocks_differ():
    a, b = _manager().session, _manager().session
    a.achievements = {"kaboom": "t"}
    b.achievements = {"hole_in_one": "t"}
    assert not profiles_equal(session_to_profile(a, "u"), session_to_profile(b, "u"))


def test_an_old_profile_without_achievements_is_not_a_difference():
    a = _manager().session
    a.achievements = {}
    old = session_to_profile(_manager().session, "u")
    old.stats.pop("achievements", None)
    old.stats.pop("achievement_progress", None)
    assert profiles_equal(session_to_profile(a, "u"), old)


# --- the login conflict --------------------------------------------------------
def _login_scene():
    from vector_drift.scenes.auth import LoginScene

    manager = _manager()
    manager.scene = LoginScene(manager)
    return manager


def _profile_with(unlocks):
    session = _manager().session
    session.achievements = dict(unlocks)
    return session_to_profile(session, "u")


@pytest.mark.parametrize("prefer_local, expected", [
    (True, {"kaboom"}),
    (False, {"hole_in_one"}),
])
def test_the_conflict_choice_decides_the_achievements(prefer_local, expected):
    # "Use Local" / "Use Cloud": the achievements go with the chosen copy.
    from vector_drift.scenes.auth import LoginScene

    manager = _login_scene()
    scene = manager.scene
    scene._conflict = {
        "local": _profile_with({"kaboom": "t"}),
        "cloud": _profile_with({"hole_in_one": "t"}),
        "user_id": "u",
        "email": None,
    }
    scene._resolve_conflict(prefer_local)
    assert set(manager.session.achievements) == expected
