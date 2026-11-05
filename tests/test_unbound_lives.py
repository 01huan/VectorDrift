"""Unbound comes back every life; a time-up off the map sends the next life to the start."""

from types import SimpleNamespace

import pygame
import pytest

from vector_drift import config
from vector_drift.data import LevelSpec, ObstacleSpec, PickupSpec
from vector_drift.physics import Outcome
from vector_drift.scenes import game as game_module
from vector_drift.scenes import replay as replay_module
from vector_drift.scenes.base import SceneManager
from vector_drift.scenes.game import FLIGHT, SETUP, GameScene
from vector_drift.scenes.replay import ReplayScene
from vector_drift.story import all_seen_keys

pytestmark = pytest.mark.usefixtures("pygame_display")

START = (-7.0, 0.0)
UNBOUND = (-7.0, 0.8)
SHOCKWAVE = (-7.0, 2.0)
EXTRATIME = (-7.0, 3.5)
MONEY = (-7.0, 5.0)
ROCK = (-4.5, 2.0)                  # inside the shockwave's blast, off the ship's path

# Every pickup sits straight above the start, in the order a ship flying up meets them.
LEVEL = LevelSpec(
    id=1, name="test", start=START, target_center=(7.0, 0.0), target_radius=1.0,
    ship_id="ship01",
    obstacles=(ObstacleSpec(center=ROCK, radius=0.5),),
    pickups=(
        PickupSpec(center=UNBOUND, radius=0.45, kind="unbound"),
        PickupSpec(center=SHOCKWAVE, radius=0.45, kind="shockwave"),
        PickupSpec(center=EXTRATIME, radius=0.45, kind="extratime"),
        PickupSpec(center=MONEY, radius=0.45, kind="money"),
    ),
)


@pytest.fixture
def scene(monkeypatch):
    monkeypatch.setattr(game_module, "get_level", lambda *a, **k: LEVEL)
    monkeypatch.setattr(replay_module, "get_level", lambda *a, **k: LEVEL)
    audio = SimpleNamespace(play=lambda *a, **k: None, start_loop=lambda *a, **k: None,
                            stop_loop=lambda *a, **k: None, toggle_mute=lambda: None)
    manager = SceneManager(audio)
    manager.session.story_seen = all_seen_keys()
    manager.session.level_id = 1
    s = GameScene(manager)
    manager.switch(s)
    return s


def fly(scene, fx, fy):
    """Launch and run until the flight ends; returns the finished Flight."""
    scene.editor.set_lines([fx, fy])
    scene._on_text_change(scene.editor)
    scene._try_launch()
    assert scene.state == FLIGHT
    flight = scene.flight
    for _ in range(5000):
        if scene.state != FLIGHT:
            return flight
        scene.update(1 / 30)
    raise AssertionError("flight never ended")


def pickup(scene, center):
    return next(p for p in scene.pickups if p.center == center)


def test_unbound_comes_back_after_a_lost_life(scene):
    flight = fly(scene, "0", "10")              # up through every pickup, far off the map
    assert flight.unbound
    assert flight.outcome is Outcome.TIMEOUT
    assert scene.state == SETUP and scene.lives == LEVEL.lives - 1
    assert not pickup(scene, UNBOUND).consumed


def test_unbound_comes_back_after_a_time_up_too(scene):
    flight = fly(scene, "0", "0.05")            # takes the unbound, stops at y = 2.5 m
    assert flight.unbound
    assert flight.outcome is Outcome.TIMEOUT
    assert not pickup(scene, UNBOUND).consumed


def test_the_other_pickups_and_cleared_rocks_stay_gone(scene):
    fly(scene, "0", "10")
    for center in (SHOCKWAVE, EXTRATIME, MONEY):
        assert pickup(scene, center).consumed
    assert ROCK not in [o.center for o in scene.level.obstacles]

    second = fly(scene, "0", "10")              # the next life: same again, unbound once more
    assert second.unbound
    assert ROCK not in [o.center for o in second.obstacle_specs]
    assert not pickup(scene, UNBOUND).consumed
    assert all(pickup(scene, c).consumed for c in (SHOCKWAVE, EXTRATIME, MONEY))


def test_time_up_off_the_map_sends_the_next_life_to_the_start(scene):
    # Unbound, then (10 s + 3 s extratime) y = 12.7 m when time runs out.
    flight = fly(scene, "0", "0.15")
    assert flight.outcome is Outcome.TIMEOUT
    assert abs(flight.y) > config.WORLD_HALF_H
    assert tuple(scene.launch_pos) == START
    assert "back to start" in scene.banner[1]


def test_time_up_on_the_map_still_resumes_where_the_ship_stopped(scene):
    flight = fly(scene, "0", "0.05")
    assert flight.outcome is Outcome.TIMEOUT
    assert abs(flight.y) < config.WORLD_HALF_H
    assert tuple(scene.launch_pos) == (flight.x, flight.y)
    assert "resume from" in scene.banner[1]


def test_replay_of_the_next_life_shows_the_unbound_again(scene):
    fly(scene, "0", "10")
    (first,) = scene.session.replays
    fly(scene, "0", "10")
    (second,) = [r for r in scene.session.replays if r != first]
    assert [tuple(c) for c in first["consumed_pickups"]] == []
    consumed = {tuple(c) for c in second["consumed_pickups"]}
    assert consumed == {SHOCKWAVE, EXTRATIME, MONEY}

    scene.session.replays = [second]
    replay = ReplayScene(scene.manager)
    shown = {p.center for p in replay._pickups if not p.consumed}
    assert UNBOUND in shown
    assert not shown & {SHOCKWAVE, EXTRATIME, MONEY}
    replay.draw(pygame.Surface((config.WINDOW_W, config.WINDOW_H)))
