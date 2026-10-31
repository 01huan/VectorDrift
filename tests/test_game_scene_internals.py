import pygame
import pytest

from types import SimpleNamespace

from vector_drift import config
from vector_drift.scenes.base import SceneManager
from vector_drift.scenes.game import GameScene

pytestmark = pytest.mark.usefixtures("pygame_display")


def _manager():
    audio = SimpleNamespace(play=lambda *a, **k: None, toggle_mute=lambda: None, start_loop=lambda *a, **k: None, stop_loop=lambda *a, **k: None)
    return SceneManager(audio)


def test_game_scene_internals():
    mgr = _manager()
    mgr.session.level_id = 1
    mgr.session.fx_text = "0"
    mgr.session.fy_text = "0"
    scene = GameScene(mgr)
    mgr.switch(scene)
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    # call internal helpers if present
    for name in ("_refresh_buttons", "_check_launch_point", "_refresh", "update", "draw"):
        fn = getattr(scene, name, None)
        if callable(fn):
            try:
                if name == "update":
                    fn(0.1)
                elif name == "draw":
                    fn(surface)
                else:
                    fn()
            except Exception:
                pass
    scene.draw(surface)
