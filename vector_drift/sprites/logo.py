"""Logo sprite."""

import pygame

from ..image_assets import LOGO
from .common import load_image, source_size


def draw_logo(surface, center, width):
    size = source_size(LOGO)
    if size is None:
        return False
    w = max(1, round(width))
    h = max(1, round(w * size[1] / size[0]))
    img = load_image(LOGO, size_px=(w, h))
    if img is None:
        return False
    try:
        surface.blit(img, img.get_rect(center=(round(center[0]), round(center[1]))))
    except (pygame.error, TypeError, ValueError, OverflowError, MemoryError):
        return False
    return True
