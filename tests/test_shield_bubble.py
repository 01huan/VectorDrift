"""draw_shield is the see-through bubble, never the shield pickup's icon."""
import numpy as np
import pygame
import pytest

from vector_drift import image_assets, sprites
from vector_drift.data import SHIPS

pytestmark = pytest.mark.usefixtures("pygame_display")

SIZE = 160
CENTER = (SIZE // 2, SIZE // 2)
RADIUS = 36


@pytest.fixture
def code_drawn(tmp_path, monkeypatch):
    """No pictures and an empty sprite cache: every prop is code-drawn, fresh."""
    monkeypatch.setattr(image_assets, "IMAGES_DIR", tmp_path)
    monkeypatch.setattr(sprites, "_cache", {})
    image_assets.clear_cache()
    yield
    image_assets.clear_cache()


def _ship_scene():
    surface = pygame.Surface((SIZE, SIZE))
    surface.fill((10, 12, 24))
    sprites.draw_ship(surface, CENTER, 0.0, 2 * RADIUS, SHIPS["ship01"])
    return surface


def _inner_disk(surface):
    """RGB of every pixel within 0.7 of the shield radius of the centre."""
    rgb = pygame.surfarray.array3d(surface).astype(float)
    xs, ys = np.ogrid[:SIZE, :SIZE]
    inside = (xs - CENTER[0]) ** 2 + (ys - CENTER[1]) ** 2 <= (0.7 * RADIUS) ** 2
    return rgb[inside]


def _shield_over_ship():
    surface = _ship_scene()
    before = _inner_disk(surface)
    sprites.draw_shield(surface, CENTER, RADIUS, t=0.0)
    return before, _inner_disk(surface)


def _assert_see_through(before, after):
    # The bubble only tints what is under it (the small glint aside), so the
    # ship stays plainly visible. Measured: about 40-50 mean, 60-72 at the
    # 90th percentile for the bubble; about 155 / 205 for the opaque pickup icon.
    change = np.linalg.norm(after - before, axis=1)
    assert change.mean() < 80, change.mean()
    assert np.percentile(change, 90) < 110, np.percentile(change, 90)


def test_shield_center_is_see_through(code_drawn):
    _assert_see_through(*_shield_over_ship())


def test_shield_is_see_through_after_a_shield_pickup_of_the_same_size(code_drawn):
    # The pickup icon is drawn first at the same radius: its cached art must
    # not be reused for the bubble.
    sprites.draw_pickup(pygame.Surface((SIZE, SIZE), pygame.SRCALPHA), CENTER, RADIUS,
                        0.0, kind="shield")
    _assert_see_through(*_shield_over_ship())


def test_shield_pickup_icon_is_still_drawn_after_the_bubble(code_drawn):
    sprites.draw_shield(pygame.Surface((SIZE, SIZE)), CENTER, RADIUS, t=0.0)
    surface = pygame.Surface((SIZE, SIZE))
    surface.fill((0, 0, 0))
    sprites.draw_pickup(surface, CENTER, RADIUS, 0.0, kind="shield")
    # The icon's solid purple body, not the faint blue bubble.
    r, g, b, _ = surface.get_at((CENTER[0], CENTER[1] + RADIUS // 2))
    assert b > 150 and r > 80 and g < 140, (r, g, b)
