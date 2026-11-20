"""XP for daily challenge clears: XP_DAILY with a streak bonus on the day's first clear."""

import json
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from vector_drift import config, daily_level, progression
from vector_drift.account.integration import apply_profile_to_session, session_to_profile
from vector_drift.account.models import PlayerProfile
from vector_drift.daily_records import get_record, mark_answer_used
from vector_drift.physics import Outcome
from vector_drift.scenes import game as game_module
from vector_drift.scenes.base import SceneManager
from vector_drift.scenes.game import GameScene
from vector_drift.scenes.win import WinScene

pytestmark = pytest.mark.usefixtures("pygame_display")

DAY = date(2026, 11, 19)


@pytest.fixture(autouse=True)
def setup(monkeypatch):
    monkeypatch.setattr(daily_level, "daily_today", lambda now=None: DAY)
    monkeypatch.setattr(game_module, "run_solver_async", lambda *a, **k: SimpleNamespace(
        running=True, cancel=lambda: None, stop=lambda *a: True, error=None, result=None))
    # Only the clear's own XP: achievements still unlock but give no XP here.
    monkeypatch.setattr(progression, "achievement_xp", lambda session, key: 0)


def _manager(streak_before=0):
    """A player who cleared the ``streak_before`` days right before DAY."""
    audio = SimpleNamespace(play=lambda *a, **k: None, start_loop=lambda *a, **k: None,
                            stop_loop=lambda *a, **k: None)
    manager = SceneManager(audio)
    for n in range(1, streak_before + 1):
        record = get_record(manager.session, DAY - timedelta(days=n), create=True)
        record.update(cleared=True, xp_clears=1)
    return manager


def _reloaded(manager):
    """A new game launch that loads what ``manager`` saved."""
    row = json.loads(json.dumps(session_to_profile(manager.session, "u").to_row()))
    again = SceneManager(manager.audio)
    apply_profile_to_session(again.session, PlayerProfile.from_row(row, "u"), "u")
    return again


def _clear(manager, day=DAY):
    """Clear ``day``'s map; return the Win screen's stats."""
    manager.session.level_id = config.DAILY_LEVEL_ID
    manager.session.daily_day = day
    manager.session.random_seed = None
    scene = GameScene(manager)
    manager.switch(scene)
    scene.flight = SimpleNamespace(time=1.0, trail=[], x=0.0, y=0.0)
    scene._end_flight(Outcome.REACHED)
    for _ in range(60 * 5):
        if not isinstance(manager.scene, GameScene):
            break
        scene.update(1 / 60)
    assert isinstance(manager.scene, WinScene)
    return manager.session.stats


def test_the_third_day_in_a_row_gives_360_then_150_then_100_after_reloading():
    manager = _manager(streak_before=2)
    assert _clear(manager)["xp_gained"] == 360
    assert manager.session.xp_total == 360
    assert _clear(manager)["xp_gained"] == 150

    again = _reloaded(manager)
    assert get_record(again.session, DAY)["xp_clears"] == 2
    assert _clear(again)["xp_gained"] == 100
    assert get_record(again.session, DAY)["xp_clears"] == 3
    assert again.session.xp_total == 610


@pytest.mark.parametrize("streak_before, xp", [(0, 300), (1, 330), (3, 390), (4, 420), (9, 420)])
def test_the_first_clear_counts_today_in_the_streak(streak_before, xp):
    assert _clear(_manager(streak_before))["xp_gained"] == xp


def test_a_missed_day_breaks_the_bonus():
    manager = _manager()
    get_record(manager.session, DAY - timedelta(days=2), create=True)["cleared"] = True
    assert _clear(manager)["xp_gained"] == 300


def test_a_clear_after_the_answer_still_gives_xp():
    manager = _manager(streak_before=1)
    mark_answer_used(manager.session, DAY)
    assert _clear(manager)["xp_gained"] == 330


