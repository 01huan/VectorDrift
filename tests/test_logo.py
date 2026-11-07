"""The game logo replaces the "VECTOR DRIFT" title text; the menu tagline."""

from types import SimpleNamespace

import pygame
import pytest

from vector_drift import config, image_assets, sprites
from vector_drift.scenes import game as game_module
from vector_drift.scenes import menu as menu_module
from vector_drift.scenes.base import SceneManager
from vector_drift.scenes.game import GameScene
from vector_drift.scenes.menu import MenuScene

pytestmark = pytest.mark.usefixtures("pygame_display")
LOGO_PATH = image_assets.IMAGES_DIR / image_assets.get_spec(image_assets.LOGO).path


@pytest.fixture(autouse=True)
def fresh_images():
    image_assets.clear_cache()
    yield
    image_assets.clear_cache()


@pytest.fixture
def no_logo(monkeypatch):
    monkeypatch.setitem(image_assets._SPECS, image_assets.LOGO,
                        image_assets.AssetSpec(image_assets.LOGO, image_assets.Path("ui/missing.png")))


def _manager():
    audio = SimpleNamespace(play=lambda *a, **k: None, start_loop=lambda *a, **k: None,
                            stop_loop=lambda *a, **k: None)
    return SceneManager(audio)


def _texts(module, monkeypatch):
    texts = []
    real = module.draw_text
    monkeypatch.setattr(module, "draw_text",
                        lambda surface, text, *a, **k: (texts.append(text), real(surface, text, *a, **k))[1])
    return texts


def _logo_calls(monkeypatch):
    calls = []
    real = sprites.draw_logo
    monkeypatch.setattr(sprites, "draw_logo",
                        lambda surface, center, width: (calls.append((center, width)),
                                                        real(surface, center, width))[1])
    return calls


def test_logo_picture_is_small_and_transparent():
    assert LOGO_PATH.exists()
    assert LOGO_PATH.stat().st_size <= 200 * 1024
    img = pygame.image.load(str(LOGO_PATH)).convert_alpha()
    assert img.get_width() == 1200
    assert img.get_at((0, 0)).a == 0                       # see-through corners


def test_draw_logo_keeps_the_picture_aspect():
    surface = pygame.Surface((800, 400), pygame.SRCALPHA)
    assert sprites.draw_logo(surface, (400, 200), 600)
    w, h = image_assets.source_size(image_assets.LOGO)
    img = image_assets.load_image(image_assets.LOGO, size_px=(600, round(600 * h / w)))
    assert img is not None and img.get_width() == 600
    assert surface.get_bounding_rect().width > 500


def test_draw_logo_reports_a_missing_picture(no_logo):
    assert not sprites.draw_logo(pygame.Surface((100, 100)), (50, 50), 80)


def test_menu_shows_the_logo_and_the_new_tagline(monkeypatch):
    texts, calls = _texts(menu_module, monkeypatch), _logo_calls(monkeypatch)
    MenuScene(_manager()).draw(pygame.Surface((config.WINDOW_W, config.WINDOW_H)))

    assert len(calls) == 1
    assert "Shape the field, guide the ship" in texts
    assert "VECTOR DRIFT" not in texts
    assert "Design a force field. Let physics fly the ship." not in texts


def test_menu_falls_back_to_the_title_text(no_logo, monkeypatch):
    texts = _texts(menu_module, monkeypatch)
    MenuScene(_manager()).draw(pygame.Surface((config.WINDOW_W, config.WINDOW_H)))
    assert "VECTOR DRIFT" in texts
    assert "Shape the field, guide the ship" in texts


def _game():
    manager = _manager()
    manager.session.level_id = 1
    scene = GameScene(manager)
    manager.switch(scene)
    return scene


def test_level_panel_shows_the_logo(monkeypatch):
    texts, calls = _texts(game_module, monkeypatch), _logo_calls(monkeypatch)
    _game().draw(pygame.Surface((config.WINDOW_W, config.WINDOW_H)))
    assert len(calls) == 1
    assert "VECTOR DRIFT" not in texts


def test_level_panel_falls_back_to_the_title_text(no_logo, monkeypatch):
    texts = _texts(game_module, monkeypatch)
    _game().draw(pygame.Surface((config.WINDOW_W, config.WINDOW_H)))
    assert "VECTOR DRIFT" in texts
