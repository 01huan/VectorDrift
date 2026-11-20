"""The player level on screen: level select row, win screen bar, level-up popup."""

from types import SimpleNamespace

import pygame
import pytest

from vector_drift import config
from vector_drift.level_presets import RANDOM_LEVEL_ID
from vector_drift.scenes import levels, xp_ui
from vector_drift.scenes.base import SceneManager

pytestmark = pytest.mark.usefixtures("pygame_display")


def _manager(xp_total=0, coins=1234):
    audio = SimpleNamespace(play=lambda *a, **k: None, start_loop=lambda *a, **k: None,
                            stop_loop=lambda *a, **k: None)
    manager = SceneManager(audio)
    manager.session.money.add(coins)
    manager.session.xp_total = xp_total
    return manager


def _texts(module, monkeypatch):
    texts = []
    real = module.draw_text

    def spy(surface, text, *args, **kwargs):
        texts.append(text)
        return real(surface, text, *args, **kwargs)

    monkeypatch.setattr(module, "draw_text", spy)
    return texts


def _screen():
    return pygame.Surface((config.WINDOW_W, config.WINDOW_H))


# --- task 14: level select ------------------------------------------------------------
def test_level_select_shows_the_level_and_the_xp_into_it(monkeypatch):
    texts = _texts(xp_ui, monkeypatch)
    levels.LevelSelectScene(_manager(xp_total=290)).draw(_screen())
    assert "Lv 3" in texts
    assert "40 / 200 XP" in texts


def test_a_new_player_is_level_one_with_an_empty_bar(monkeypatch):
    texts = _texts(xp_ui, monkeypatch)
    levels.LevelSelectScene(_manager()).draw(_screen())
    assert "Lv 1" in texts and "0 / 100 XP" in texts


@pytest.mark.parametrize("coins", [0, 1234, 9_999_999])
def test_the_level_row_sits_under_the_balance_clear_of_everything(coins):
    scene = levels.LevelSelectScene(_manager(xp_total=2699, coins=coins))
    scene.draw(_screen())
    row = scene.level_row_rect
    balance = scene.balance_rect
    assert row.top >= balance.bottom
    assert row.left == balance.left
    buttons = [scene.daily_button, scene.tutorial_button, scene.lab_button,
               scene.editor_button, scene.shop_button, scene.menu_button]
    for button in buttons:
        assert not row.colliderect(button.rect), button.label if hasattr(button, "label") else button
    assert not row.colliderect(scene.grid_rect())
    assert not row.colliderect(scene.prev_arrow.rect)


def test_the_bar_fill_follows_the_fraction():
    surface = pygame.Surface((200, 20))
    rect = pygame.Rect(0, 0, 200, 10)
    assert xp_ui.bar_fill_width(rect, 0.0) == 0
    assert xp_ui.bar_fill_width(rect, 0.5) == 100
    assert xp_ui.bar_fill_width(rect, 1.0) == 200
    assert xp_ui.bar_fill_width(rect, 3.0) == 200               # never past the end
    assert xp_ui.bar_fill_width(rect, 0.01) == rect.h           # a sliver still shows round
    xp_ui.draw_xp_bar(surface, rect, 0.5)


# --- task 15: win screen -----------------------------------------------------------------
def _win_screen(monkeypatch, level_id=1, setup=None, **stats):
    """Draw the Win screen; return (scene, every text drawn with its rect)."""
    from vector_drift.scenes import base, win
    manager = _manager(xp_total=290)
    manager.session.level_id = level_id
    if setup:
        setup(manager)
    manager.session.stats = {"time": 1.0, "total_time": 1.0, "attempts": 1, "lives_left": 5,
                             "max_lives": 5, "fx": "1", "fy": "0", "coins_earned": 0,
                             "clear_reward": 0, **stats}
    scene = win.WinScene(manager)
    drawn = []
    real = base.draw_text

    def spy(surface, text, *args, **kwargs):
        rect = real(surface, text, *args, **kwargs)
        drawn.append((text, rect))
        return rect

    for module in (win, base, xp_ui):
        monkeypatch.setattr(module, "draw_text", spy)
    scene.draw(_screen())
    return scene, drawn


def _texts_of(drawn):
    return [text for text, _rect in drawn]


def test_the_win_screen_shows_the_xp_earned(monkeypatch):
    _scene, drawn = _win_screen(monkeypatch, xp_gained=110)
    texts = _texts_of(drawn)
    assert "XP earned" in texts and "+110" in texts


def test_a_win_without_xp_shows_plus_zero(monkeypatch):
    _scene, drawn = _win_screen(monkeypatch)                # stats from before XP existed
    assert "+0" in _texts_of(drawn)


def _custom(manager):
    from vector_drift import data
    data.register_custom_level(data.LevelSpec(id=1000, name="Mine", start=(-7.0, 0.0),
                                              target_center=(7.0, 0.0), target_radius=1.0,
                                              ship_id="ship01"))
    manager.session.custom_level_ids.add(1000)


def _community(manager):
    from vector_drift import data
    level_id = data.community_level_id("row-for-win")
    data.register_community_level(data.LevelSpec(id=level_id, name="Theirs", start=(-7.0, 0.0),
                                                 target_center=(7.0, 0.0), target_radius=1.0,
                                                 ship_id="ship01"))
    manager.session.level_id = level_id


@pytest.mark.parametrize("setup, level_id", [(_custom, 1000), (_community, None)],
                         ids=["custom", "community"])
