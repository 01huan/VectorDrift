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


def test_target_flash_exception():
    class _Surface:
        def __init__(self):
            self.s = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
            self.n = 0

        def get_size(self):
            return self.s.get_size()

        def blit(self, *a, **k):
            self.n += 1
            if self.n >= 3:
                raise pygame.error("boom")
            return self.s.blit(*a, **k)

        def get_rect(self, **k):
            return self.s.get_rect(**k)

    sprites.draw_target(_Surface(), (100, 100), 20, 0.0, flash=1.0)


def test_logo_returns_false_when_source_known_image_missing(monkeypatch):
    monkeypatch.setattr(sprites, "source_size", lambda key: (10, 10))
    monkeypatch.setattr(sprites, "load_image", lambda *a, **k: None)
    surface = pygame.Surface((100, 100), pygame.SRCALPHA)
    assert not sprites.draw_logo(surface, (50, 50), 80)


def test_obstacle_picture_exception(monkeypatch):
    monkeypatch.setattr(sprites, "_obstacle_picture", lambda *a, **k: (_ for _ in ()).throw(pygame.error("boom")))
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    sprites.draw_obstacle(surface, (100, 100), 20, 1.0, kind="bumper", seed=1)


def test_pickup_unknown_painter(monkeypatch):
    monkeypatch.setattr(sprites, "PICKUP_RENDERERS", {"shockwave": _boom})
    import tempfile, pathlib
    d = pathlib.Path(tempfile.mkdtemp())
    monkeypatch.setattr(image_assets, "IMAGES_DIR", d)
    image_assets.clear_cache()
    sprites._cache.clear()
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    sprites.draw_pickup(surface, (100, 100), 20, 1.0, kind="shockwave")
    monkeypatch.setattr(sprites, "PICKUP_RENDERERS", {
        "shockwave": _paint_shockwave_placeholder if False else sprites.PICKUP_RENDERERS.get("shockwave", lambda *a, **k: None)
    })


def test_start_marker_and_draw_vector_exceptions(monkeypatch):
    monkeypatch.setattr(pygame.transform, "rotozoom", _boom)
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    sprites.draw_start_marker(surface, (100, 100), 20, 1.0)

    monkeypatch.setattr(pygame.transform, "rotozoom", lambda *a, **k: pygame.Surface((4, 4)))
    monkeypatch.setattr(sprites, "draw_smooth_arrow", _boom)
    sprites.draw_vector(surface, (10, 10), (1.0, 1.0), (255, 0, 0))


def test_draw_hole_exception(monkeypatch):
    monkeypatch.setattr(image_assets, "load_image", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    sprites.draw_hole(surface, (100, 100), 20, 1.0, kind="black", pair_index=1)


def test_trail_exception_lines(monkeypatch):
    # 845: set_alpha raises during draw recovery
    class _FakeLayer:
        def set_alpha(self, *a, **k):
            raise pygame.error("boom")

    trail = sprites.TrailLayer((10, 10))
    trail.extend([(1.0, 1.0), (2.0, 2.0)])
    trail.layer = _FakeLayer()
    trail.draw(pygame.Surface((40, 40)), (0, 0))

    # 861: non-finite self.last reset
    trail2 = sprites.TrailLayer((10, 10))
    trail2.last = (float("inf"), 0.0)
    trail2.extend([(1.0, 1.0)])

    # 872: giant jump returns early
    trail3 = sprites.TrailLayer((10, 10))
    trail3.last = (0.0, 0.0)
    trail3.extend([(100000.0, 100000.0)])

    # 882: get_size fails
    class _BadLayer:
        def get_size(self):
            raise pygame.error("boom")

    trail4 = sprites.TrailLayer((10, 10))
    trail4.layer = _BadLayer()
    trail4.extend([(1.0, 1.0), (2.0, 2.0)])

    # 895 / 915: skip outside segments and empty dirty
    trail5 = sprites.TrailLayer((10, 10))
    trail5.extend([(15.0, 15.0), (16.0, 16.0)])

    # 900: draw raises
    monkeypatch.setattr(pygame.draw, "line", _boom)
    trail6 = sprites.TrailLayer((10, 10))
    trail6.extend([(1.0, 1.0), (2.0, 2.0)])
    monkeypatch.setattr(pygame.draw, "line", pygame.draw.line)

    # 920: smoothscale raises
    monkeypatch.setattr(pygame.transform, "smoothscale", _boom)
    trail7 = sprites.TrailLayer((10, 10))
    trail7.extend([(1.0, 1.0), (2.0, 2.0)])
    monkeypatch.setattr(pygame.transform, "smoothscale", pygame.transform.smoothscale)
    trail7.clear()
