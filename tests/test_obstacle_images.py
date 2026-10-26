"""Each bumper shows one of the rock pictures, turned by its own random angle."""
import pygame
import pytest

from vector_drift import image_assets, sprites
from vector_drift.image_assets import ROCK_KEYS

pytestmark = pytest.mark.usefixtures("pygame_display")


def test_every_rock_has_a_512px_image():
    # Real assets/ on purpose: each registered rock must ship its picture.
    assert len(ROCK_KEYS) >= 2
    for key in ROCK_KEYS:
        path = image_assets.IMAGES_DIR / image_assets.get_spec(key).path
        assert pygame.image.load(str(path)).get_size() == (512, 512)


def test_a_bumper_keeps_its_rock_and_angle():
    seed = ((1.5, -2.0), 0.8)
    assert sprites._obstacle_look(seed, ROCK_KEYS) == sprites._obstacle_look(seed, ROCK_KEYS)


def test_bumpers_use_every_rock_and_many_angles():
    looks = [sprites._obstacle_look(((x * 0.7, -x * 0.3), 1.0), ROCK_KEYS) for x in range(60)]
    assert {key for key, _ in looks} == set(ROCK_KEYS)
    assert len({round(angle) for _, angle in looks}) > 30
    assert all(0.0 <= angle < 360.0 for _, angle in looks)


def test_bumper_picture_is_cached_and_drawn():
    image_assets.clear_cache()
    seed = ((0.0, 0.0), 1.2)
    first = sprites._obstacle_picture("bumper", 60, seed)
    assert first is not None
    assert sprites._obstacle_picture("bumper", 60, seed) is first
    surface = pygame.Surface((200, 200), pygame.SRCALPHA)
    sprites.draw_obstacle(surface, (100, 100), 60, 0.0, seed=seed)
    assert surface.get_at((100, 100)).a > 0


def test_without_rock_pictures_the_code_drawn_rock_is_used(tmp_path, monkeypatch):
    monkeypatch.setattr(image_assets, "IMAGES_DIR", tmp_path)
    image_assets.clear_cache()
    try:
        assert sprites._obstacle_picture("bumper", 60, ((0.0, 0.0), 1.2)) is None
        surface = pygame.Surface((200, 200), pygame.SRCALPHA)
        sprites.draw_obstacle(surface, (100, 100), 60, 0.0, seed=((0.0, 0.0), 1.2))
        assert surface.get_at((100, 100)).a > 0
    finally:
        image_assets.clear_cache()