@pytest.mark.parametrize("xp_gained", [0, 10])
def test_custom_and_community_maps_always_say_no_clear_xp(monkeypatch, setup, level_id, xp_gained):
    _scene, drawn = _win_screen(monkeypatch, level_id or 1, setup, xp_gained=xp_gained)
    texts = _texts_of(drawn)
    assert f"+{xp_gained}" in texts                         # an achievement's XP still shows
    assert "No XP for clearing custom maps" in texts
    assert "No clear reward on custom maps" in texts


@pytest.mark.parametrize("xp_gained", [0, 10])
def test_the_daily_challenge_always_says_no_clear_xp(monkeypatch, xp_gained):
    _scene, drawn = _win_screen(monkeypatch, config.DAILY_LEVEL_ID, xp_gained=xp_gained,
                                clear_reward=5, coins_earned=5)
    texts = _texts_of(drawn)
    assert f"+{xp_gained}" in texts
    assert "No XP for clearing the daily challenge" in texts


@pytest.mark.parametrize("level_id", [1, RANDOM_LEVEL_ID])
def test_campaign_and_random_clears_have_no_xp_note(monkeypatch, level_id):
    _scene, drawn = _win_screen(monkeypatch, level_id, xp_gained=100, clear_reward=5, coins_earned=5)
    assert not any("No XP" in text for text in _texts_of(drawn))


def test_the_xp_line_and_two_notes_stay_above_the_buttons(monkeypatch):
    scene, drawn = _win_screen(monkeypatch, 1000, _custom, xp_gained=0)
    lowest = max(rect.bottom for text, rect in drawn
                 if text in ("+0", "No XP for clearing custom maps", "No clear reward on custom maps"))
    for button in (scene.replay_button, scene.levels_button, scene.menu_button):
        assert lowest < button.rect.top
        assert button.rect.bottom <= config.WINDOW_H


# --- task 16: the XP bar grows on the win screen -------------------------------------------
def _states(before, after, steps=50):
    duration = xp_ui.XP_BAR_S
    return [xp_ui.xp_bar_state(before, after, duration * i / steps) for i in range(steps + 1)]


def test_the_bar_grows_from_before_to_after_inside_one_level():
    states = _states(130, 205)                              # Lv 2: 30/150 -> 105/150
    assert states[0] == (2, 30 / 150)
    assert states[-1] == (2, 105 / 150)
    fractions = [f for _level, f in states]
    assert fractions == sorted(fractions)


def test_the_bar_eases_out():
    level, fraction = xp_ui.xp_bar_state(130, 205, xp_ui.XP_BAR_S / 2)
    assert fraction > (30 + 105) / 2 / 150                 # past halfway at half time


def test_a_level_up_fills_the_bar_then_grows_from_zero():
    states = _states(230, 280)                              # Lv 2 130/150 -> Lv 3 30/200
    assert states[0] == (2, 130 / 150)
    assert states[-1] == (3, 30 / 200)
    levels_shown = [level for level, _f in states]
    assert levels_shown == sorted(levels_shown) and set(levels_shown) == {2, 3}
    assert max(f for level, f in states if level == 2) > 0.95      # it gets (almost) full
    assert min(f for level, f in states if level == 3) < 0.05      # and starts again near 0
    assert all(0.0 <= f <= 1.0 for _level, f in states)


def test_jumping_several_levels_fills_once_then_shows_the_new_level():
    states = _states(0, 2750)                               # Lv 1 -> Lv 10
    assert {level for level, _f in states} == {1, 10}
    assert states[-1] == (10, 50 / 550)


def test_no_gain_keeps_the_bar_still():
    assert set(_states(290, 290)) == {(3, 40 / 200)}


def test_after_the_time_is_up_the_bar_stays_at_the_end():
    assert xp_ui.xp_bar_state(230, 280, 10.0) == (3, 30 / 200)
    assert xp_ui.xp_bar_state(230, 280, -1.0) == (2, 130 / 150)


def test_the_win_screen_bar_starts_before_the_clear_and_ends_after_it(monkeypatch):
    from vector_drift.scenes import win
    manager = _manager(xp_total=280)
    manager.session.stats = {"xp_before": 230, "xp_gained": 50, "clear_reward": 5}
    scene = win.WinScene(manager)
    texts = _texts(xp_ui, monkeypatch)
    scene.draw(_screen())
    assert "Lv 2" in texts and "130 / 150 XP" in texts
    texts.clear()
    scene.update(xp_ui.XP_BAR_S + 0.1)
    scene.draw(_screen())
    assert "Lv 3" in texts and "30 / 200 XP" in texts


def test_the_win_screen_bar_sits_between_the_notes_and_the_buttons(monkeypatch):
    scene, drawn = _win_screen(monkeypatch, 1000, _custom, xp_gained=10, xp_before=280)
    notes_bottom = max(rect.bottom for text, rect in drawn if text.startswith("No "))
    bar = scene.xp_bar_rect
    assert bar.top > notes_bottom
    assert bar.bottom < scene.replay_button.rect.top
    numbers = next(rect for text, rect in drawn if text.endswith(" XP"))
    assert numbers.bottom < scene.replay_button.rect.top


def test_a_clear_records_the_xp_before_it():
    from tests.test_progression import _manager as game_manager, _scene, _win
    manager = game_manager()
    manager.session.xp_total = 230
    stats = _win(_scene(1, manager))
    assert stats["xp_before"] == 230
    assert manager.session.xp_total == 230 + stats["xp_gained"]
