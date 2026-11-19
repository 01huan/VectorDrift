"""Playing the daily challenge: the level select button and the game screen."""

from datetime import date
from types import SimpleNamespace

import pygame
import pytest

from vector_drift import config, daily_level
from vector_drift.daily_level import daily_map, generate_daily
from vector_drift.scenes.base import SceneManager
from vector_drift.scenes.game import GameScene
from vector_drift.scenes.levels import LevelSelectScene

pytestmark = pytest.mark.usefixtures("pygame_display")

DAY = date(2026, 11, 19)


def _manager():
    audio = SimpleNamespace(play=lambda *a, **k: None, toggle_mute=lambda: None,
                            start_loop=lambda *a, **k: None, stop_loop=lambda *a, **k: None)
    return SceneManager(audio)


def _click(scene, rect):
    scene.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=rect.center))


@pytest.fixture
def today(monkeypatch):
    """daily_today() answers DAY (tests move it with today.set)."""
    state = SimpleNamespace(day=DAY)
    monkeypatch.setattr(daily_level, "daily_today", lambda now=None: state.day)
    state.set = lambda day: setattr(state, "day", day)
    return state


def _enter_daily(mgr):
    levels = LevelSelectScene(mgr)
    mgr.switch(levels)
    _click(levels, levels.daily_button.rect)
    return mgr.scene


# --- the button ------------------------------------------------------------------

def test_daily_button_sits_in_the_top_row_without_overlapping():
    scene = LevelSelectScene(_manager())
    others = [scene.tutorial_button, scene.lab_button, scene.editor_button, scene.shop_button]
    daily = scene.daily_button

    assert daily.label == "Daily"
    assert all(daily.rect.y == b.rect.y and daily.rect.size == b.rect.size for b in others)
    assert daily.rect.right <= scene.tutorial_button.rect.left
    assert not any(daily.rect.colliderect(b.rect) for b in others + [scene.menu_button])
    assert daily.rect.left >= 0
    scene.draw(pygame.Surface((config.WINDOW_W, config.WINDOW_H)))


def test_daily_button_opens_today_s_map(today):
    mgr = _manager()
    game = _enter_daily(mgr)

    assert isinstance(game, GameScene)
    assert mgr.session.daily_day == DAY
    assert mgr.session.level_id == config.DAILY_LEVEL_ID
    assert mgr.session.random_seed is None
    assert game.full_level == generate_daily(DAY).level
    assert game.ship.id == "ship01"


def test_daily_map_is_generated_once_per_day():
    assert daily_map(DAY) is daily_map(DAY)
    assert daily_map(DAY) == generate_daily(DAY)


def test_the_daily_game_screen_says_daily_not_a_level_number(today):
    game = _enter_daily(_manager())

    assert game.level_label() == "DAILY"
    game.draw(pygame.Surface((config.WINDOW_W, config.WINDOW_H)))


def test_other_levels_still_show_their_number():
    mgr = _manager()
    mgr.session.level_id = 1
    assert GameScene(mgr).level_label() == "LV1"


def test_a_daily_level_without_a_day_plays_today(today):
    mgr = _manager()
    mgr.session.level_id = config.DAILY_LEVEL_ID
    mgr.session.daily_day = None

    game = GameScene(mgr)

    assert game.full_level == generate_daily(DAY).level
    assert mgr.session.daily_day == DAY


def test_back_from_daily_returns_to_the_level_select(today):
    from vector_drift.scenes.base import back_scene_for_level

    mgr = _manager()
    game = _enter_daily(mgr)
    assert back_scene_for_level(mgr.session, game) is LevelSelectScene


def test_a_daily_launch_is_not_kept_as_a_replay(today):
    mgr = _manager()
    game = _enter_daily(mgr)
    game.flight = None
    game._replay_frames = []
    game._store_replay("Outcome.TIMEOUT")
    assert mgr.session.replays == []
