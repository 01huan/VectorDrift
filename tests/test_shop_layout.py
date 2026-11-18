"""Shop layout scales once with UI_SCALE, and Back never covers the Money label."""

from types import SimpleNamespace

import pygame
import pytest

from vector_drift import config, ui
from vector_drift.image_assets import COIN_BALANCE
from vector_drift.scenes import shop as shop_scene_module
from vector_drift.scenes.base import SceneManager
from vector_drift.scenes.shop import ShopScene

pytestmark = pytest.mark.usefixtures("pygame_display")


@pytest.fixture(params=[1.0, 1.5])
def scale(request, monkeypatch):
    s = request.param
    monkeypatch.setattr(config, "UI_SCALE", s)
    monkeypatch.setattr(config, "WINDOW_W", config.px(config.BASE_W))
    monkeypatch.setattr(config, "WINDOW_H", config.px(config.BASE_H))
    monkeypatch.setattr(ui, "_font_cache", {})     # fonts are sized for the current scale
    return s


def _scene():
    manager = SceneManager(SimpleNamespace(play=lambda *a, **k: None))
    scene = ShopScene(manager)
    manager.switch(scene)
    return scene


def _money_rect(scene, monkeypatch):
    rects = []
    real = shop_scene_module.draw_coins

    def spy(surface, amount, *args, **kwargs):
        rect = real(surface, amount, *args, **kwargs)
        if kwargs.get("icon") == COIN_BALANCE:
            rects.append(rect)
        return rect

    monkeypatch.setattr(shop_scene_module, "draw_coins", spy)
    scene.draw(pygame.Surface((config.WINDOW_W, config.WINDOW_H)))
    assert len(rects) == 1
    return rects[0]


def test_cards_and_buttons_stay_on_screen(scale):
    scene = _scene()
    screen = pygame.Rect(0, 0, config.WINDOW_W, config.WINDOW_H)
    assert scene.cards
    for _item, rect in scene.cards:
        assert screen.contains(rect)
    for _item, btn in scene.buy_buttons:
        assert screen.contains(btn.rect)
    assert screen.contains(scene.back_button.rect)


def test_cards_are_centred_and_scale_once(scale):
    scene = _scene()
    rects = [rect for _item, rect in scene.cards]
    left = min(r.left for r in rects)
    right = max(r.right for r in rects)
    assert abs((left + right) / 2 - config.WINDOW_W / 2) <= 2
    assert rects[0].top == config.px(shop_scene_module.GRID_TOP)
    assert rects[0].size == (config.px(shop_scene_module.CARD_W), config.px(scene.card_h))


def test_seven_abilities_in_four_columns_on_one_page(scale):
    scene = _scene()
    rects = [rect for _item, rect in scene.cards]
    assert len(rects) == 7
    rows = sorted({r.top for r in rects})
    assert [sum(r.top == top for r in rects) for top in rows] == [4, 3]
    second = [r for r in rects if r.top == rows[1]]
    # The row of three is centred too.
    mid = (min(r.left for r in second) + max(r.right for r in second)) / 2
    assert abs(mid - config.WINDOW_W / 2) <= 2
    assert scene.page_count == 1
    assert not hasattr(scene, "next_button") or scene.next_button is None


def test_card_contents_fit_inside_the_card(scale):
    scene = _scene()
    for item, rect in scene.cards:
        # Every description line fits the card's text width: nothing is cut.
        lines = scene.desc_lines[item.id]
        assert " ".join(lines) == item.description
        width = rect.w - 2 * config.px(shop_scene_module.CARD_PAD)
        font = ui.get_font(shop_scene_module.DESC_SIZE)
        assert all(font.size(line)[0] <= width for line in lines)
        last = rect.y + config.px(shop_scene_module.CARD_PAD + shop_scene_module.ICON_BOX + 12
                                  + len(lines) * shop_scene_module.DESC_LINE_H)
        price_top = rect.bottom - config.px(shop_scene_module.CARD_PAD + shop_scene_module.BUY_H
                                            + 10 + shop_scene_module.PRICE_ROW_H)
        assert last <= price_top
    for item, btn in scene.buy_buttons:
        card = dict((i.id, r) for i, r in scene.cards)[item.id]
        assert card.contains(btn.rect)


def test_back_does_not_cover_money_or_cards(scale, monkeypatch):
    scene = _scene()
    back = scene.back_button.rect
    assert not back.colliderect(_money_rect(scene, monkeypatch))
    for _item, rect in scene.cards:
        assert not back.colliderect(rect)
