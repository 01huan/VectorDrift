"""Where coins come from: pickups only, once per fixed coin, once per random map."""

from types import SimpleNamespace

import pygame
import pytest

from vector_drift import config
from vector_drift.data import get_level
from vector_drift.hints import get_hint
from vector_drift.scenes import game as game_module
from vector_drift.scenes.base import SceneManager
from vector_drift.scenes.game import GameScene
from vector_drift.scenes.win import WinScene
from vector_drift.story import all_seen_keys

pytestmark = pytest.mark.usefixtures("pygame_display")


@pytest.fixture(autouse=True)
def no_solver(monkeypatch):
    monkeypatch.setattr(game_module, "run_solver_async", lambda *a, **k: SimpleNamespace(
        running=True, cancel=lambda: None, stop=lambda *a: True, error=None, result=None))


def _manager():
    audio = SimpleNamespace(play=lambda *a, **k: None, start_loop=lambda *a, **k: None,
                            stop_loop=lambda *a, **k: None)
    manager = SceneManager(audio)
    manager.session.story_seen = all_seen_keys()     # no story dialogue in the way
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


@pytest.mark.parametrize("level_id", [1, 3])
def test_clearing_a_level_gives_no_coins(level_id):
    scene = _scene(level_id)
    before = _balance(scene)
    _win(scene)
    assert _balance(scene) == before


def test_clearing_again_gives_no_coins():
    manager = _manager()
    manager.session.records[1] = 50.0
    scene = _scene(1, manager)
    _win(scene)
    assert int(manager.session.money) == 0


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
    scene = _scene(7, manager, seed=123)
    coin = _coins(scene)[0]
    _collect(scene, coin)
    assert int(manager.session.money) == 1

    retry = _scene(7, manager, seed=123)                    # same map: already taken
    assert [p.consumed for p in _coins(retry)][0]

    other = _scene(7, manager, seed=456)                    # a new map pays again
    fresh = [p for p in _coins(other) if not p.consumed][0]
    _collect(other, fresh)
    assert int(manager.session.money) == 2
