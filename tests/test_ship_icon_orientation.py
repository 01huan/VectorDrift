"""ship_icon_surface: the lives-counter / checkpoint icon flies nose-up.

Ships are drawn (and pictured) nose pointing +x. pygame's positive angles
turn counter-clockwise, so standing the ship upright is a +90 turn.
"""
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pygame
import pytest

from vector_drift import image_assets, sprites
from vector_drift.image_assets import AssetSpec

pytestmark = pytest.mark.usefixtures("pygame_display")

SIZE = 18


@pytest.fixture
def fresh(tmp_path, monkeypatch):
    """Empty images dir and empty sprite cache, so no earlier icon is reused."""
    monkeypatch.setattr(image_assets, "IMAGES_DIR", tmp_path)
    monkeypatch.setattr(sprites, "_cache", {})
    image_assets.clear_cache()
    yield tmp_path
    image_assets.clear_cache()


@pytest.fixture
def pictured_ship(fresh, monkeypatch):
    """A ship whose picture is blue with a red nose on its right-hand side."""
    (fresh / "ships").mkdir()
    surf = pygame.Surface((64, 64), pygame.SRCALPHA)
    surf.fill((0, 0, 255, 255))
    surf.fill((255, 0, 0, 255), (44, 0, 20, 64))
    pygame.image.save(surf, str(fresh / "ships" / "test.png"))
    monkeypatch.setitem(image_assets._SPECS, "ship.test",
                        AssetSpec("ship.test", Path("ships/test.png")))
    return SimpleNamespace(id="test")


def _pixels(surface):
    return (pygame.surfarray.array3d(surface), pygame.surfarray.array_alpha(surface))


@pytest.mark.parametrize("alive", [True, False])
def test_pictured_icon_is_the_picture_turned_90_counter_clockwise(pictured_ship, alive):
    icon = sprites.ship_icon_surface(pictured_ship, SIZE, alive=alive)

    img = image_assets.load_image("ship.test", size_px=(SIZE, SIZE))
    source = img if alive else sprites._used_life_image(img)
    expected = pygame.transform.rotozoom(source, 90, 1.0)
    assert icon.get_size() == expected.get_size()
    for got, want in zip(_pixels(icon), _pixels(expected)):
        assert np.array_equal(got, want)


def test_pictured_icon_has_its_nose_on_top(pictured_ship):
    rgb, alpha = _pixels(sprites.ship_icon_surface(pictured_ship, SIZE))
    nose = (rgb[..., 0] > 128) & (rgb[..., 2] < 128) & (alpha > 128)
    rows = np.nonzero(nose)[1]
    assert rows.size and rows.max() < SIZE / 2


@pytest.mark.parametrize("alive", [True, False])
def test_code_drawn_icon_has_its_nose_on_top(fresh, alive):
    from vector_drift.data import SHIPS
    ship = SHIPS["ship01"]
    assert image_assets.load_image(f"ship.{ship.id}", size_px=(40, 40)) is None

    icon = sprites.ship_icon_surface(ship, 40, alive=alive)
    opaque = pygame.surfarray.array_alpha(icon) > 128
    width_per_row = opaque.sum(axis=0)
    rows = np.nonzero(width_per_row)[0]
    middle = (rows[0] + rows[-1]) / 2
    # The +x end of _render_ship is the narrow nose; the wings sit near the
    # tail. Nose up means the widest rows (the wings) are below the middle.
    assert int(np.argmax(width_per_row)) > middle
    assert width_per_row[rows[0]] < width_per_row[rows[-1]]
