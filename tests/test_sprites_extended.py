import pygame
import pytest

from vector_drift import config, sprites
from vector_drift.data import SHIPS

pytestmark = pytest.mark.usefixtures("pygame_display")


def test_sprites_extended():
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    center = (100, 100)
    for sid, ship in SHIPS.items():
        sprites.draw_ship(surface, center, 0.5, 20, ship)
        sprites.draw_ship(surface, center, 0.5, 20, ship, grey=True)
        sprites.draw_ship_icon(surface, center, 20, ship, alive=True)
        sprites.draw_ship_icon(surface, center, 20, ship, alive=False)
        sprites.ship_icon_surface(ship, 20, alive=True)
        sprites.ship_icon_surface(ship, 20, alive=False)
    # obstacles
    for kind in ("bumper", "rock"):
        for seed in (0, 1, 2, 42):
            sprites.draw_obstacle(surface, (200, 200), 20, 1.0, kind=kind, seed=seed)
    # pickups
    for kind in ("shockwave", "extratime", "shield", "life", "money"):
        for t in (0.0, 1.5, 3.0):
            sprites.draw_pickup(surface, (300, 300), 16, t, kind=kind)
    # holes
    for kind in ("black", "white"):
        for pair in (1, 2, 5, 10, 11):
            sprites.draw_hole(surface, (400, 400), 20, 1.0, kind=kind, pair_index=pair)
    sprites.draw_black_hole(surface, (400, 450), 20, 1.0)
    sprites.draw_white_hole(surface, (450, 450), 20, 1.0)
    # shield/target
    for flash in (0.0, 0.5, 1.0):
        sprites.draw_target(surface, (500, 500), 30, 1.0, flash=flash)
    sprites.draw_shield(surface, (500, 550), 30, 1.0)
    sprites.draw_start_marker(surface, (50, 50), 15, 0.5)
    sprites.draw_start_marker(surface, (50, 50), 15, 2.0)
    # trail
    trail = sprites.TrailLayer((60, 60))
    trail.extend([(5.0, 5.0), (10.0, 10.0), (15.0, 15.0)])
    trail.draw(surface, (0, 0))
    trail.clear()
    # vectors
    sprites.draw_vector(surface, (10, 10), (5, 3), (255, 100, 50))
    sprites.draw_vector(surface, (10, 10), (0, 0), (255, 100, 50))
    assert sprites.vector_length_px(0) >= 0
    assert sprites.vector_length_px(1000) >= 0
