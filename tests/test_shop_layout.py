"""Shop layout scales once with UI_SCALE, and Back never covers the Money label."""

from types import SimpleNamespace

import pygame
import pytest

from vector_drift import config, ui
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
    real = shop_scene_module.draw_text

    def spy(surface, text, *args, **kwargs):
        rect = real(surface, text, *args, **kwargs)
        if text.startswith("Money:"):
            rects.append(rect)
        return rect

    monkeypatch.setattr(shop_scene_module, "draw_text", spy)
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
    assert rects[0].top == config.px(150)
    assert rects[0].size == (config.px(260), config.px(180))


def test_back_does_not_cover_money_or_cards(scale, monkeypatch):
    scene = _scene()
    back = scene.back_button.rect
    assert not back.colliderect(_money_rect(scene, monkeypatch))
    for _item, rect in scene.cards:
        assert not back.colliderect(rect)
