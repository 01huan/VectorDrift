"""Extra security/robustness tests for community levels (appended)."""

from types import SimpleNamespace

import pygame

from vector_drift import config, data
from vector_drift.account import community as community_module
from vector_drift.scenes.base import SceneManager
import pytest

from vector_drift.scenes.community_levels import CommunityLevelsScene

pytestmark = pytest.mark.usefixtures("pygame_display")


def _manager(account=None):
    audio = SimpleNamespace(
        play=lambda *a, **k: None,
        start_loop=lambda *a, **k: None,
        stop_loop=lambda *a, **k: None,
        set_music=lambda *a, **k: None,
        toggle_mute=lambda *a, **k: None,
        update=lambda *a, **k: None,
    )
    return SceneManager(audio, account_manager=account)


def _scene(monkeypatch):
    def fetch(on_success=None, on_error=None):
        if on_success:
            on_success([])
    monkeypatch.setattr(community_module, "fetch_community_levels", fetch)
    return CommunityLevelsScene(_manager())


def test_register_custom_level_never_overwrites_builtin():
    before = data.get_level(1)
    spec = data.LevelSpec(
        id=1, name="Evil", start=(-7.0, 0.0), target_center=(7.0, 0.0),
        target_radius=1.0, ship_id="ship01",
    )
    try:
        data.register_custom_level(spec)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError on colliding id")
    after = data.get_level(1)
    assert after is before
    assert after.name == "First Drift"


def test_community_level_id_same_as_level_1_does_not_affect_level_1(monkeypatch):
    scene = _scene(monkeypatch)
    built_in_before = data.get_level(1)
    lvl = {"id": "evil-row", "level_data": {
        "id": 1, "name": "Evil", "start": [-7.0, 0.0],
        "target_center": [7.0, 0.0], "target_radius": 1.0,
    }}
    scene._open(lvl)
    assert data.get_level(1) is built_in_before
    assert data.get_level(1).name == "First Drift"
    assert 1 not in data.CUSTOM_LEVELS
    # The opened level uses a locally generated negative id.
    assert scene.manager.session.level_id < 0
    assert data.community_remote_id(scene.manager.session.level_id) == "evil-row"


def test_community_level_ids_are_stable_and_separate():
    a = data.community_level_id("row-a")
    b = data.community_level_id("row-a")
    c = data.community_level_id("row-b")
    assert a == b
    assert a != c
    assert a < 0 and c < 0


def test_draw_preview_invalid_data_does_not_crash(monkeypatch):
    scene = _scene(monkeypatch)
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    rect = pygame.Rect(0, 0, config.px(240), config.px(160))
    bad_cases = [
        {"level_data": {}},
        {"level_data": None},
        {"level_data": []},
        {"level_data": {"start": [float("nan"), 0.0], "target_center": [1.0, 0.0], "target_radius": 1.0}},
        {"level_data": {"start": [0.0, 0.0], "target_center": [1.0, 0.0], "target_radius": -1.0}},
        {"level_data": {"start": [0.0, 0.0], "target_center": [1.0, 0.0], "target_radius": 1.0,
                         "obstacles": [{"center": [0.0, 0.0], "radius": -1.0}]}},
        {"level_data": {"start": [0.0, 0.0], "target_center": [1.0, 0.0], "target_radius": 1.0,
                         "obstacles": "bad"}},
        {"level_data": {"start": [0.0, 0.0], "target_center": [1.0, 0.0], "target_radius": 1.0,
                         "time_limit": 1e9}},
        {"level_data": {"start": [0.0, 0.0], "target_center": [1.0, 0.0], "target_radius": 1.0,
                         "lives": 0}},
        {"level_data": {"start": [0.0, 0.0], "target_center": [1.0, 0.0], "target_radius": 1.0,
                         "obstacles": [{"center": [0.0, 0.0], "radius": 0.5, "kind": "nope"}]}},
    ]
    for lvl in bad_cases:
        scene._draw_preview(surface, lvl, rect)
    assert True


def test_open_invalid_data_does_not_register(monkeypatch):
    scene = _scene(monkeypatch)
    before = set(data.CUSTOM_LEVELS)
    lvl = {"level_data": {"id": 1, "start": [-7.0, 0.0],
                          "target_center": [7.0, 0.0], "target_radius": 1.0,
                          "obstacles": [{"center": [0.0, 0.0], "radius": -0.5}]}}
    scene._open(lvl)
    assert "Invalid level data" in scene.status
    assert set(data.CUSTOM_LEVELS) == before