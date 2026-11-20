"""draw_ship: a ship flying left keeps its top side up.

Turning a picture 180 degrees would put its dome and antenna underneath, so a
ship heading left (cos(heading) < 0) is flipped top-to-bottom before it is
turned; it reads as a left-right mirror of the right-facing ship. Ships
heading right are drawn exactly as before.
"""
import math
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pygame
import pytest

from vector_drift import image_assets, sprites
from vector_drift.image_assets import AssetSpec

pytestmark = pytest.mark.usefixtures("pygame_display")

SIZE = 40
CANVAS = 80
CENTER = (CANVAS / 2, CANVAS / 2)


@pytest.fixture
def fresh(tmp_path, monkeypatch):
    """Empty images dir and empty sprite cache, so no earlier sprite is reused."""
    monkeypatch.setattr(image_assets, "IMAGES_DIR", tmp_path)
    monkeypatch.setattr(sprites, "_cache", {})
    image_assets.clear_cache()
    yield tmp_path
    image_assets.clear_cache()


@pytest.fixture
def pictured_ship(fresh, monkeypatch):
    """Top half red, bottom half blue, with a green nose on the right."""
    (fresh / "ships").mkdir()
    surf = pygame.Surface((64, 64), pygame.SRCALPHA)
    surf.fill((0, 0, 255, 255))
    surf.fill((255, 0, 0, 255), (0, 0, 64, 32))
    surf.fill((0, 255, 0, 255), (52, 0, 12, 64))
    pygame.image.save(surf, str(fresh / "ships" / "test.png"))
    monkeypatch.setitem(image_assets._SPECS, "ship.test",
                        AssetSpec("ship.test", Path("ships/test.png")))
    return SimpleNamespace(id="test")


def _draw(ship, heading, grey=False):
    canvas = pygame.Surface((CANVAS, CANVAS), pygame.SRCALPHA)
    canvas.fill((0, 0, 0, 0))
    sprites.draw_ship(canvas, CENTER, heading, SIZE, ship, grey=grey)
    return canvas


def _old_draw(source, heading):
    """What draw_ship did before the fix: turn the picture, never flip it."""
    canvas = pygame.Surface((CANVAS, CANVAS), pygame.SRCALPHA)
    canvas.fill((0, 0, 0, 0))
    rotated = pygame.transform.rotozoom(source, math.degrees(heading), 1.0)
    canvas.blit(rotated, rotated.get_rect(center=CENTER))
    return canvas


def _mask(canvas, want):
    rgb = pygame.surfarray.array3d(canvas).astype(int)
    alpha = pygame.surfarray.array_alpha(canvas)
    near = np.abs(rgb - np.array(want)).sum(axis=-1) < 120
    return near & (alpha > 200)


def _mean_xy(mask):
    xs, ys = np.nonzero(mask)  # surfarray is indexed [x, y]
    assert xs.size, "colour not found on the canvas"
    return xs.mean(), ys.mean()


@pytest.mark.parametrize("grey", [False, True])
def test_pictured_ship_heading_left_keeps_its_top_half_on_top(pictured_ship, grey):
    canvas = _draw(pictured_ship, math.pi, grey=grey)
    if grey:
        # Used-life copy: the red top is brighter than the blue bottom once
        # it is greyscaled, so compare brightness of the two halves.
        rgb = pygame.surfarray.array3d(canvas)[..., 0].astype(int)
        opaque = pygame.surfarray.array_alpha(canvas) > 200
        ys = np.nonzero(opaque)[1]
        mid = (ys.min() + ys.max()) / 2
        top = rgb[:, :int(mid)][opaque[:, :int(mid)]].mean()
        bottom = rgb[:, int(mid) + 1:][opaque[:, int(mid) + 1:]].mean()
        assert top > bottom
        return
    _, red_y = _mean_xy(_mask(canvas, (255, 0, 0)))
    _, blue_y = _mean_xy(_mask(canvas, (0, 0, 255)))
    nose_x, _ = _mean_xy(_mask(canvas, (0, 255, 0)))
    assert red_y < CANVAS / 2 < blue_y
    assert nose_x < CANVAS / 2  # still pointing the way it flies


@pytest.mark.parametrize("heading", [0.0, 0.7, -1.2, math.pi / 2 - 0.01])
def test_pictured_ship_heading_right_is_unchanged(pictured_ship, heading):
    img = image_assets.load_image("ship.test", size_px=(SIZE, SIZE))
    got, want = _draw(pictured_ship, heading), _old_draw(img, heading)
    assert np.array_equal(pygame.surfarray.array3d(got), pygame.surfarray.array3d(want))
    assert np.array_equal(pygame.surfarray.array_alpha(got), pygame.surfarray.array_alpha(want))


@pytest.mark.parametrize("grey", [False, True])
def test_code_drawn_ship_heading_left_keeps_its_shine_on_top(fresh, grey):
    from vector_drift.data import SHIPS
    ship = SHIPS["ship01"]
    assert image_assets.load_image(f"ship.{ship.id}", size_px=(SIZE, SIZE)) is None

    def shine_y(heading):
        canvas = _draw(ship, heading, grey=grey)
        rgb = pygame.surfarray.array3d(canvas).astype(int)
        white = (rgb.min(axis=-1) > 200) & (pygame.surfarray.array_alpha(canvas) > 200)
        if not white.any():  # the grey ship has no white; use its lightest pixels
            lum = rgb.sum(axis=-1) * (pygame.surfarray.array_alpha(canvas) > 200)
            white = lum >= np.percentile(lum[lum > 0], 95)
        return _mean_xy(white)[1]

    assert shine_y(0.0) < CANVAS / 2
    assert shine_y(math.pi) < CANVAS / 2


def test_code_drawn_ship_heading_right_is_unchanged(fresh):
    from vector_drift.data import SHIPS
    ship = SHIPS["ship01"]
    img = sprites._render_ship(SIZE, ship.hull_color, ship.wing_color, ship.trim_color)
    got, want = _draw(ship, 0.0), _old_draw(img, 0.0)
    assert np.array_equal(pygame.surfarray.array3d(got), pygame.surfarray.array3d(want))
    assert np.array_equal(pygame.surfarray.array_alpha(got), pygame.surfarray.array_alpha(want))
