"""Coin pictures stand in for the words: coin_1 marks the player's balance."""

from types import SimpleNamespace

import pygame
import pytest

from vector_drift import config, ui
from vector_drift.image_assets import COIN_BALANCE, COIN_TRADE
from vector_drift.scenes import account, fail, levels, shop, win
from vector_drift.scenes.base import SceneManager

pytestmark = pytest.mark.usefixtures("pygame_display")


def _manager(coins=7):
    audio = SimpleNamespace(play=lambda *a, **k: None, start_loop=lambda *a, **k: None,
                            stop_loop=lambda *a, **k: None)
    manager = SceneManager(audio)
    manager.session.money.add(coins)
    return manager


def _draw(scene, module, monkeypatch):
    """Draw ``scene``; return (every text drawn, every icon row drawn)."""
    texts, rows = [], []
    real_text, real_row = module.draw_text, ui.draw_icon_row

    def text_spy(surface, text, *args, **kwargs):
        texts.append(text)
        return real_text(surface, text, *args, **kwargs)

    def row_spy(surface, parts, *args, **kwargs):
        rows.append(list(parts))
        return real_row(surface, parts, *args, **kwargs)

    monkeypatch.setattr(module, "draw_text", text_spy)
    monkeypatch.setattr(ui, "draw_icon_row", row_spy)              # behind draw_coins
    if hasattr(module, "draw_icon_row"):
        monkeypatch.setattr(module, "draw_icon_row", row_spy)
    scene.draw(pygame.Surface((config.WINDOW_W, config.WINDOW_H)))
    return texts, rows


SCENES = [
    (levels, lambda m: levels.LevelSelectScene(m)),
    (shop, lambda m: shop.ShopScene(m)),
    (win, lambda m: win.WinScene(m)),
    (fail, lambda m: fail.FailScene(m)),
]


@pytest.mark.parametrize("module, make", SCENES, ids=["levels", "shop", "win", "fail"])
def test_balance_corner_shows_coin_1_and_the_amount(module, make, monkeypatch):
    manager = _manager(7)
    texts, rows = _draw(make(manager), module, monkeypatch)
    assert [COIN_BALANCE, (7, config.TEXT)] in rows
    assert not any("Money" in t or "Coins:" in t for t in texts)


def test_account_screen_shows_coin_1_instead_of_money(monkeypatch):
    manager = _manager(7)
    texts, rows = _draw(account.AccountScene(manager), account, monkeypatch)
    assert [COIN_BALANCE] in rows
    assert "7" in texts
    assert "Money" not in texts


def test_icon_row_draws_the_picture_at_text_height():
    surface = pygame.Surface((300, 60), pygame.SRCALPHA)
    rect = ui.draw_coins(surface, 12, (10, 10), 16, icon=COIN_BALANCE)
    font_h = ui.get_font(16, "bold").get_height()
    assert rect.h == font_h
    assert rect.w > font_h                          # the picture plus the number
    assert surface.get_at((10 + font_h // 2, 10 + font_h // 2)).a > 0


def test_missing_coin_picture_falls_back_to_a_gold_disc(monkeypatch, tmp_path):
    from vector_drift import image_assets
    monkeypatch.setattr(image_assets, "IMAGES_DIR", tmp_path)
    image_assets.clear_cache()
    try:
        surface = pygame.Surface((300, 60), pygame.SRCALPHA)
        rect = ui.draw_coins(surface, 3, (0, 0), 16, icon=COIN_TRADE)
        side = rect.h
        assert tuple(surface.get_at((side // 2, side // 2)))[:3] == ui.COIN_GOLD
    finally:
        image_assets.clear_cache()
