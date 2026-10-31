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


def test_game_scene_buttons_and_inputs():
    mgr = _manager()
    mgr.session.level_id = 1
    mgr.session.fx_text = "x"
    mgr.session.fy_text = "y"
    scene = GameScene(mgr)
    mgr.switch(scene)
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    scene.draw(surface)
    # click various icon buttons
    for attr in ("level_button", "run_button", "ai_button", "ai_apply_button", "ai_close_button"):
        btn = getattr(scene, attr, None)
        if btn is not None:
            scene.handle_event(pygame.event.Event(pygame.MOUSEMOTION, pos=btn.rect.center))
            scene.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=btn.rect.center))
    scene.draw(surface)
    # keyboard shortcuts
    for key in (pygame.K_RETURN, pygame.K_ESCAPE, pygame.K_TAB):
        scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key, mod=0))
    scene.draw(surface)
