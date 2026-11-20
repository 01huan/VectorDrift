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


# --- back to the page from a daily game (task 25) ---------------------------------------------

def _daily_game(mgr):
    page = _page(mgr)
    _click(page, page.play_button.rect)
    assert isinstance(mgr.scene, GameScene)
    return mgr.scene


def _result_screen(mgr, result):
    from vector_drift.scenes.fail import FailScene
    from vector_drift.scenes.win import WinScene
    mgr.session.stats = {}
    screen = WinScene(mgr) if result == "win" else FailScene(mgr)
    mgr.switch(screen)
    return screen


def _pause(game):
    from vector_drift.scenes.pause_menu import PauseMenu
    game._open_pause()
    assert isinstance(game.pause_menu, PauseMenu)
    return game.pause_menu


def _pause_button(menu, action):
    return next(button for button, act in menu.buttons() if act == action)


def test_the_game_s_back_button_opens_the_daily_page(today):
    mgr = _manager()
    game = _daily_game(mgr)
    _click(game, game.level_button.rect)
    assert isinstance(mgr.scene, DailyScene)


@pytest.mark.parametrize("result", ["win", "fail"])
def test_result_screens_go_back_to_the_daily_page(today, result):
    from vector_drift.scenes.menu import MenuScene
    mgr = _manager()
    _daily_game(mgr)
    screen = _result_screen(mgr, result)

    assert screen.levels_button.label == "Daily"
    _click(screen, screen.levels_button.rect)
    assert isinstance(mgr.scene, DailyScene)

    _daily_game(mgr)
    screen = _result_screen(mgr, result)
    _click(screen, screen.menu_button.rect)
    assert isinstance(mgr.scene, MenuScene)


def test_the_pause_menu_goes_back_to_the_daily_page(today):
    from vector_drift.scenes.menu import MenuScene
    mgr = _manager()
    game = _daily_game(mgr)
    menu = _pause(game)
    button = _pause_button(menu, "levels")

    assert button.label == "Daily"
    _click(game, button.rect)
    assert isinstance(mgr.scene, DailyScene)

    game = _daily_game(mgr)
    _click(game, _pause_button(_pause(game), "menu").rect)
    assert isinstance(mgr.scene, MenuScene)


@pytest.mark.parametrize("result", ["win", "fail"])
def test_other_levels_still_go_back_to_the_level_select(today, result):
    mgr = _manager()
    mgr.session.level_id = 1
    game = GameScene(mgr)
    mgr.switch(game)
    menu = _pause(game)
    button = _pause_button(menu, "levels")
    assert button.label == "Levels"
    _click(game, button.rect)
    assert isinstance(mgr.scene, LevelSelectScene)

    screen = _result_screen(mgr, result)
    assert screen.levels_button.label == "Levels"
    _click(screen, screen.levels_button.rect)
    assert isinstance(mgr.scene, LevelSelectScene)


def test_play_after_midnight_from_the_result_screen_is_a_new_day(today):
    mgr = _manager()
    first = _daily_game(mgr)                            # Play at 23:59
    today.set(date(2026, 11, 21))                       # 00:05
    screen = _result_screen(mgr, "win")
    _click(screen, screen.levels_button.rect)
    page = mgr.scene
    assert isinstance(page, DailyScene)

    _click(page, page.play_button.rect)

    assert mgr.session.daily_day == date(2026, 11, 21)
    assert mgr.scene.full_level == generate_daily(date(2026, 11, 21)).level
    assert mgr.scene.full_level != first.full_level


def test_restart_retry_and_replay_keep_the_day(today):
    mgr = _manager()
    _daily_game(mgr)
    today.set(date(2026, 11, 21))
    game = mgr.scene
    _click(game, _pause_button(_pause(game), "restart").rect)
    assert mgr.session.daily_day == DAY
    for result in ("win", "fail"):
        screen = _result_screen(mgr, result)
        _click(screen, (screen.replay_button if result == "win" else screen.retry_button).rect)
        assert isinstance(mgr.scene, GameScene) and mgr.session.daily_day == DAY


