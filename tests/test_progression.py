"""Where XP comes from and what it pays: clears, level-up coins (progression.py)."""

from types import SimpleNamespace

import pytest

from vector_drift import config, progression
from vector_drift.physics import Outcome
from vector_drift.scenes import game as game_module
from vector_drift.scenes.base import SceneManager, Session
from vector_drift.scenes.fail import FailScene
from vector_drift.scenes.game import GameScene
from vector_drift.scenes.win import WinScene
from vector_drift.hints import get_hint

pytestmark = pytest.mark.usefixtures("pygame_display")


@pytest.fixture(autouse=True)
def no_solver(monkeypatch):
    monkeypatch.setattr(game_module, "run_solver_async", lambda *a, **k: SimpleNamespace(
        running=True, cancel=lambda: None, stop=lambda *a: True, error=None, result=None))


@pytest.fixture
def no_achievements(monkeypatch):
    """Only the clear's own XP: achievements still unlock but give no XP here."""
    monkeypatch.setattr(progression, "achievement_xp", lambda session, key: 0)


def _manager():
    audio = SimpleNamespace(play=lambda *a, **k: None, start_loop=lambda *a, **k: None,
                            stop_loop=lambda *a, **k: None)
    return SceneManager(audio)


def _scene(level_id, manager=None, seed=None):
    manager = manager or _manager()
    manager.session.level_id = level_id
    manager.session.random_seed = seed
    scene = GameScene(manager)
    manager.switch(scene)
    return scene


def _run_to_win_screen(scene):
    for _ in range(60 * 20):
        if not isinstance(scene.manager.scene, GameScene):
            break
        scene.update(1 / 60)
    assert isinstance(scene.manager.scene, WinScene)
    return scene.manager.session.stats


def _win(scene):
    """Fly the level's first stored answer to the Win screen; return its stats."""
    answer = get_hint(scene.level.id).answers[0]
    scene.editor.set_lines([answer.fx, answer.fy])
    scene._on_text_change(scene.editor)
    scene._try_launch()
    return _run_to_win_screen(scene)


def _reach(scene):
    """End one flight on the current screen's target."""
    scene.flight = SimpleNamespace(time=1.0, trail=[], x=0.0, y=0.0)
    scene._end_flight(Outcome.REACHED)


def _pan(scene):
    for _ in range(60 * 3):
        if scene.pan is None:
            break
        scene.update(1 / 60)


def _arrive(scene):
    """Reach every checkpoint, then the final target; return the Win screen's stats."""
    while not scene.on_last_section:
        _reach(scene)
        _pan(scene)
    _reach(scene)
    return _run_to_win_screen(scene)


def _lose(scene):
    scene.editor.set_lines(["0", "0"])
    scene._on_text_change(scene.editor)
    for _ in range(scene.level.lives):
        scene._try_launch()
        scene.flight.abort()
        scene._end_flight(Outcome.ABORTED)
    assert isinstance(scene.manager.scene, FailScene)


# --- task 8: fixed level clears ---------------------------------------------------------
def test_fixed_level_clear_xp_decays_with_each_clear():
    session = Session()
    assert [progression.fixed_level_clear_xp(session, 1) for _ in range(3)] == [100, 50, 33]
    assert session.fixed_clear_counts == {1: 3}
    assert session.xp_total == 183


def test_a_fixed_level_without_an_xp_entry_gives_nothing():
    session = Session()
    assert progression.fixed_level_clear_xp(session, 91) == 0
    assert session.xp_total == 0 and session.fixed_clear_counts == {}


def test_clear_xp_takes_the_count_from_the_caller():
    session = Session()
    assert progression.grant_clear_xp(session, 260, 4) == 65
    assert session.xp_total == 65


@pytest.mark.usefixtures("no_achievements")
def test_three_clears_of_level_one_give_100_50_33():
    manager = _manager()
    gained = []
    for _ in range(3):
        gained.append(_win(_scene(1, manager))["xp_gained"])
    assert gained == [100, 50, 33]
    assert manager.session.xp_total == 183
    assert manager.session.fixed_clear_counts[1] == 3


@pytest.mark.usefixtures("no_achievements")
def test_a_clear_after_seeing_the_answer_still_gives_xp():
    manager = _manager()
    scene = _scene(3, manager)
    scene._reveal_solution()
    assert _win(scene)["xp_gained"] == config.XP_FIXED_LEVEL_BASE[3]
    assert manager.session.xp_total == config.XP_FIXED_LEVEL_BASE[3]


@pytest.mark.usefixtures("no_achievements")
def test_losing_a_level_gives_no_xp():
    manager = _manager()
    _lose(_scene(1, manager))
    assert manager.session.xp_total == 0
    assert manager.session.fixed_clear_counts == {}


