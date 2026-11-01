"""Shop cards show each price with coin_2: white, or red when it is out of reach."""

from types import SimpleNamespace

import pygame
import pytest

from vector_drift import config, ui
from vector_drift.image_assets import COIN_TRADE
from vector_drift.scenes import shop as shop_scene_module
from vector_drift.scenes.base import SceneManager
from vector_drift.scenes.shop import ShopScene

pytestmark = pytest.mark.usefixtures("pygame_display")


def _price_rows(coins, monkeypatch):
    """Draw the shop; return the scene and {price: colours it was drawn in}."""
    manager = SceneManager(SimpleNamespace(play=lambda *a, **k: None))
    manager.session.money.add(coins)
    scene = ShopScene(manager)
    manager.switch(scene)
    rows = []
    real = ui.draw_icon_row

    def spy(surface, parts, *a, **k):
        rows.append(list(parts))
        return real(surface, parts, *a, **k)

    monkeypatch.setattr(ui, "draw_icon_row", spy)
    monkeypatch.setattr(shop_scene_module, "draw_icon_row", spy)
    scene.draw(pygame.Surface((config.WINDOW_W, config.WINDOW_H)))
    prices = {}
    for parts in rows:
        if parts[0] == ("Price", config.TEXT_DIM) and parts[1] == COIN_TRADE:
            prices.setdefault(parts[2][0], set()).add(parts[2][1])
    return scene, prices


def test_prices_are_white_when_affordable(monkeypatch):
    scene, prices = _price_rows(10 ** 6, monkeypatch)
    assert {item.price for item, _ in scene.cards} == set(prices)
    assert all(colours == {config.TEXT} for colours in prices.values())


def test_unowned_items_out_of_reach_are_red(monkeypatch):
    scene, prices = _price_rows(0, monkeypatch)
    for item, _rect in scene.cards:
        expected = config.TEXT if item.owned(scene.session) or item.price == 0 else config.DANGER
        assert expected in prices[item.price]