# --- the calendar (task 26) ---------------------------------------------------------------

def _record(mgr, day, **fields):
    from vector_drift.daily_records import get_record
    get_record(mgr.session, day, create=True).update(fields)


def test_day_marks_tell_every_state_apart():
    from vector_drift.scenes.daily_page import DayMarks, day_marks
    past, today_, future = date(2026, 11, 19), DAY, date(2026, 11, 21)
    assert day_marks({"cleared": True}, past, today_) == DayMarks("cleared", False, False)
    assert day_marks({"cleared": True, "answer_used": True}, past, today_) == DayMarks("cleared", True, False)
    assert day_marks({"cleared": False}, past, today_) == DayMarks("failed", False, False)
    assert day_marks(None, past, today_) == DayMarks("none", False, False)
    assert day_marks(None, today_, today_) == DayMarks("none", False, True)
    assert day_marks({"cleared": True}, today_, today_) == DayMarks("cleared", False, True)
    assert day_marks(None, future, today_) == DayMarks("future", False, False)


def test_the_calendar_shows_this_month_sunday_first(today):
    page = _page()
    cells = page.day_cells()

    assert page.month == (2026, 11)
    assert [d.day for d, _r in cells] == list(range(1, 31))
    by_day = {d.day: r for d, r in cells}
    assert by_day[1].x == by_day[8].x == by_day[29].x       # 11/1/2026 is a Sunday: first column
    assert by_day[1].x < by_day[2].x < by_day[7].x
    assert by_day[7].y == by_day[1].y and by_day[8].y > by_day[1].y


def test_a_month_starting_late_in_the_week_needs_six_rows_that_fit(today):
    from vector_drift.scenes.daily_page import calendar_card_rect
    today.set(date(2026, 8, 15))                            # 8/1/2026 is a Saturday
    page = _page()
    cells = page.day_cells()
    rows = sorted({r.y for _d, r in cells})

    assert len(rows) == 6
    card = calendar_card_rect()
    screen = pygame.Rect(0, 0, config.WINDOW_W, config.WINDOW_H)
    assert screen.contains(card)
    assert all(card.contains(r) for _d, r in cells)
    for button in (page.play_button, page.back_button):
        assert not card.colliderect(button.rect)
    rects = [r for _d, r in cells]
    assert not any(a.colliderect(b) for i, a in enumerate(rects) for b in rects[i + 1:])


def test_each_day_is_marked_from_its_record(today):
    mgr = _manager()
    _record(mgr, date(2026, 11, 3), cleared=True)
    _record(mgr, date(2026, 11, 4), cleared=True, answer_used=True)
    _record(mgr, date(2026, 11, 5))
    page = _page(mgr)

    assert page.marks(date(2026, 11, 3)).state == "cleared"
    assert page.marks(date(2026, 11, 4)) == ("cleared", True, False)
    assert page.marks(date(2026, 11, 5)).state == "failed"
    assert page.marks(date(2026, 11, 6)).state == "none"
    assert page.marks(DAY).today
    assert page.marks(date(2026, 11, 21)).state == "future"
    _draw(page)


def test_today_follows_midnight_while_the_page_is_open(today):
    page = _page()
    today.set(date(2026, 11, 21))
    assert page.marks(date(2026, 11, 21)) == ("none", False, True)
    assert not page.marks(DAY).today


def test_the_month_title_and_weekdays_are_drawn(today, monkeypatch):
    texts = _texts(_page(), monkeypatch)
    assert "November 2026" in texts
    assert [t for t in texts if t in ("Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat")] == \
        ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]


# --- switching months (task 27) ----------------------------------------------------------------

def test_shift_month_crosses_years():
    from vector_drift.scenes.daily_page import shift_month
    assert shift_month((2026, 11), 1) == (2026, 12)
    assert shift_month((2026, 12), 1) == (2027, 1)
    assert shift_month((2026, 1), -1) == (2025, 12)


