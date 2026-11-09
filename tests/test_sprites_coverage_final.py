import tempfile
import pathlib
import pygame
import pytest

from vector_drift import config, image_assets, sprites

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


def test_start_marker_image_path_exception(monkeypatch):
    monkeypatch.setattr(sprites, "load_image", lambda key, *a, **k: (
        pygame.Surface((8, 8)) if key == "ui.start_marker" else image_assets.load_image(key, *a, **k)
    ))
    monkeypatch.setattr(pygame.transform, "rotozoom", _boom)
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    sprites.draw_start_marker(surface, (100, 100), 20, 1.0)


def test_obstacle_fallback_exceptions(monkeypatch):
    d = pathlib.Path(tempfile.mkdtemp())
    _missing_images(monkeypatch, d)
    # 525: fallback painter raises
    monkeypatch.setattr(sprites, "OBSTACLE_RENDERERS", {"bumper": _boom})
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    sprites.draw_obstacle(surface, (100, 100), 20, 1.0, kind="bumper", seed=1)

    # 542: non-finite cull branch
    sprites.draw_obstacle(surface, (float("inf"), 0.0), 20, 1.0, kind="bumper", seed=1)

    # 547: get_size raises while caching prop
    class _BadSurface:
        def get_size(self):
            raise pygame.error("boom")
    sprites.draw_obstacle(_BadSurface(), (100, 100), 20, 1.0, kind="bumper", seed=1)


def test_paint_cached_prop_lines(monkeypatch):
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    sprites._paint_cached_prop(surface, (float("inf"), 0.0), 20, 1.0, "x", lambda *a, **k: None)

    class _Bad:
        def get_size(self):
            raise pygame.error("boom")

    sprites._paint_cached_prop(_Bad(), (10.0, 10.0), 20, 1.0, "x", lambda *a, **k: None)


def test_start_marker_image_success_and_exception(monkeypatch):
    monkeypatch.setattr(sprites, "load_image", lambda key, *a, **k: (
        pygame.Surface((8, 8)) if key == "ui.start_marker" else image_assets.load_image(key, *a, **k)
    ))
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    sprites.draw_start_marker(surface, (100, 100), 20, 1.0)
    monkeypatch.setattr(pygame.transform, "rotozoom", _boom)
    sprites.draw_start_marker(surface, (100, 100), 20, 1.0)
def test_spr_trail_extra_lines(monkeypatch):
    # 863: no clean points
    trail = sprites.TrailLayer((10, 10))
    trail.extend([(float("nan"), 0.0)])

    # 874: parser exception
    trail2 = sprites.TrailLayer((10, 10))
    try:
        trail2.extend([None])
    except Exception:
        pass

    # 912: margin calculation exception
    class _BadRectLayer:
        def __init__(self, size):
            self.size = size

        def get_size(self):
            return self.size

        def get_rect(self):
            raise ValueError("boom")

    trail3 = sprites.TrailLayer((10, 10))
    trail3.extend([(1.0, 1.0), (2.0, 2.0)])
    trail3.layer = _BadRectLayer(trail3.layer.get_size() if hasattr(trail3, "_orig") else (10, 10))
    trail3.extend([(3.0, 3.0), (4.0, 4.0)])
    del trail3

    # 920: smoothscale exception
    monkeypatch.setattr(pygame.transform, "smoothscale", _boom)
    trail4 = sprites.TrailLayer((10, 10))
    trail4.extend([(1.0, 1.0), (2.0, 2.0)])
    monkeypatch.setattr(pygame.transform, "smoothscale", pygame.transform.smoothscale)