import pygame
import pytest

from vector_drift import config, image_assets, sprites
from vector_drift.data import SHIPS

pytestmark = pytest.mark.usefixtures("pygame_display")


@pytest.fixture(autouse=True)
def _clear_caches():
    sprites._cache.clear()
    image_assets.clear_cache()
    yield
    sprites._cache.clear()
    image_assets.clear_cache()


def _missing_images(monkeypatch, tmp_path):
    monkeypatch.setattr(image_assets, "IMAGES_DIR", tmp_path)
    image_assets.clear_cache()
    sprites._cache.clear()


def _boom(*a, **k):
    raise pygame.error("boom")


def test_blit_paths_image_present(monkeypatch):
    class _surface:
        def get_size(self):
            return (config.WINDOW_W, config.WINDOW_H)
        def blit(self, *a, **k):
            raise pygame.error("boom")
    surface = _surface()
    ship = SHIPS["ship01"]
    center = (100, 100)
    sprites.draw_ship(surface, center, 0.25, 30, ship)
    sprites.draw_ship(surface, center, 0.25, 30, ship, grey=True)
    sprites.draw_ship_icon(surface, center, 30, ship, alive=True)
    sprites.draw_ship_icon(surface, center, 30, ship, alive=False)
    sprites.draw_target(surface, center, 20, 1.0, flash=1.0)
    sprites.draw_shield(surface, center, 20, 1.0)
    for kind in ("shockwave", "extratime", "shield", "life", "money", "unbound"):
        sprites.draw_pickup(surface, center, 16, 1.0, kind=kind)
    for kind in ("bumper", "rock", "glow", "unknown"):
        sprites.draw_obstacle(surface, center, 20, 1.0, kind=kind, seed=1)
    sprites.draw_start_marker(surface, center, 20, 1.0)
    for kind in ("black", "white"):
        sprites.draw_hole(surface, center, 20, 1.5, kind=kind, pair_index=2)
    sprites.draw_black_hole(surface, center, 20, 1.0)
    sprites.draw_white_hole(surface, center, 20, 1.0)
    sprites.draw_checkpoint(surface, center, 20, 1.0, ship)
    sprites.draw_checkpoint_life(surface, center, 20, 1.0, ship, fade=0.5)
    sprites.draw_logo(surface, (50, 50), 80)
    trail = sprites.TrailLayer((10, 10))
    trail.extend([(1.0, 1.0), (2.0, 2.0)])
    trail.draw(surface, (0, 0))


def test_blit_paths_image_missing(monkeypatch, tmp_path):
    _missing_images(monkeypatch, tmp_path)
    class _surface:
        def get_size(self):
            return (config.WINDOW_W, config.WINDOW_H)
        def blit(self, *a, **k):
            raise pygame.error("boom")
    surface = _surface()
    ship = SHIPS["ship01"]
    center = (100, 100)
    sprites.draw_ship(surface, center, 0.25, 30, ship)
    sprites.draw_ship(surface, center, 0.25, 30, ship, grey=True)
    sprites.draw_ship_icon(surface, center, 30, ship, alive=True)
    sprites.draw_ship_icon(surface, center, 30, ship, alive=False)
    sprites.draw_pickup(surface, center, 16, 1.0, kind="unbound")
    for kind in ("bumper", "rock", "unknown"):
        sprites.draw_obstacle(surface, center, 20, 1.0, kind=kind, seed=1)
    sprites.draw_start_marker(surface, center, 20, 1.0)
    for kind in ("black", "white"):
        sprites.draw_hole(surface, center, 20, 1.5, kind=kind, pair_index=2)
    sprites.draw_checkpoint(surface, center, 20, 1.0, ship)
    sprites.draw_checkpoint_life(surface, center, 20, 1.0, ship, fade=0.5)