@pytest.mark.usefixtures("no_achievements")
@pytest.mark.parametrize("level_id", [9, 10])
def test_a_checkpoint_is_not_a_clear(level_id):
    manager = _manager()
    scene = _scene(level_id, manager)
    _reach(scene)                                   # the checkpoint
    _pan(scene)
    assert manager.session.xp_total == 0
    assert manager.session.fixed_clear_counts == {}
    _reach(scene)                                   # the final target
    assert _run_to_win_screen(scene)["xp_gained"] == config.XP_FIXED_LEVEL_BASE[level_id]
    assert manager.session.fixed_clear_counts == {level_id: 1}


@pytest.mark.usefixtures("no_achievements")
def test_clear_xp_is_saved_with_the_clear(monkeypatch):
    from vector_drift.account import integration
    saved = []
    monkeypatch.setattr(integration, "save_progress", lambda account, session: saved.append(
        (session.xp_total, dict(session.fixed_clear_counts))))
    _win(_scene(1))
    assert (100, {1: 1}) in saved


# --- task 9: level-up coins -------------------------------------------------------------
def _xp_at_level(level):
    """The total XP that just reaches ``level``."""
    from vector_drift.xp import xp_to_next
    return sum(xp_to_next(n) for n in range(1, level))


def test_reaching_level_five_pays_fifteen_coins_once():
    session = Session()
    session.xp_total, session.xp_rewarded_level = _xp_at_level(4), 4
    session.xp_total = _xp_at_level(5)
    level_up = progression.pay_level_ups(session)
    assert level_up == progression.LevelUp(4, 5, 15)
    assert int(session.money) == 15
    assert session.xp_rewarded_level == 5

    assert progression.pay_level_ups(session) is None       # nothing new: nothing paid
    assert int(session.money) == 15


def test_jumping_from_level_one_to_nine_pays_every_level_between():
    session = Session()
    session.xp_total = _xp_at_level(9)
    assert progression.pay_level_ups(session) == progression.LevelUp(1, 9, 50)
    assert int(session.money) == 50
    assert session.xp_rewarded_level == 9


def test_no_level_up_pays_nothing():
    session = Session()
    session.xp_total = 99
    assert progression.pay_level_ups(session) is None
    assert int(session.money) == 0 and session.xp_rewarded_level == 1


def test_level_up_reads_as_win_stats():
    assert progression.LevelUp(4, 5, 15).as_stats() == {"from": 4, "to": 5, "coins": 15}


@pytest.mark.usefixtures("no_achievements")
def test_a_clear_that_levels_up_pays_and_shows_it():
    manager = _manager()
    stats = _win(_scene(1, manager))                    # 100 XP: Lv 1 -> Lv 2
    assert stats["level_up"] == {"from": 1, "to": 2, "coins": 5}
    assert int(manager.session.money) == config.CLEAR_REWARD + 5
    assert manager.session.xp_rewarded_level == 2

    stats = _win(_scene(1, manager))                    # 150 XP: still Lv 2
    assert "level_up" not in stats
    assert int(manager.session.money) == config.CLEAR_REWARD + 5


# --- task 10: random map clears ---------------------------------------------------------
def test_random_map_clear_xp_decays_per_map():
    from vector_drift.level_presets import RANDOM_LEVEL_ID
    session = Session()
    assert progression.random_map_clear_xp(session, RANDOM_LEVEL_ID, 123) == 150
    assert progression.random_map_clear_xp(session, RANDOM_LEVEL_ID, 123) == 75
    assert progression.random_map_clear_xp(session, RANDOM_LEVEL_ID, 456) == 150
    assert session.random_map_clears == {(RANDOM_LEVEL_ID, 123): 2, (RANDOM_LEVEL_ID, 456): 1}


@pytest.mark.usefixtures("no_achievements")
def test_random_map_clears_give_150_75_then_150_on_a_new_seed():
    from vector_drift.level_presets import RANDOM_LEVEL_ID
    manager = _manager()
    gained = [_arrive(_scene(RANDOM_LEVEL_ID, manager, seed=seed))["xp_gained"]
              for seed in (123, 123, 456)]
    assert gained == [150, 75, 150]
    assert manager.session.xp_total == 375
    assert manager.session.fixed_clear_counts == {}


@pytest.mark.usefixtures("no_achievements")
def test_random_map_clears_level_up_too():
    from vector_drift.level_presets import RANDOM_LEVEL_ID
    manager = _manager()
    stats = _arrive(_scene(RANDOM_LEVEL_ID, manager, seed=123))
    assert stats["level_up"] == {"from": 1, "to": 2, "coins": 5}


def test_random_map_clear_counts_are_not_saved():
    from vector_drift.account.integration import apply_profile_to_session, session_to_profile
    from vector_drift.account.models import PlayerProfile
    from vector_drift.level_presets import RANDOM_LEVEL_ID
    session = Session()
    progression.random_map_clear_xp(session, RANDOM_LEVEL_ID, 123)
    row = session_to_profile(session, "u1").to_row()
    assert "random_map_clears" not in row["stats"]
    loaded = Session()
    apply_profile_to_session(loaded, PlayerProfile.from_row(row, "u1"), "u1")
    assert loaded.random_map_clears == {}
    assert progression.random_map_clear_xp(loaded, RANDOM_LEVEL_ID, 123) == 150


