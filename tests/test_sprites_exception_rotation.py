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


def test_rotating_paths_image_present(monkeypatch):
    monkeypatch.setattr(pygame.transform, "rotozoom", _boom)
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    ship = SHIPS["ship01"]
    center = (100, 100)
    sprites.draw_ship(surface, center, 0.25, 30, ship)
    sprites.draw_ship(surface, center, 0.25, 30, ship, grey=True)
    sprites.draw_ship_icon(surface, center, 30, ship, alive=True)
    sprites.draw_ship_icon(surface, center, 30, ship, alive=False)
    trail = sprites.TrailLayer((10, 10))
    trail.extend([(1.0, 1.0), (2.0, 2.0)])
    trail.draw(surface, (0, 0))


def test_rotating_paths_image_missing(monkeypatch, tmp_path):
    _missing_images(monkeypatch, tmp_path)
    monkeypatch.setattr(pygame.transform, "rotozoom", _boom)
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    ship = SHIPS["ship01"]
    center = (100, 100)
    sprites.draw_ship(surface, center, 0.25, 30, ship)
    sprites.draw_ship(surface, center, 0.25, 30, ship, grey=True)
    sprites.draw_ship_icon(surface, center, 30, ship, alive=True)
    sprites.draw_ship_icon(surface, center, 30, ship, alive=False)
    sprites.draw_checkpoint_life(surface, 100, 100, 20, ship, fade=0.5)
    trail = sprites.TrailLayer((10, 10))
    trail.extend([(1.0, 1.0), (2.0, 2.0)])
    trail.draw(surface, (0, 0))


def test_bad_surface_get_size():
    class Bad:
        def get_size(self):
            raise pygame.error("boom")

        def get_rect(self, **k):
            raise pygame.error("boom")

    ship = SHIPS["ship01"]
    class SurfaceStub:
        def get_size(self):
            raise pygame.error("boom")
        def blit(self, *a, **k):
            raise pygame.error("boom")
        def get_rect(self, **k):
            raise pygame.error("boom")
    stub = SurfaceStub()
    sprites.draw_ship(stub, (10, 10), 0.0, 10, ship)
    sprites.draw_checkpoint(stub, (10, 10), 20, 1.0, ship)
    sprites.draw_checkpoint_life(stub, (10, 10), 20, 1.0, ship, fade=0.5)
    sprites.draw_target(stub, (10, 10), 10, 1.0)
    sprites.draw_shield(stub, (10, 10), 10, 1.0)
    sprites.draw_pickup(stub, (10, 10), 10, 1.0, kind="shield")
    sprites.draw_obstacle(stub, (10, 10), 10, 1.0)
    sprites.draw_start_marker(stub, (10, 10), 10, 1.0)
    sprites.draw_hole(stub, (10, 10), 10, 1.0)
    sprites.draw_black_hole(stub, (10, 10), 10, 1.0)
    sprites.draw_white_hole(stub, (10, 10), 10, 1.0)
