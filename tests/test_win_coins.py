"""Mission Complete shows the coins this run earned, and why there are none."""

from types import SimpleNamespace

import pygame
import pytest

from vector_drift import config
from vector_drift.image_assets import COIN_TRADE
from vector_drift.scenes import base, win
from vector_drift.scenes.base import SceneManager

pytestmark = pytest.mark.usefixtures("pygame_display")


def _shown(monkeypatch, level_id=1, **stats):
    """Draw the Win screen; return (texts drawn, coin amounts drawn with coin_2)."""
    manager = SceneManager(SimpleNamespace(play=lambda *a, **k: None))
    manager.session.level_id = level_id
    manager.session.stats = {"time": 1.0, "total_time": 1.0, "attempts": 1, "lives_left": 5,
                             "max_lives": 5, "fx": "1", "fy": "0", **stats}
    scene = win.WinScene(manager)
    texts, coins = [], []
    real_text, real_coins = win.draw_text, win.draw_coins    # both are ui.draw_text / draw_coins

    def text_spy(surface, text, *args, **kwargs):
        texts.append(text)
        return real_text(surface, text, *args, **kwargs)

    def coins_spy(surface, amount, *args, **kwargs):
        rect = real_coins(surface, amount, *args, **kwargs)
        if kwargs.get("icon", COIN_TRADE) == COIN_TRADE:
            coins.append((amount, rect))
        return rect

    monkeypatch.setattr(win, "draw_text", text_spy)
    monkeypatch.setattr(base, "draw_text", text_spy)        # the card's stat lines
    monkeypatch.setattr(win, "draw_coins", coins_spy)
    scene.draw(pygame.Surface((config.WINDOW_W, config.WINDOW_H)))
    return scene, texts, coins


def test_coins_earned_row_shows_coin_2_and_the_amount(monkeypatch):
    _scene, texts, coins = _shown(monkeypatch, coins_earned=6, clear_reward=5)
    assert "Coins earned" in texts
    assert [amount for amount, _ in coins] == ["+6"]


def test_solution_used_explains_why_there_are_no_coins(monkeypatch):
    _scene, texts, coins = _shown(monkeypatch, coins_earned=0, clear_reward=0,
                                  solution_used=True)
    assert [amount for amount, _ in coins] == ["+0"]
    assert "Solution used · not counted as a best time" in texts
    assert any("no coins" in t for t in texts)


@pytest.mark.parametrize("level_id, where", [(1, "level"), (8, "map")])
def test_reward_already_collected_is_explained(monkeypatch, level_id, where):
    _scene, texts, _coins = _shown(monkeypatch, level_id, coins_earned=0, clear_reward=0)
    assert f"Clear reward already collected for this {where}" in texts


def test_a_paid_clear_needs_no_note(monkeypatch):
    _scene, texts, _coins = _shown(monkeypatch, coins_earned=5, clear_reward=5)
    assert not any("already collected" in t or "no coins" in t for t in texts)


def test_coins_row_and_notes_stay_above_the_buttons(monkeypatch):
    scene, _texts, coins = _shown(monkeypatch, coins_earned=0, clear_reward=0,
                                  solution_used=True)
    rect = coins[0][1]
    assert rect.bottom < scene.replay_button.rect.top
