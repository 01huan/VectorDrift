"""Daily challenge coins, clear reward and records: once per day, saved with the profile."""

import json
from datetime import date
from types import SimpleNamespace

import pygame
import pytest

from vector_drift import config, daily_level
from vector_drift.account.integration import apply_profile_to_session, session_to_profile
from vector_drift.account.models import PlayerProfile
from vector_drift.daily_level import daily_map
from vector_drift.daily_records import get_record
from vector_drift.scenes.base import SceneManager
from vector_drift.scenes.game import GameScene
from vector_drift.scenes.win import WinScene

pytestmark = pytest.mark.usefixtures("pygame_display")

DAY = date(2026, 11, 19)
NEXT_DAY = date(2026, 11, 20)


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    """daily_today() answers DAY until a test moves it."""
    state = SimpleNamespace(day=DAY)
    monkeypatch.setattr(daily_level, "daily_today", lambda now=None: state.day)
    return state


def _manager():
    audio = SimpleNamespace(play=lambda *a, **k: None, start_loop=lambda *a, **k: None,
                            stop_loop=lambda *a, **k: None)
    return SceneManager(audio)


def _daily(manager=None, day=DAY):
    """The game screen on ``day``'s map, entered the way the Daily button does."""
    manager = manager or _manager()
    manager.session.level_id = config.DAILY_LEVEL_ID
    manager.session.daily_day = day
    manager.session.random_seed = None
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


def _fly(scene, fx, fy):
    scene.editor.set_lines([fx, fy])
    scene._on_text_change(scene.editor)
    scene._try_launch()
    for _ in range(60 * 20):
        if scene.manager.scene is not scene or scene.flight is None:
            break
        scene.update(1 / 60)


def _win(scene):
    """Fly the day's reference answer to the target, then on to the Win screen."""
    answer = daily_map(scene.session.daily_day)
    _fly(scene, answer.fx, answer.fy)
    for _ in range(60 * 5):
        if isinstance(scene.manager.scene, WinScene):
            break
        scene.update(1 / 60)
    assert isinstance(scene.manager.scene, WinScene)


def _reloaded(manager):
    """A new game launch that loads what ``manager`` saved."""
    row = json.loads(json.dumps(session_to_profile(manager.session, "u").to_row()))
    again = _manager()
    apply_profile_to_session(again.session, PlayerProfile.from_row(row, "u"), "u")
    return again


def _balance(manager):
    return int(manager.session.money)


# --- coins and clear reward ------------------------------------------------------------

def test_a_daily_coin_pays_once_per_day():
    scene = _daily()
    coin = _coins(scene)[0]

    _collect(scene, coin)
    assert _balance(scene.manager) == 1
    record = get_record(scene.session, DAY)
    assert record["coins_taken"] == [list(coin.center)]

    again = _daily(scene.manager)
    assert all(p.consumed for p in _coins(again) if p.center == coin.center)
    _collect(again, next(p for p in _coins(again) if p.center == coin.center))
    assert _balance(scene.manager) == 1


def test_daily_coins_are_not_fixed_level_coins():
    scene = _daily()
    _collect(scene, _coins(scene)[0])
    assert scene.session.collected_money_pickups == set()


def test_the_clear_reward_pays_once_per_day():
    manager = _manager()
    scene = _daily(manager)
    coins = len(_coins(scene))

    _win(scene)
    assert _balance(manager) == coins + config.CLEAR_REWARD
    assert manager.session.stats["clear_reward"] == config.CLEAR_REWARD
    assert get_record(manager.session, DAY)["clear_rewarded"]
    assert config.DAILY_LEVEL_ID not in manager.session.clear_rewarded_levels

    _win(_daily(manager))
    assert _balance(manager) == coins + config.CLEAR_REWARD
    assert not manager.session.stats.get("clear_reward")


def test_nothing_pays_again_after_reloading_the_save():
    first = _manager()
    scene = _daily(first)
    coins = len(_coins(scene))
    _win(scene)

    second = _reloaded(first)
    before = _balance(second)
    _win(_daily(second))

    assert _balance(second) == before == coins + config.CLEAR_REWARD


def test_the_win_screen_says_the_reward_was_collected_today():
    manager = _manager()
    _win(_daily(manager))
    _win(_daily(manager))

    notes = manager.scene._notes(manager.session.stats)

    assert notes == [("Clear reward already collected today", config.TEXT_DIM)]
    manager.scene.draw(pygame.Surface((config.WINDOW_W, config.WINDOW_H)))


def test_a_clear_after_midnight_counts_for_the_day_entered(clock):
    from vector_drift.scenes.levels import LevelSelectScene

    manager = _manager()
    levels = LevelSelectScene(manager)
    manager.switch(levels)
    levels.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1,
                                           pos=levels.daily_button.rect.center))   # 23:59
    clock.day = NEXT_DAY                                                            # 00:05
    retry = GameScene(manager)          # Retry builds a new game screen
    manager.switch(retry)

    _win(retry)

    assert get_record(manager.session, DAY)["clear_rewarded"]
    assert get_record(manager.session, NEXT_DAY) is None
