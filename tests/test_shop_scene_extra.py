import pygame
import pytest

from types import SimpleNamespace

from vector_drift import config
from vector_drift.scenes.base import SceneManager
from vector_drift.scenes.shop import ShopScene

pytestmark = pytest.mark.usefixtures("pygame_display")


def _manager():
    audio = SimpleNamespace(play=lambda *a, **k: None, toggle_mute=lambda: None, start_loop=lambda *a, **k: None, stop_loop=lambda *a, **k: None)
    mgr = SceneManager(audio)
    mgr.session.money.amount = 1000
    return mgr


def test_shop_scene_purchase_flow():
    mgr = _manager()
    scene = ShopScene(mgr)
    mgr.switch(scene)
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    scene.draw(surface)
    if scene.buy_buttons:
        btn = scene.buy_buttons[0][1]
        btn.enabled = True
        scene.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=btn.rect.center))
        scene.draw(surface)
    # escape
    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))


def test_buying_adds_a_charge_and_the_card_shows_it(monkeypatch):
    from vector_drift.scenes import shop as shop_scene_module

    monkeypatch.setattr("vector_drift.account.integration.save_progress", lambda *a, **k: None)
    mgr = _manager()
    scene = ShopScene(mgr)
    mgr.switch(scene)
    item, btn = next((i, b) for i, b in scene.buy_buttons if i.id == "ability_boost")
    before = int(mgr.session.money)
    scene.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=btn.rect.center))
    scene.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=btn.rect.center))
    assert mgr.session.ability_charges["ability_boost"] == 2
    assert int(mgr.session.money) == before - 2 * item.price
    assert scene.owned_count(item) == 2

    texts = []
    real = shop_scene_module.draw_text

    def spy(surface, text, *a, **k):
        texts.append(text)
        return real(surface, text, *a, **k)

    monkeypatch.setattr(shop_scene_module, "draw_text", spy)
    scene.draw(pygame.Surface((config.WINDOW_W, config.WINDOW_H)))
    assert "Owned ×2" in texts
    assert "Owned ×0" in texts
    assert shop_scene_module.SUBTITLE in texts
    assert shop_scene_module.SUBTITLE == "Abilities are one-use charges. Press the key during a flight."
