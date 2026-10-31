import pygame
import pytest

from types import SimpleNamespace

from vector_drift import config
from vector_drift.scenes.base import SceneManager
from vector_drift.scenes.levels import LevelSelectScene

pytestmark = pytest.mark.usefixtures("pygame_display")


def _manager():
    audio = SimpleNamespace(play=lambda *a, **k: None, toggle_mute=lambda: None, start_loop=lambda *a, **k: None, stop_loop=lambda *a, **k: None)
    return SceneManager(audio)


def test_levels_rebuild_all_pages():
    mgr = _manager()
    scene = LevelSelectScene(mgr)
    mgr.switch(scene)
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    for page in (0, 1, 2):
        scene.page = page
        scene._rebuild_cards()
        scene.draw(surface)
    # click a locked/coming soon card? just draw
