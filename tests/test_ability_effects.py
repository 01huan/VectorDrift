"""Ability effects: the flash when an ability is used, and the replay of it."""

import pygame
import pytest

from types import SimpleNamespace

from vector_drift import config
from vector_drift.physics import Outcome
from vector_drift.replay import (ReplayRecord, normalize_ability_events,
                                 normalize_records)
from vector_drift.scenes import ability_effects as afx
from vector_drift.scenes.base import SceneManager
from vector_drift.scenes.game import GameScene
from vector_drift.scenes.replay import ReplayScene

pytestmark = pytest.mark.usefixtures("pygame_display")


def _manager():
    audio = SimpleNamespace(play=lambda *a, **k: None, toggle_mute=lambda: None,
                             start_loop=lambda *a, **k: None, stop_loop=lambda *a, **k: None)
    return SceneManager(audio)


def _game_scene(charges=None):
    mgr = _manager()
    mgr.session.level_id = 1
    mgr.session.fx_text = "0"
    mgr.session.fy_text = "0"
    mgr.session.ability_charges = dict(charges or {})
    scene = GameScene(mgr)
    mgr.switch(scene)
    return mgr, scene


# --- the live game ----------------------------------------------------------
def test_using_an_ability_starts_a_flash():
    _mgr, scene = _game_scene({"ability_boost": 1})
    scene._try_launch()
    assert scene.ability_fx.effects == []
    assert scene._use_ability_key(pygame.K_b) is True
    assert len(scene.ability_fx.effects) == 1
    effect = scene.ability_fx.effects[0]
    assert effect.ability_id == "ability_boost"
    assert effect.name == "Boost"
    assert effect.center == pytest.approx((scene.flight.x, scene.flight.y))


def test_the_use_is_recorded_for_the_replay():
    _mgr, scene = _game_scene({"ability_boost": 1})
    scene._try_launch()
    scene._use_ability_key(pygame.K_b)
    assert len(scene._replay_ability_events) == 1
    event = scene._replay_ability_events[0]
    assert event["ability"] == "ability_boost"
    assert event["name"] == "Boost"
    assert event["t"] == pytest.approx(scene.flight.time)
    assert event["x"] == pytest.approx(scene.flight.x)


def test_a_new_launch_starts_a_new_set_of_flashes():
    _mgr, scene = _game_scene({"ability_boost": 2})
    scene._try_launch()
    scene._use_ability_key(pygame.K_b)
    assert len(scene.ability_fx.effects) == 1
    scene._try_launch()
    assert scene.ability_fx.effects == []
    assert scene._replay_ability_events == []


def test_the_saved_replay_record_carries_the_ability_use():
    mgr, scene = _game_scene({"ability_boost": 1})
    scene._try_launch()
    scene._use_ability_key(pygame.K_b)
    scene._end_flight(Outcome.TIMEOUT)
    record = mgr.session.replays[0]
    assert len(record["ability_events"]) == 1
    assert record["ability_events"][0]["ability"] == "ability_boost"


def test_the_flash_ages_out():
    _mgr, scene = _game_scene({"ability_boost": 1})
    scene._try_launch()
    scene._use_ability_key(pygame.K_b)
    scene.ability_fx.update(afx.ABILITY_FX_S)
    assert scene.ability_fx.effects == []


def test_the_game_draws_the_flash():
    _mgr, scene = _game_scene({"ability_boost": 1})
    scene._try_launch()
    scene._use_ability_key(pygame.K_b)
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    scene.draw(surface)


# --- the record --------------------------------------------------------------
def test_the_record_keeps_the_ability_events():
    record = ReplayRecord(level_id=1, ability_events=[
        {"kind": "ability", "ability": "ability_boost", "name": "Boost",
         "key": "B", "t": 1.5, "x": 2.0, "y": -3.0},
    ])
    data = record.to_dict()
    assert data["ability_events"][0]["ability"] == "ability_boost"
    again = ReplayRecord.from_dict(data)
    assert again.ability_events == data["ability_events"]


def test_old_records_without_ability_events_still_load():
    record = ReplayRecord.from_dict({"level_id": 1, "frames": []})
    assert record.ability_events == []
    assert record.to_dict()["ability_events"] == []


def test_normalize_records_keeps_the_ability_events():
    records = normalize_records([{
        "level_id": 1,
        "frames": [],
        "ability_events": [{"ability": "ability_blink", "name": "Blink", "t": 0.5,
                            "x": 1.0, "y": 2.0}],
    }])
    assert records[0]["ability_events"][0]["ability"] == "ability_blink"


def test_broken_ability_events_are_dropped():
    events = normalize_ability_events([
        "not a dict",
        {"ability": "ability_boost", "t": "soon", "x": 0.0, "y": 0.0},
        {"ability": "ability_boost", "t": 1.0, "x": float("nan"), "y": 0.0},
        {"ability": "ability_boost", "name": "Boost", "t": 1.0, "x": 1.0, "y": 2.0},
    ])
    assert len(events) == 1
    assert events[0]["ability"] == "ability_boost"


# --- the replay --------------------------------------------------------------
def test_the_replay_shows_the_recorded_flash(monkeypatch):
    calls = []
    monkeypatch.setattr(afx, "draw_effects",
                        lambda surface, effects, *a, **k: calls.append(list(effects)))
    mgr = _manager()
    mgr.session.replays = [{
        "level_id": 1,
        "ship_id": "ship01",
        "fx_text": "0",
        "fy_text": "0",
        "outcome": "timeout",
        "frames": [
            {"t": 0, "x": -7, "y": 0, "vx": 0, "vy": 0, "fx": 0, "fy": 0},
            {"t": 1, "x": -6, "y": 0, "vx": 1, "vy": 0, "fx": 0, "fy": 0},
        ],
        "ability_events": [{"kind": "ability", "ability": "ability_boost",
                            "name": "Boost", "key": "B", "t": 0.0, "x": -7, "y": 0}],
    }]
    scene = ReplayScene(mgr)
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    scene.draw(surface)
    assert calls, "the recorded ability flash was not drawn"
    assert calls[0][0].ability_id == "ability_boost"


def test_the_replay_has_no_flash_without_recorded_uses(monkeypatch):
    calls = []
    monkeypatch.setattr(afx, "draw_effects",
                        lambda surface, effects, *a, **k: calls.append(list(effects)))
    mgr = _manager()
    mgr.session.replays = [{
        "level_id": 1,
        "ship_id": "ship01",
        "fx_text": "0",
        "fy_text": "0",
        "outcome": "timeout",
        "frames": [
            {"t": 0, "x": -7, "y": 0, "vx": 0, "vy": 0, "fx": 0, "fy": 0},
            {"t": 1, "x": -6, "y": 0, "vx": 1, "vy": 0, "fx": 0, "fy": 0},
        ],
    }]
    scene = ReplayScene(mgr)
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    scene.draw(surface)
    assert calls == []


def test_the_flash_only_shows_while_it_lasts():
    events = [{"ability": "ability_boost", "name": "Boost", "t": 1.0, "x": 0.0, "y": 0.0}]
    assert len(afx.effects_at(events, 0.5)) == 0        # not yet
    assert len(afx.effects_at(events, 1.0)) == 1        # starts
    assert len(afx.effects_at(events, 1.5)) == 1        # still showing
    assert len(afx.effects_at(events, 1.0 + afx.ABILITY_FX_S)) == 0   # over