def test_month_range_runs_from_the_first_record_to_today():
    from vector_drift.scenes.daily_page import month_range
    records = {"2026-09-14": {}, "2026-11-02": {}}
    assert month_range({}, DAY) == ((2026, 11), (2026, 11))
    assert month_range(records, DAY) == ((2026, 9), (2026, 11))
    assert month_range({"2025-12-31": {}}, DAY) == ((2025, 12), (2026, 11))
    assert month_range({"2027-01-01": {}}, DAY) == ((2026, 11), (2026, 11))


def test_without_records_neither_arrow_works(today):
    page = _page()
    assert not page.prev_arrow.enabled and not page.next_arrow.enabled
    _click(page, page.prev_arrow.rect)
    _key(page, pygame.K_LEFT)
    _click(page, page.next_arrow.rect)
    assert page.month == (2026, 11)
    _draw(page)


def test_the_arrows_walk_back_to_the_first_record_and_stop(today, monkeypatch):
    mgr = _manager()
    _record(mgr, date(2026, 9, 14), cleared=True)
    page = _page(mgr)

    assert page.month == (2026, 11)
    assert page.prev_arrow.enabled and not page.next_arrow.enabled
    _click(page, page.prev_arrow.rect)
    assert page.month == (2026, 10)
    assert page.prev_arrow.enabled and page.next_arrow.enabled
    _click(page, page.prev_arrow.rect)
    assert page.month == (2026, 9)
    assert not page.prev_arrow.enabled
    _click(page, page.prev_arrow.rect)                  # at the end: nothing happens
    assert page.month == (2026, 9)

    assert page.marks(date(2026, 9, 14)).state == "cleared"
    assert "September 2026" in _texts(page, monkeypatch)
    assert [d.day for d, _r in page.day_cells()] == list(range(1, 31))

    _click(page, page.next_arrow.rect)
    assert page.month == (2026, 10)


def test_arrow_keys_switch_months(today):
    mgr = _manager()
    _record(mgr, date(2026, 10, 1))
    page = _page(mgr)
    _key(page, pygame.K_LEFT)
    assert page.month == (2026, 10)
    _key(page, pygame.K_RIGHT)
    assert page.month == (2026, 11)
    _key(page, pygame.K_RIGHT)
    assert page.month == (2026, 11)


def test_the_page_always_opens_on_today_s_month(today):
    mgr = _manager()
    _record(mgr, date(2026, 9, 1))
    page = _page(mgr)
    _key(page, pygame.K_LEFT)
    _key(page, pygame.K_LEFT)
    assert _page(mgr).month == (2026, 11)


def test_a_new_month_at_midnight_opens_the_next_arrow(today):
    today.set(date(2026, 11, 30))
    page = _page()
    assert not page.next_arrow.enabled
    today.set(date(2026, 12, 1))
    _draw(page)
    assert page.month == (2026, 11)                     # the shown month stays
    assert page.next_arrow.enabled
    _click(page, page.next_arrow.rect)
    assert page.month == (2026, 12)


def test_disabled_arrows_take_no_hover(today):
    page = _page()
    page.handle_event(pygame.event.Event(pygame.MOUSEMOTION, pos=page.prev_arrow.rect.center,
                                         rel=(0, 0), buttons=(0, 0, 0)))
    assert not page.prev_arrow.hover


def test_the_arrows_sit_beside_the_month_title_clear_of_the_days(today):
    from vector_drift.scenes.daily_page import calendar_card_rect
    page = _page()
    card = calendar_card_rect()
    for arrow in (page.prev_arrow, page.next_arrow):
        assert card.contains(arrow.rect)
        assert not any(arrow.rect.colliderect(r) for _d, r in page.day_cells())
    assert page.prev_arrow.rect.right < page.next_arrow.rect.left