def test_the_streak_ends_on_the_day_being_played(monkeypatch):
    manager = _manager(streak_before=1)                 # DAY - 1 cleared
    monkeypatch.setattr(daily_level, "daily_today", lambda now=None: DAY + timedelta(days=1))
    assert _clear(manager, DAY)["xp_gained"] == 330     # DAY's map, finished after midnight
    assert get_record(manager.session, DAY + timedelta(days=1)) is None


def test_the_daily_xp_levels_up_like_any_clear():
    manager = _manager()
    stats = _clear(manager)
    assert manager.session.xp_rewarded_level == 3       # 300 XP: Lv 1 -> 3
    assert stats["level_up"] == {"from": 1, "to": 3, "coins": 2 * config.LEVEL_UP_COINS}
    assert stats["xp_before"] == 0


def test_the_win_screen_no_longer_says_no_xp_for_the_daily():
    manager = _manager()
    _clear(manager)
    assert manager.scene._xp_notes() == []


# --- the streak bonus on the win screen (task 35) ------------------------------------------

def _notes(manager):
    scene = manager.scene
    return scene._notes(manager.session.stats) + scene._xp_notes()


def test_the_day_s_first_clear_in_a_streak_shows_its_bonus():
    manager = _manager(streak_before=2)
    stats = _clear(manager)
    assert stats["streak_bonus"] == {"xp": 60, "days": 3}
    assert ("Streak bonus +60 (3 days)", config.WARNING) in _notes(manager)
    import pygame
    manager.scene.draw(pygame.Surface((config.WINDOW_W, config.WINDOW_H)))


def test_a_long_streak_shows_its_real_length_with_the_capped_bonus():
    manager = _manager(streak_before=11)
    _clear(manager)
    assert ("Streak bonus +120 (12 days)", config.WARNING) in _notes(manager)


def test_no_bonus_line_without_a_streak_or_on_a_later_clear():
    manager = _manager()
    assert "streak_bonus" not in _clear(manager)                    # a one-day streak
    assert not any(text.startswith("Streak") for text, _c in _notes(manager))

    manager = _manager(streak_before=2)
    _clear(manager)
    assert "streak_bonus" not in _clear(manager)                    # the day's second clear
    assert not any(text.startswith("Streak") for text, _c in _notes(manager))


def _win_screen(monkeypatch, level_id, **stats):
    """Draw the Win screen for ``stats``; return (scene, every text drawn with its rect)."""
    import pygame
    from vector_drift.scenes import base, win, xp_ui
    manager = _manager()
    manager.session.level_id = level_id
    manager.session.stats = {"time": 1.0, "total_time": 1.0, "attempts": 1, "lives_left": 5,
                             "max_lives": 5, "fx": "1", "fy": "0", "coins_earned": 0,
                             "clear_reward": 0, **stats}
    scene = WinScene(manager)
    drawn = []
    real = base.draw_text

    def spy(surface, text, *args, **kwargs):
        rect = real(surface, text, *args, **kwargs)
        drawn.append((text, rect))
        return rect

    for module in (win, base, xp_ui):
        monkeypatch.setattr(module, "draw_text", spy)
    scene.draw(pygame.Surface((config.WINDOW_W, config.WINDOW_H)))
    return scene, drawn


def test_other_levels_show_no_bonus_line(monkeypatch):
    _scene, drawn = _win_screen(monkeypatch, 1, xp_gained=100, streak_bonus={"xp": 60, "days": 3})
    assert not any(str(text).startswith("Streak") for text, _r in drawn)


def test_the_bonus_line_sits_in_the_notes_above_the_buttons(monkeypatch):
    scene, drawn = _win_screen(monkeypatch, config.DAILY_LEVEL_ID, xp_gained=360, clear_reward=5,
                               coins_earned=5, streak_bonus={"xp": 60, "days": 3})
    rect = next(r for text, r in drawn if text == "Streak bonus +60 (3 days)")
    xp_rect = next(r for text, r in drawn if text == "+360")
    assert rect.top > xp_rect.bottom
    assert abs(rect.centerx - config.WINDOW_W // 2) <= 1
    assert rect.bottom < scene.xp_bar_rect.top
    for button in (scene.replay_button, scene.levels_button, scene.menu_button):
        assert rect.bottom < button.rect.top
