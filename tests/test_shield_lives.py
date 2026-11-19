"""A Shield comes back every life, like Unbound; the other pickups stay taken."""

from types import SimpleNamespace

import pytest

from vector_drift.data import LevelSpec, PickupSpec
from vector_drift.scenes import game as game_module
from vector_drift.scenes.base import SceneManager
from vector_drift.scenes.game import FLIGHT, SETUP, GameScene

pytestmark = pytest.mark.usefixtures("pygame_display")

START = (-7.0, 0.0)
SHIELD = (-7.0, 0.8)
EXTRATIME = (-7.0, 2.0)
MONEY = (-7.0, 3.5)

# Every pickup sits straight above the start, in the order a ship flying up meets them.
LEVEL = LevelSpec(
    id=1, name="test", start=START, target_center=(7.0, 0.0), target_radius=1.0,
    ship_id="ship01",
    pickups=(
        PickupSpec(center=SHIELD, radius=0.45, kind="shield"),
        PickupSpec(center=EXTRATIME, radius=0.45, kind="extratime"),
        PickupSpec(center=MONEY, radius=0.45, kind="money"),
    ),
)


@pytest.fixture
def scene(monkeypatch):
    monkeypatch.setattr(game_module, "get_level", lambda *a, **k: LEVEL)
    audio = SimpleNamespace(play=lambda *a, **k: None, start_loop=lambda *a, **k: None,
                            stop_loop=lambda *a, **k: None, toggle_mute=lambda: None)
    manager = SceneManager(audio)
    manager.session.level_id = 1
    s = GameScene(manager)
    manager.switch(s)
    return s


def fly(scene, fx, fy):
    """Launch and run until the flight ends; True if the shield was taken on the way.

    Watched during the flight: once the life is lost the scene puts it back.
    """
    scene.editor.set_lines([fx, fy])
    scene._on_text_change(scene.editor)
    scene._try_launch()
    assert scene.state == FLIGHT
    took_shield = False
    for _ in range(5000):
        if scene.state != FLIGHT:
            return took_shield
        scene.update(1 / 30)
        took_shield = took_shield or pickup(scene, SHIELD).consumed
    raise AssertionError("flight never ended")


def pickup(scene, center):
    return next(p for p in scene.pickups if p.center == center)


def test_the_shield_comes_back_after_a_lost_life(scene):
    assert fly(scene, "0", "10")                # up through every pickup and out of the map
    assert scene.state == SETUP and scene.lives == LEVEL.lives - 1
    assert not pickup(scene, SHIELD).consumed


def test_the_shield_comes_back_after_a_time_up_too(scene):
    assert fly(scene, "0", "0.05")              # takes the shield, stops at y = 2.5 m
    assert scene.state == SETUP and scene.lives == LEVEL.lives - 1
    assert not pickup(scene, SHIELD).consumed


def test_the_other_pickups_stay_gone(scene):
    assert fly(scene, "0", "10")
    assert pickup(scene, EXTRATIME).consumed and pickup(scene, MONEY).consumed

    assert fly(scene, "0", "10")                # the next life takes the shield once more
    assert not pickup(scene, SHIELD).consumed
    assert pickup(scene, EXTRATIME).consumed and pickup(scene, MONEY).consumed
