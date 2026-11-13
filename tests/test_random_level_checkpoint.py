"""Checkpoints in the merged random level: the screens are chained."""

from types import SimpleNamespace

import pytest

from vector_drift import config
from vector_drift.physics import Outcome
from vector_drift.scenes.base import SceneManager
from vector_drift.scenes.game import ARRIVED, PANNING, SETUP, GameScene
from vector_drift.scenes.win import WinScene

pytestmark = pytest.mark.usefixtures("pygame_display")


class Audio:
    def __init__(self):
        self.played = []

    def play(self, name, *a, **k):
        self.played.append(name)

    def start_loop(self, *a, **k):
        pass

    def stop_loop(self, *a, **k):
        pass

    def toggle_mute(self):
        pass


def _manager():
    return SceneManager(Audio())


def _scene(manager, seed):
    manager.session.level_id = 8
    manager.session.random_seed = seed
    scene = GameScene(manager)
    manager.switch(scene)
    return scene


def _pan_to_next_screen(scene):
    """Let the checkpoint pan finish: the camera moves on to the next screen."""
    assert scene.state == PANNING
    steps = int(config.CHECKPOINT_PAN_DURATION / 0.05) + 2
    for _ in range(steps):
        scene.update(0.05)
    assert scene.state == SETUP


def _reach_the_target(scene):
    """End the flight on the screen's target (the checkpoint or the planet)."""
    target = scene.level.target_center
    scene.flight = SimpleNamespace(time=1.0, trail=[], x=target[0], y=target[1])
    scene._end_flight(Outcome.REACHED)


def _multi_screen_seed():
    """A seed whose random map is made of more than one screen."""
    from vector_drift.level_merge import generate_merged_layout
    from vector_drift.level_presets import PRESET_8

    for seed in range(60):
        if len(generate_merged_layout(seed, PRESET_8).sections) > 1:
            return seed
    raise AssertionError("no multi-screen random map found")


def test_a_random_map_continues_on_the_next_screen_after_a_checkpoint():
    seed = _multi_screen_seed()
    manager = _manager()
    scene = _scene(manager, seed)
    assert scene.section_total > 1

    first = scene.level
    _reach_the_target(scene)

    # A checkpoint is not a win: the camera pans to the next screen.
    assert scene.state == PANNING
    assert scene.section_index == 1
    assert scene.manager.scene is scene
    assert not isinstance(scene.manager.scene, WinScene)

    _pan_to_next_screen(scene)
    assert scene.launch_pos == scene.level.start
    assert scene.level.start != first.start


def test_the_checkpoint_gives_a_life_and_the_last_screen_wins():
    seed = _multi_screen_seed()
    manager = _manager()
    scene = _scene(manager, seed)
    lives = scene.lives

    while not scene.on_last_section:
        _reach_the_target(scene)
        _pan_to_next_screen(scene)

    assert scene.section_index == scene.section_total - 1
    assert scene.lives >= lives, "a checkpoint gives a life back"

    _reach_the_target(scene)
    assert scene.state == ARRIVED
    for _ in range(120):
        if not isinstance(scene.manager.scene, GameScene):
            break
        scene.update(1 / 60)
    assert isinstance(scene.manager.scene, WinScene)
