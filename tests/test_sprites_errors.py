import math

import pygame
import pytest

from vector_drift import config, sprites
from vector_drift.data import SHIPS

pytestmark = pytest.mark.usefixtures("pygame_display")


def test_sprites_error_and_edge_paths():
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    # invalid center types
    sprites.draw_ship(surface, None, 0.0, 10, SHIPS["ship01"])
    sprites.draw_ship(surface, "bad", 0.0, 10, SHIPS["ship01"])
    sprites.draw_ship(surface, (1e9, 1e9), 0.0, 10, SHIPS["ship01"])  # cull
    sprites.draw_ship(surface, (10, 10), float("inf"), 10, SHIPS["ship01"])
    # huge size
    sprites.draw_ship(surface, (10, 10), 0.0, 64, SHIPS["ship01"])
    # draw_ship_icon / ship_icon_surface invalid
    sprites.draw_ship_icon(surface, (10, 10), 10, SHIPS["ship01"])
    sprites.ship_icon_surface(SHIPS["ship01"], 10)
    # draw_target invalid
    sprites.draw_target(surface, None, 10, 1.0)
    sprites.draw_target(surface, (10, 10), 0, 1.0)
    # draw_obstacle invalid
    sprites.draw_obstacle(surface, None, 10, 1.0)
    sprites.draw_obstacle(surface, (10, 10), 0, 1.0, kind="unknown", seed=1)
    # draw_pickup invalid
    sprites.draw_pickup(surface, None, 10, 1.0, kind="shockwave")
    sprites.draw_pickup(surface, (10, 10), 0, 1.0, kind="bogus")
    # draw_shield invalid
    sprites.draw_shield(surface, None, 10, 1.0)
    # draw_start_marker invalid
    sprites.draw_start_marker(surface, None, 10, 1.0)
    # draw_hole invalid
    sprites.draw_hole(surface, None, 10, 1.0)
    sprites.draw_hole(surface, (10, 10), 0, 1.0, kind="white", pair_index=99)
    sprites.draw_black_hole(surface, None, 10, 1.0)
    sprites.draw_white_hole(surface, None, 10, 1.0)
    # draw_vector invalid
    sprites.draw_vector(surface, None, (1, 1), (255, 0, 0))
    sprites.draw_vector(surface, (10, 10), (0, 0), (255, 0, 0))
    sprites.draw_vector(surface, (10, 10), (float("inf"), 1), (255, 0, 0))
    # vector_length_px
    assert sprites.vector_length_px(0) == 0.0
    assert sprites.vector_length_px(float("nan")) == 0.0
    assert sprites.vector_length_px(1e9) >= 0
    # TrailLayer invalid
    trail = sprites.TrailLayer((10, 10))
    trail.extend([])
    trail.draw(surface, (0, 0))
