import os

import pytest

# Run headless at 1x scale (config reads these when first imported).
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")


@pytest.fixture(scope="module")
def pygame_display():
    """pygame with a tiny display for one test module.

    Fonts cached during another module's pygame session die with its
    pygame.quit(); using them again is an access violation, so the font
    cache is cleared on the way in and out.
    """
    import pygame
    from vector_drift import ui
    ui._font_cache.clear()
    pygame.init()
    pygame.display.set_mode((1, 1))
    yield
    ui._font_cache.clear()
    pygame.quit()
