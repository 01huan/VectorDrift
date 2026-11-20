"""The player level on screen: level select row, win screen bar, level-up popup."""

from types import SimpleNamespace

import pygame
import pytest

from vector_drift import config
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
