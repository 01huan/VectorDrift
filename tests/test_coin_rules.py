"""Where coins come from: pickups (once per fixed coin, once per random map) and
the clear reward (once per fixed level, once per random map). Seeing a full
answer costs only its price: the run's coins stay and the clear still pays."""

from types import SimpleNamespace

import pygame
import pytest

from vector_drift import config
from vector_drift.account.integration import (apply_profile_to_session, reset_session_to_guest,
                                              session_to_profile)
from vector_drift.account.models import PlayerProfile
from vector_drift.data import get_level
from vector_drift.hints import get_hint
from vector_drift.physics import Outcome
from vector_drift.scenes import game as game_module
from vector_drift.scenes.base import SceneManager
from vector_drift.scenes.game import GameScene
from vector_drift.scenes.win import WinScene

pytestmark = pytest.mark.usefixtures("pygame_display")


@pytest.fixture(autouse=True)
def no_solver(monkeypatch):
    monkeypatch.setattr(game_module, "run_solver_async", lambda *a, **k: SimpleNamespace(
        running=True, cancel=lambda: None, stop=lambda *a: True, error=None, result=None))


def _manager():
    audio = SimpleNamespace(play=lambda *a, **k: None, start_loop=lambda *a, **k: None,
                            stop_loop=lambda *a, **k: None)
    manager = SceneManager(audio)
    return manager


def _scene(level_id, manager=None, seed=None):
    manager = manager or _manager()
    manager.session.level_id = level_id
    manager.session.random_seed = seed
    scene = GameScene(manager)
    manager.switch(scene)
    return scene


def _coins(scene):
    return [p for p in scene.pickups if p.kind == "money"]


def _collect(scene, pickup):
    """What a flight does when the ship touches a coin."""
    pickup.consumed = True
    scene.flight = SimpleNamespace(pickup_events=[
        {"kind": "money", "center": pickup.center, "amount": 1}])
    scene._drain_pickup_events()
    scene.flight = None


def _balance(scene):
    return int(scene.session.money)


def _win(scene):
    answer = get_hint(scene.level.id).answers[0]
    scene.editor.set_lines([answer.fx, answer.fy])
    scene._on_text_change(scene.editor)
    scene._try_launch()
    for _ in range(60 * 20):
        if not isinstance(scene.manager.scene, GameScene):
            break
        scene.update(1 / 60)
    assert isinstance(scene.manager.scene, WinScene)


def test_level_one_has_no_coin():
    assert not [p for p in get_level(1).pickups if p.kind == "money"]
    assert not _coins(_scene(1))


def _arrive(scene):
    """End a flight on the target (random maps have no stored answer to fly)."""
    scene.flight = SimpleNamespace(time=1.0, trail=[])
    scene._end_flight(Outcome.REACHED)


def test_clear_reward_is_five():
    assert config.CLEAR_REWARD == 5


@pytest.mark.parametrize("level_id", [1, 3])
def test_first_clear_pays_the_clear_reward(level_id):
    scene = _scene(level_id)
    before = _balance(scene)
    _win(scene)
    assert _balance(scene) == before + config.CLEAR_REWARD


def test_second_clear_of_a_fixed_level_pays_nothing():
    manager = _manager()
    _win(_scene(1, manager))
    _win(_scene(1, manager))
    assert int(manager.session.money) == config.CLEAR_REWARD


def test_clear_reward_does_not_come_from_records():
    manager = _manager()
    manager.session.records[1] = 50.0       # an old best time is not a paid reward
    _win(_scene(1, manager))
    assert int(manager.session.money) == config.CLEAR_REWARD


def test_clear_reward_survives_a_save_and_load():
    manager = _manager()
    _win(_scene(1, manager))
    row = session_to_profile(manager.session, "u1").to_row()

    loaded = _manager()
    apply_profile_to_session(loaded.session, PlayerProfile.from_row(row, "u1"), "u1")
    assert int(loaded.session.money) == config.CLEAR_REWARD
    _win(_scene(1, loaded))
    assert int(loaded.session.money) == config.CLEAR_REWARD


def test_logging_out_forgets_the_paid_clear_rewards():
    manager = _manager()
    _win(_scene(1, manager))
    reset_session_to_guest(manager.session)
    _win(_scene(1, manager))
    assert int(manager.session.money) == config.CLEAR_REWARD


