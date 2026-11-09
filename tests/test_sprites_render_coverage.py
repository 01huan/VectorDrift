import os
import pathlib

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


def test_fallback_ship_and_icon_paths(monkeypatch, tmp_path):
    _missing_images(monkeypatch, tmp_path)
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    center = (100, 100)
    ship = SHIPS["ship01"]
    for grey in (False, True):
        sprites.draw_ship(surface, center, 0.0, 20, ship, grey=grey)
        sprites.draw_ship(surface, center, 0.25, 64, ship, grey=grey)
        sprites.draw_ship(surface, (1e9, 1e9), 0.0, 10, ship)  # cull
    sprites.draw_ship(surface, None, 0.0, 10, ship)  # invalid center
    sprites.draw_ship(surface, (10, 10), float("inf"), 10, ship)
    for alive in (True, False):
        sprites.draw_ship_icon(surface, center, 20, ship, alive=alive)
        sprites.ship_icon_surface(ship, 20, alive=alive)
    sprites.draw_ship_icon(surface, None, 20, ship)  # exception branch


def test_fallback_target_planet(monkeypatch, tmp_path):
    _missing_images(monkeypatch, tmp_path)
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    center = (100, 100)
    for radius in (0, 20, 40):
        for flash in (0.0, 0.5, 1.0):
            sprites.draw_target(surface, center, radius, 1.0, flash=flash)
    sprites.draw_target(surface, None, 20, 1.0)
    sprites.draw_target(surface, (10, 10), 0, 1.0)


def test_fallback_shield(monkeypatch, tmp_path):
    _missing_images(monkeypatch, tmp_path)
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    center = (100, 100)
    sprites.draw_shield(surface, center, 20, 1.0)
    sprites.draw_shield(surface, (1.0, 0.0), 20, 1.0)
    sprites.draw_shield(surface, None, 20, 1.0)


def test_fallback_pickups_all_kinds(monkeypatch, tmp_path):
    _missing_images(monkeypatch, tmp_path)
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    center = (100, 100)
    kinds = ("shockwave", "extratime", "shield", "life", "money", "unbound")
    for kind in kinds:
        for t in (0.0, 1.0, 2.5, 3.5, 5.0):
            sprites.draw_pickup(surface, center, 16, t, kind=kind)
    sprites.draw_pickup(surface, None, 16, 1.0, kind="shockwave")
    sprites.draw_pickup(surface, (10, 10), 0, 1.0, kind="bogus")
    sprites.draw_pickup(surface, (1e9, 1e9), 16, 1.0, kind="shield")  # cull


def test_fallback_obstacles(monkeypatch, tmp_path):
    target = (tmp_path / "does-not-exist")
    _missing_images(monkeypatch, tmp_path)
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    center = (100, 100)
    for kind in ("bumper", "rock", "unknown"):
        for seed in (0, 1, 2, 42):
            sprites.draw_obstacle(surface, center, 20, 1.0, kind=kind, seed=seed)
    sprites.draw_obstacle(surface, None, 20, 1.0)
    sprites.draw_obstacle(surface, (10, 10), 0, 1.0, kind="unknown", seed=1)


def test_fallback_start_marker(monkeypatch, tmp_path):
    _missing_images(monkeypatch, tmp_path)
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    sprites.draw_start_marker(surface, (100, 100), 20, 1.0)
    sprites.draw_start_marker(surface, None, 20, 1.0)
    sprites.draw_start_marker(surface, (10, 10), 0, 2.0)


def test_fallback_holes(monkeypatch, tmp_path):
    _missing_images(monkeypatch, tmp_path)
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    for kind in ("black", "white"):
        for pair in (1, 2, 5, 10, 11):
            sprites.draw_hole(surface, (100 + pair * 5, 100), 20, 1.5, kind=kind, pair_index=pair)
    sprites.draw_hole(surface, None, 20, 1.0)
    sprites.draw_hole(surface, (10, 10), 0, 1.0, kind="white", pair_index=99)
    sprites.draw_black_hole(surface, (200, 200), 10, 1.0)
    sprites.draw_white_hole(surface, (250, 250), 10, 1.0)
    sprites.draw_black_hole(surface, None, 10, 1.0)
    sprites.draw_white_hole(surface, None, 10, 1.0)


def test_fallback_logo(monkeypatch, tmp_path):
    _missing_images(monkeypatch, tmp_path)
    surface = pygame.Surface((100, 100), pygame.SRCALPHA)
    assert not sprites.draw_logo(surface, (50, 50), 80)


def test_fallback_checkpoint(monkeypatch, tmp_path):
    _missing_images(monkeypatch, tmp_path)
    surface = pygame.Surface((200, 200), pygame.SRCALPHA)
    sprites.draw_checkpoint(surface, 10, 100, 10, True)
    sprites.draw_checkpoint(surface, 50, 100, 20, False)
    sprites.draw_checkpoint_life(surface, 10, 10, 8, False)


def test_fallback_vectors(monkeypatch, tmp_path):
    _missing_images(monkeypatch, tmp_path)
    surface = pygame.Surface((100, 100), pygame.SRCALPHA)
    sprites.draw_vector(surface, (10, 10), (5, 3), (255, 100, 50))
    sprites.draw_vector(surface, None, (1, 1), (255, 0, 0))
    sprites.draw_vector(surface, (10, 10), (0, 0), (255, 0, 0))
    sprites.draw_vector(surface, (10, 10), (float("inf"), 1), (255, 0, 0))
    assert sprites.vector_length_px(0.0) == 0.0
    assert sprites.vector_length_px(float("nan")) == 0.0
    assert sprites.vector_length_px(1e9) >= 0
    trail = sprites.TrailLayer((10, 10))
    trail.extend([(1.0, 1.0), (2.0, 2.0)])
    trail.draw(surface, (0, 0))
    trail.clear()


def test_image_used_life_icon_path():
    surface = pygame.Surface((100, 100), pygame.SRCALPHA)
    ship = SHIPS["ship01"]
    sprites.draw_ship(surface, (20, 20), 0.0, 30, ship, grey=True)
    sprites.draw_ship_icon(surface, (50, 50), 30, ship, alive=False)
    sprites.ship_icon_surface(ship, 30, alive=False)
