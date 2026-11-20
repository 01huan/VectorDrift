"""The daily challenge page: reached from Daily, Play picks the day."""

from datetime import date
from types import SimpleNamespace

import pygame
import pytest

from vector_drift import config, daily_level
from vector_drift.daily_level import generate_daily
from vector_drift.scenes.base import SceneManager
from vector_drift.scenes.daily_page import DailyScene, long_date
from vector_drift.scenes.game import GameScene
from vector_drift.scenes.levels import LevelSelectScene

pytestmark = pytest.mark.usefixtures("pygame_display")

DAY = date(2026, 11, 20)


@pytest.fixture
def today(monkeypatch):
    """daily_today() answers DAY (tests move it with today.set)."""
    state = SimpleNamespace(day=DAY)
    monkeypatch.setattr(daily_level, "daily_today", lambda now=None: state.day)
    state.set = lambda day: setattr(state, "day", day)
    return state


def _manager():
    audio = SimpleNamespace(play=lambda *a, **k: None, start_loop=lambda *a, **k: None,
                            stop_loop=lambda *a, **k: None)
    return SceneManager(audio)


def _click(scene, rect):
    scene.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=rect.center))


def _key(scene, key):
    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key, mod=0, unicode=""))


def _page(mgr=None):
    mgr = mgr or _manager()
    page = DailyScene(mgr)
    mgr.switch(page)
    return page


def _draw(scene):
    scene.draw(pygame.Surface((config.WINDOW_W, config.WINDOW_H)))


def _texts(scene, monkeypatch):
    """Every string the page draws."""
    from vector_drift.scenes import daily_page
    drawn = []
    real = daily_page.draw_text
    monkeypatch.setattr(daily_page, "draw_text",
                        lambda surface, text, *a, **k: drawn.append(str(text)) or real(surface, text, *a, **k))
    _draw(scene)
    return drawn


# --- getting there -------------------------------------------------------------------

def test_the_daily_button_opens_the_page_not_the_game(today):
    mgr = _manager()
    levels = LevelSelectScene(mgr)
    mgr.switch(levels)
    mgr.session.daily_day = None

    _click(levels, levels.daily_button.rect)

    assert isinstance(mgr.scene, DailyScene)
    assert mgr.session.daily_day is None                # Play decides the day


def test_the_page_shows_its_title_and_today(today, monkeypatch):
    texts = _texts(_page(), monkeypatch)
    assert "DAILY CHALLENGE" in texts
    assert "Friday, November 20, 2026" in texts


def test_long_dates_are_english():
    assert long_date(date(2026, 11, 1)) == "Sunday, November 1, 2026"
    assert long_date(date(2027, 2, 28)) == "Sunday, February 28, 2027"


def test_the_date_follows_midnight_while_the_page_is_open(today, monkeypatch):
    page = _page()
    today.set(date(2026, 11, 21))
    assert "Saturday, November 21, 2026" in _texts(page, monkeypatch)


# --- Play and Back --------------------------------------------------------------------

def test_play_starts_today_s_map(today):
    mgr = _manager()
    mgr.session.fx_text, mgr.session.fy_text = "1", "2"
    mgr.session.random_seed = 5
    page = _page(mgr)

    _click(page, page.play_button.rect)

    game = mgr.scene
    assert isinstance(game, GameScene)
    assert mgr.session.level_id == config.DAILY_LEVEL_ID
    assert mgr.session.daily_day == DAY
    assert mgr.session.random_seed is None
    assert (mgr.session.fx_text, mgr.session.fy_text) == ("", "")       # a fresh editor
    assert game.full_level == generate_daily(DAY).level
    assert game.ship.id == "ship01"


def test_play_picks_the_day_when_pressed(today):
    page = _page()
    today.set(date(2026, 11, 21))                       # the page was opened yesterday
    _click(page, page.play_button.rect)
    assert page.session.daily_day == date(2026, 11, 21)


def test_play_still_works_once_today_is_cleared(today):
    from vector_drift.daily_records import get_record
    mgr = _manager()
    get_record(mgr.session, DAY, create=True)["cleared"] = True
    page = _page(mgr)
    assert page.play_button.enabled
    _click(page, page.play_button.rect)
    assert isinstance(mgr.scene, GameScene)


def test_enter_plays_and_escape_goes_back(today):
    mgr = _manager()
    _key(_page(mgr), pygame.K_RETURN)
    assert isinstance(mgr.scene, GameScene)

    _key(_page(mgr), pygame.K_ESCAPE)
    assert isinstance(mgr.scene, LevelSelectScene)


def test_back_returns_to_the_level_select(today):
    mgr = _manager()
    page = _page(mgr)
    _click(page, page.back_button.rect)
    assert isinstance(mgr.scene, LevelSelectScene)


def test_the_buttons_do_not_overlap(today):
    page = _page()
    assert not page.play_button.rect.colliderect(page.back_button.rect)
    screen = pygame.Rect(0, 0, config.WINDOW_W, config.WINDOW_H)
    assert screen.contains(page.play_button.rect) and screen.contains(page.back_button.rect)