def test_random_map_clear_pays_once_per_seed():
    manager = _manager()
    _arrive(_scene(8, manager, seed=123))
    assert int(manager.session.money) == config.CLEAR_REWARD

    _arrive(_scene(8, manager, seed=123))                  # Retry, same map
    assert int(manager.session.money) == config.CLEAR_REWARD

    _arrive(_scene(8, manager, seed=456))                  # a new map pays again
    assert int(manager.session.money) == 2 * config.CLEAR_REWARD


def test_random_map_clear_reward_is_not_saved():
    manager = _manager()
    _arrive(_scene(8, manager, seed=123))
    row = session_to_profile(manager.session, "u1").to_row()

    loaded = _manager()
    apply_profile_to_session(loaded.session, PlayerProfile.from_row(row, "u1"), "u1")
    _arrive(_scene(8, loaded, seed=123))
    assert int(loaded.session.money) == 2 * config.CLEAR_REWARD


def test_solution_used_clear_still_pays_the_clear_reward():
    manager = _manager()
    scene = _scene(3, manager)
    scene._reveal_solution()
    _win(scene)
    assert int(manager.session.money) == config.CLEAR_REWARD

    # A second clear of the same level pays nothing
    _win(_scene(3, manager))
    assert int(manager.session.money) == config.CLEAR_REWARD


def test_solution_used_clear_still_pays_random_map_reward():
    manager = _manager()
    scene = _scene(8, manager, seed=123)
    scene._reveal_solution()
    _arrive(scene)
    assert int(manager.session.money) == config.CLEAR_REWARD

    _arrive(_scene(8, manager, seed=123))   # same map: already paid
    assert int(manager.session.money) == config.CLEAR_REWARD

    _arrive(_scene(8, manager, seed=456))   # a new map pays again
    assert int(manager.session.money) == 2 * config.CLEAR_REWARD


def test_fixed_coin_pays_once_and_stays_gone_after_reset_and_reentry():
    manager = _manager()
    scene = _scene(2, manager)
    coin = _coins(scene)[0]
    _collect(scene, coin)
    assert _balance(scene) == 1

    scene._reset_level()
    assert all(p.consumed for p in _coins(scene))

    again = _scene(2, manager)
    assert all(p.consumed for p in _coins(again))
    assert int(manager.session.money) == 1


def test_random_coin_pays_once_per_map():
    manager = _manager()
    scene = _scene(8, manager, seed=123)
    coin = _coins(scene)[0]
    _collect(scene, coin)
    assert int(manager.session.money) == 1

    retry = _scene(8, manager, seed=123)                    # same map: already taken
    assert [p.consumed for p in _coins(retry)][0]

    other = _scene(8, manager, seed=456)                    # a new map pays again
    fresh = [p for p in _coins(other) if not p.consumed][0]
    _collect(other, fresh)
    assert int(manager.session.money) == 2


# --- Mission Complete: coins earned this run ---------------------------------

def _finish(scene):
    """Let an arrived run reach the Win screen; return the stats it shows."""
    for _ in range(60 * 5):
        if not isinstance(scene.manager.scene, GameScene):
            break
        scene.update(1 / 60)
    assert isinstance(scene.manager.scene, WinScene)
    return scene.manager.session.stats


def test_win_stats_count_coins_picked_up_plus_the_clear_reward():
    manager = _manager()
    scene = _scene(2, manager)
    _collect(scene, _coins(scene)[0])
    _win(scene)
    stats = manager.session.stats
    assert stats["coins_earned"] == 1 + config.CLEAR_REWARD
    assert stats["clear_reward"] == config.CLEAR_REWARD


def test_win_stats_on_a_second_clear_count_no_reward():
    manager = _manager()
    _win(_scene(1, manager))
    _win(_scene(1, manager))
    assert manager.session.stats["coins_earned"] == 0
    assert manager.session.stats["clear_reward"] == 0


def test_win_stats_after_a_reveal_still_count_coins():
    manager = _manager()
    scene = _scene(2, manager)
    _collect(scene, _coins(scene)[0])                       # coins kept after reveal
    scene._reveal_solution()
    _win(scene)
    assert manager.session.stats["coins_earned"] == 1 + config.CLEAR_REWARD
    assert manager.session.stats["clear_reward"] == config.CLEAR_REWARD
    assert manager.session.stats["solution_used"] is True


def test_win_stats_on_a_random_map():
    manager = _manager()
    scene = _scene(8, manager, seed=123)
    _arrive(scene)
    assert _finish(scene)["coins_earned"] == config.CLEAR_REWARD
