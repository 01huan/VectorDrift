"""Smoke coverage for sprites draw functions."""

import pygame
import pytest

from vector_drift import config, sprites

pytestmark = pytest.mark.usefixtures("pygame_display")


def _surf():
    return pygame.Surface((config.WINDOW_W, config.WINDOW_H), pygame.SRCALPHA)


def test_draw_ship():
    s = _surf()
    from vector_drift import data
    ship = list(data.SHIPS.values())[0]
    sprites.draw_ship(s, (100, 100), 0.5, 20, ship)
    sprites.draw_ship(s, (100, 100), 0.5, 20, ship, grey=True)


def test_draw_ship_icon():
    s = _surf()
    from vector_drift import data
    ship = list(data.SHIPS.values())[0]
    sprites.draw_ship_icon(s, (50, 50), 18, ship, alive=True)
    sprites.draw_ship_icon(s, (50, 50), 18, ship, alive=False)
    sprites.ship_icon_surface(ship, 18, alive=True)


def test_draw_target():
    s = _surf()
    sprites.draw_target(s, (200, 200), 30, 1.0, flash=0.5)
    sprites.draw_target(s, (200, 200), 30, 1.0)


def test_draw_obstacle():
    s = _surf()
    for kind in ("bumper", "rock", "shockwave"):
        sprites.draw_obstacle(s, (100, 100), 15, 1.0, kind=kind, seed=((1, 2), 15))


def test_draw_pickup():
    s = _surf()
    for kind in ("shockwave", "extratime", "shield", "life", "money"):
        sprites.draw_pickup(s, (100, 100), 12, 1.0, kind=kind)


def test_draw_start_marker():
    s = _surf()
    sprites.draw_start_marker(s, (100, 100), 10, 1.0)


def test_draw_vector():
    s = _surf()
    sprites.draw_vector(s, (100, 100), (10, 5), (255, 0, 0))


def test_draw_hole():
    s = _surf()
    sprites.draw_hole(s, (100, 100), 15, 1.0, kind="black", pair_index=1)
    sprites.draw_hole(s, (200, 200), 15, 1.0, kind="white", pair_index=2)
    sprites.draw_black_hole(s, (100, 100), 15, 1.0)
    sprites.draw_white_hole(s, (200, 200), 15, 1.0)


def test_trail_layer():
    tl = sprites.TrailLayer((100, 100))
    tl.extend([(10, 10), (20, 20)])
    s = _surf()
    tl.draw(s, (0, 0))
    tl.clear()
    tl.draw(s, (0, 0))
    tl.extend([])
