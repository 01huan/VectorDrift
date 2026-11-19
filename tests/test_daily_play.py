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


# --- the same map until the player leaves -------------------------------------------

NEXT_DAY = date(2026, 11, 20)


def _after_midnight(today, mgr):
    """Enter at 23:59 on DAY; the clock then moves on to 00:05 of the next day."""
    game = _enter_daily(mgr)
    today.set(NEXT_DAY)
    return game


def _restart_from_pause(mgr, game):
    from vector_drift.scenes.pause_menu import PauseMenu

    game.pause_menu = PauseMenu()
    button = next(button for button, action in game.pause_menu.buttons() if action == "restart")
    game.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=button.rect.center))
    return mgr.scene


def test_restart_after_midnight_keeps_the_day(today):
    mgr = _manager()
    first = _after_midnight(today, mgr)

    again = _restart_from_pause(mgr, first)

    assert again is not first and isinstance(again, GameScene)
    assert mgr.session.daily_day == DAY
    assert again.full_level == first.full_level == generate_daily(DAY).level


@pytest.mark.parametrize("result", ["win", "fail"])
def test_retry_after_midnight_keeps_the_day(today, result):
    from vector_drift.scenes.fail import FailScene
    from vector_drift.scenes.win import WinScene

    mgr = _manager()
    first = _after_midnight(today, mgr)
    mgr.session.stats = {}
    screen = WinScene(mgr) if result == "win" else FailScene(mgr)
    mgr.switch(screen)
    button = screen.replay_button if result == "win" else screen.retry_button

    _click(screen, button.rect)

    assert isinstance(mgr.scene, GameScene)
    assert mgr.session.daily_day == DAY
    assert mgr.scene.full_level == first.full_level


def test_pressing_daily_again_picks_the_new_day(today):
    mgr = _manager()
    _after_midnight(today, mgr)

    again = _enter_daily(mgr)

    assert mgr.session.daily_day == NEXT_DAY
    assert again.full_level == generate_daily(NEXT_DAY).level


# --- no Hint and no AI Solver -----------------------------------------------------------

def _drawn_buttons(game):
    drawn = []
    for name in ("ai_button", "lab_button"):
        button = getattr(game, name)
        button.draw = lambda surface, name=name: drawn.append(name)
    game.draw(pygame.Surface((config.WINDOW_W, config.WINDOW_H)))
    return drawn


def test_the_daily_map_has_no_hint_or_ai_solver(today):
    game = _enter_daily(_manager())

    assert not game.show_answer_help
    assert game.ai_solver is None and game.ai_job is None
    assert _drawn_buttons(game) == ["lab_button"]

    _click(game, game.ai_button.rect)
    assert game.hint_popup is None and not game.ai_popup


def test_the_lab_still_opens_on_the_daily_map(today):
    game = _enter_daily(_manager())
    _click(game, game.lab_button.rect)
    assert game.lab_popup


def test_fixed_levels_keep_their_hint_button():
    mgr = _manager()
    mgr.session.level_id = 1
    game = GameScene(mgr)
    assert game.show_answer_help
    assert _drawn_buttons(game) == ["ai_button", "lab_button"]
