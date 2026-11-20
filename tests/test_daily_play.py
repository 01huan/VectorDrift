"""Playing the daily challenge: the level select button and the game screen."""

from datetime import date
from types import SimpleNamespace

import pygame
import pytest

from vector_drift import config, daily_level
from vector_drift.daily_level import daily_map, generate_daily
from vector_drift.daily_records import get_record
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
    """Daily on the level select, then Play on the daily page."""
    levels = LevelSelectScene(mgr)
    mgr.switch(levels)
    _click(levels, levels.daily_button.rect)
    page = mgr.scene
    _click(page, page.play_button.rect)
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


def test_daily_then_play_opens_today_s_map(today):
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


def test_pressing_play_again_picks_the_new_day(today):
    mgr = _manager()
    _after_midnight(today, mgr)

    again = _enter_daily(mgr)

    assert mgr.session.daily_day == NEXT_DAY
    assert again.full_level == generate_daily(NEXT_DAY).level


# --- the Answer button (no Hint, no AI Solver) -------------------------------------------

def _drawn_buttons(game):
    drawn = []
    for name in ("ai_button", "lab_button"):
        button = getattr(game, name)
        button.draw = lambda surface, name=name, b=button: drawn.append((name, b.label))
    game.draw(pygame.Surface((config.WINDOW_W, config.WINDOW_H)))
    return drawn


def test_the_daily_map_shows_answer_where_hint_sits(today):
    game = _enter_daily(_manager())
    fixed = _manager()
    fixed.session.level_id = 1
    hint_rect = GameScene(fixed).ai_button.rect

    assert game.daily_answer
    assert game.ai_solver is None and game.ai_job is None
    assert _drawn_buttons(game) == [("ai_button", "Answer"), ("lab_button", "Lab")]
    assert game.ai_button.rect == hint_rect
    assert game.ai_button.enabled


def test_the_answer_button_opens_no_hint_or_ai_solver(today):
    game = _enter_daily(_manager())
    _click(game, game.ai_button.rect)
    assert game.hint_popup is None and not game.ai_popup


def test_the_answer_button_works_during_a_flight_like_hint(today):
    from vector_drift.scenes.game import FLIGHT
    game = _enter_daily(_manager())
    game.editor.set_lines(["1", "0"])
    game._on_text_change(game.editor)
    game._try_launch()
    assert game.state == FLIGHT
    game.draw(pygame.Surface((config.WINDOW_W, config.WINDOW_H)))
    assert game.ai_button.enabled


def test_the_answer_button_is_off_once_the_map_is_cleared(today):
    from vector_drift.scenes.game import ARRIVED
    game = _enter_daily(_manager())
    game.state = ARRIVED
    game.draw(pygame.Surface((config.WINDOW_W, config.WINDOW_H)))
    assert not game.ai_button.enabled


def test_the_lab_still_opens_on_the_daily_map(today):
    game = _enter_daily(_manager())
    _click(game, game.lab_button.rect)
    assert game.lab_popup


def test_fixed_levels_keep_their_hint_button():
    mgr = _manager()
    mgr.session.level_id = 1
    game = GameScene(mgr)
    assert not game.daily_answer
    assert _drawn_buttons(game) == [("ai_button", "Hint"), ("lab_button", "Lab")]


def test_random_levels_keep_their_ai_solver_button():
    mgr = _manager()
    mgr.session.level_id = 999
    mgr.session.random_seed = 7
    game = GameScene(mgr)
    assert not game.daily_answer
    assert _drawn_buttons(game) == [("ai_button", "AI Solver"), ("lab_button", "Lab")]



# --- today's clear on the button ---------------------------------------------------------

def _level_select_after(today, cleared_day):
    mgr = _manager()
    if cleared_day is not None:
        get_record(mgr.session, cleared_day, create=True)["cleared"] = True
    scene = LevelSelectScene(mgr)
    mgr.switch(scene)
    return scene


def test_daily_button_has_no_check_before_today_s_clear(today):
    scene = _level_select_after(today, None)
    assert scene.daily_check_rect() is None
    get_record(scene.session, DAY, create=True)        # played, not cleared
    assert scene.daily_check_rect() is None


def test_daily_button_shows_a_check_once_today_is_cleared(today):
    scene = _level_select_after(today, DAY)

    check = scene.daily_check_rect()

    assert check is not None and scene.daily_button.rect.contains(check)
    scene.draw(pygame.Surface((config.WINDOW_W, config.WINDOW_H)))


def test_yesterday_s_clear_does_not_check_today(today):
    scene = _level_select_after(today, DAY)
    today.set(date(2026, 11, 20))
    assert scene.daily_check_rect() is None
