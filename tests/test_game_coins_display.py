"""The game screen shows the coin balance on top of everything else."""

from types import SimpleNamespace

import pygame
import pytest

from vector_drift import config
from vector_drift.scenes import game as game_module
from vector_drift.scenes.base import SceneManager
from vector_drift.scenes.game import GameScene

pytestmark = pytest.mark.usefixtures("pygame_display")


def _scene(level_id, coins):
    audio = SimpleNamespace(play=lambda *a, **k: None, start_loop=lambda *a, **k: None,
                            stop_loop=lambda *a, **k: None)
    manager = SceneManager(audio)
    manager.session.level_id = level_id
    manager.session.money.add(coins)
    scene = GameScene(manager)
    manager.switch(scene)
    return scene


def _draw_and_find(scene, monkeypatch):
    calls = []
    real = game_module.draw_text

    def spy(surface, text, *args, **kwargs):
        rect = real(surface, text, *args, **kwargs)
        calls.append((text, rect))
        return rect

    monkeypatch.setattr(game_module, "draw_text", spy)
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    scene.draw(surface)
    return surface, calls


@pytest.mark.parametrize("level_id", [2, 7])
def test_coins_are_visible_in_the_plot_top_right(monkeypatch, level_id):
    scene = _scene(level_id, 12)
    surface, calls = _draw_and_find(scene, monkeypatch)
    rects = [rect for text, rect in calls if text == "Coins: 12"]
    assert len(rects) == 1
    rect = rects[0]
    assert not any(text.startswith("Money:") for text, _ in calls)

    # Inside the window, right of the left panel, in the top-right corner.
    assert surface.get_rect().contains(rect)
    assert rect.left > config.PANEL_W
    assert rect.right > config.WINDOW_W - config.px(40)
    assert rect.top < config.px(40)

    # Not painted over: some glyph pixels still have the text colour.
    area = surface.subsurface(rect)
    assert any(tuple(area.get_at((x, y)))[:3] == config.WARNING
               for x in range(rect.w) for y in range(rect.h))

    # Clear of every other label drawn this frame.
    assert not any(rect.colliderect(r) for text, r in calls if text != "Coins: 12")
