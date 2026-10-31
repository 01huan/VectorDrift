import math

import pygame
import pytest

from vector_drift import config, sprites
from vector_drift.data import SHIPS

pytestmark = pytest.mark.usefixtures("pygame_display")


def test_sprites_smoke():
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    center = (config.WINDOW_W // 2, config.WINDOW_H // 2)
    ship = SHIPS["ship01"]
    sprites.draw_ship(surface, center, 0.3, 24, ship)
    sprites.draw_ship(surface, center, 0.3, 24, ship, grey=True)
    sprites.draw_ship_icon(surface, center, 24, ship, alive=True)
    sprites.draw_ship_icon(surface, center, 24, ship, alive=False)
    sprites.ship_icon_surface(ship, 24, alive=True)
    sprites.draw_target(surface, center, 40, 1.0, flash=0.5)
    sprites.draw_obstacle(surface, center, 30, 1.0, kind="bumper", seed=1)
    sprites.draw_obstacle(surface, center, 30, 1.0, kind="rock", seed=2)
    for kind in ("shockwave", "extratime", "shield", "life", "money"):
        sprites.draw_pickup(surface, (center[0] + 10, center[1]), 16, 1.0, kind=kind)
    sprites.draw_shield(surface, center, 40, 1.0)
    sprites.draw_start_marker(surface, (100, 100), 20, 1.0)
    sprites.draw_hole(surface, (200, 200), 30, 1.0, kind="black", pair_index=1)
    sprites.draw_hole(surface, (300, 200), 30, 1.0, kind="white", pair_index=2)
    sprites.draw_black_hole(surface, (200, 300), 30, 1.0)
    sprites.draw_white_hole(surface, (300, 300), 30, 1.0)
    sprites.draw_vector(surface, (50, 50), (10, 5), (255, 255, 255))
    assert sprites.vector_length_px(5) >= 0
    trail = sprites.TrailLayer((100, 100))
    trail.extend([(10.0, 10.0)])
    trail.draw(surface, (0, 0))
