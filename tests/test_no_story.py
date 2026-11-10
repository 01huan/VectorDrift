"""No story in the way: once the intro was seen Start opens level select, a level launches at once.

(The first Start plays the intro story: see test_intro_trigger.py.)
"""

from types import SimpleNamespace

import pygame
import pytest

from vector_drift.scenes.base import SceneManager
from vector_drift.scenes.game import FLIGHT, GameScene

pytestmark = pytest.mark.usefixtures("pygame_display")


def _manager():
    audio = SimpleNamespace(play=lambda *a, **k: None, start_loop=lambda *a, **k: None,
                            stop_loop=lambda *a, **k: None)
    return SceneManager(audio)


def test_start_after_the_intro_goes_straight_to_level_select():
    from vector_drift.scenes.levels import LevelSelectScene
    from vector_drift.scenes.menu import MenuScene

    manager = _manager()
    manager.session.seen_intro = True               # a player who has seen the intro story
    manager.switch(MenuScene(manager))
    manager.scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN,
                                                  mod=0, unicode="\r", scancode=0))
    assert isinstance(manager.scene, LevelSelectScene)


@pytest.mark.parametrize("level_id", [1, 6])
def test_a_new_player_can_launch_a_fixed_level_at_once(level_id):
    manager = _manager()
    manager.session.level_id = level_id
    manager.session.fx_text, manager.session.fy_text = "1", "0"
    scene = GameScene(manager)
    manager.switch(scene)
    scene._try_launch()
    assert scene.state == FLIGHT