# --- task 11: no XP for the tutorial, custom, community and daily maps --------------------
# These check the clear itself. A clear on such a map can still unlock an
# achievement, which gives its own XP (task 12), so achievements give none here.
def _no_clear_xp(manager):
    session = manager.session
    assert session.xp_total == 0
    assert session.fixed_clear_counts == {}
    assert session.random_map_clears == {}
    assert session.xp_rewarded_level == 1


def _plain_level(level_id):
    from vector_drift import data
    return data.LevelSpec(id=level_id, name="Plain", start=(-7.0, 0.0),
                          target_center=(7.0, 0.0), target_radius=1.0, ship_id="ship01")


@pytest.mark.usefixtures("no_achievements")
def test_a_custom_level_clear_gives_no_xp():
    from vector_drift import data
    manager = _manager()
    data.register_custom_level(_plain_level(1000))
    manager.session.custom_level_ids.add(1000)
    manager.session.level_source = "custom"
    assert _arrive(_scene(1000, manager))["xp_gained"] == 0
    _no_clear_xp(manager)


@pytest.mark.usefixtures("no_achievements")
def test_a_community_level_clear_gives_no_xp():
    from vector_drift import data
    manager = _manager()
    level_id = data.community_level_id("row-for-xp")
    data.register_community_level(_plain_level(level_id))
    manager.session.level_source = "community"
    assert _arrive(_scene(level_id, manager))["xp_gained"] == 0
    _no_clear_xp(manager)


@pytest.mark.usefixtures("no_achievements")
def test_a_daily_clear_gives_no_xp(monkeypatch):
    from datetime import date
    from vector_drift import daily_level
    day = date(2026, 11, 19)
    monkeypatch.setattr(daily_level, "daily_today", lambda now=None: day)
    manager = _manager()
    manager.session.level_id = config.DAILY_LEVEL_ID
    manager.session.daily_day = day
    manager.session.random_seed = None
    scene = GameScene(manager)
    manager.switch(scene)
    assert _arrive(scene)["xp_gained"] == 0
    _no_clear_xp(manager)


def test_a_tutorial_clear_gives_no_xp():
    from vector_drift.scenes.tutorial_basics import BasicsScene
    manager = _manager()
    scene = BasicsScene(manager, 0)                 # the "play" step: fly to the planet
    manager.switch(scene)
    _reach(scene)
    assert scene.done
    assert scene._xp_gained == 0
    _no_clear_xp(manager)


def test_a_tutorial_demo_screen_clear_gives_no_xp():
    from vector_drift.scenes.tutorial_play import TutorialGameScene
    manager = _manager()
    scene = TutorialGameScene(manager, _plain_level(1))
    manager.switch(scene)
    _reach(scene)
    assert scene._xp_gained == 0
    _no_clear_xp(manager)


# --- task 18: cleared random maps --------------------------------------------------------
def test_a_new_session_has_no_cleared_random_maps():
    assert Session().random_maps_cleared == 0


def test_each_random_map_counts_once_per_launch():
    from vector_drift.level_presets import RANDOM_LEVEL_ID
    session = Session()
    progression.random_map_clear_xp(session, RANDOM_LEVEL_ID, 123)
    assert session.random_maps_cleared == 1
    progression.random_map_clear_xp(session, RANDOM_LEVEL_ID, 123)
    assert session.random_maps_cleared == 1
    progression.random_map_clear_xp(session, RANDOM_LEVEL_ID, 456)
    assert session.random_maps_cleared == 2


@pytest.mark.usefixtures("no_achievements")
def test_clearing_random_maps_counts_the_maps():
    from vector_drift.level_presets import RANDOM_LEVEL_ID
    manager = _manager()
    for seed in (123, 123, 456):
        _arrive(_scene(RANDOM_LEVEL_ID, manager, seed=seed))
    assert manager.session.random_maps_cleared == 2


@pytest.mark.usefixtures("no_achievements")
def test_fixed_custom_and_daily_clears_do_not_count_as_random_maps(monkeypatch):
    from datetime import date
    from vector_drift import daily_level, data
    manager = _manager()
    _arrive(_scene(1, manager))
    data.register_custom_level(_plain_level(1000))
    manager.session.custom_level_ids.add(1000)
    manager.session.level_source = "custom"
    _arrive(_scene(1000, manager))
    day = date(2026, 11, 19)
    monkeypatch.setattr(daily_level, "daily_today", lambda now=None: day)
    manager.session.daily_day = day
    _arrive(_scene(config.DAILY_LEVEL_ID, manager))
    assert manager.session.random_maps_cleared == 0
