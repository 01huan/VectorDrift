import pygame
import pytest

from types import SimpleNamespace

from vector_drift import config
from vector_drift.scenes.base import SceneManager
from vector_drift.scenes.game import GameScene, SETUP, FLIGHT
from vector_drift.expr_parser import parse_expression

pytestmark = pytest.mark.usefixtures("pygame_display")


def _manager():
    audio = SimpleNamespace(play=lambda *a, **k: None, toggle_mute=lambda: None, start_loop=lambda *a, **k: None, stop_loop=lambda *a, **k: None)
    return SceneManager(audio)


def test_game_scene_flight_run():
    mgr = _manager()
    mgr.session.level_id = 1
    mgr.session.fx_text = "0"
    mgr.session.fy_text = "0"
    scene = GameScene(mgr)
    mgr.switch(scene)
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    scene.draw(surface)
    # try launching
    run_btn = getattr(scene, "run_button", None)
    if run_btn is not None:
        scene.handle_event(pygame.event.Event(pygame.MOUSEMOTION, pos=run_btn.rect.center))
        scene.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=run_btn.rect.center))
    # step simulation
    for _ in range(100):
        scene.update(1/60)
        scene.draw(surface)
        if getattr(scene, "state", None) != FLIGHT:
            break
    # maybe click run again to stop
    if run_btn is not None:
        scene.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=run_btn.rect.center))
    scene.draw(surface)
