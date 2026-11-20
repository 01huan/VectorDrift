"""Where XP comes from and what it pays: clears, level-up coins (progression.py)."""

from types import SimpleNamespace

import pytest

from vector_drift import achievements, config, progression
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
    """Only the clear's own XP: the achievements a clear unlocks give XP too."""
    monkeypatch.setattr(achievements, "clear", lambda *a, **k: None)


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
