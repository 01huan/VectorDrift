"""The explicit import actions of the community page.

Levels get an import button that saves a private copy into the player's
custom levels; functions import into the Function Lab library (see
``test_community_functions_scene.py`` for those).
"""

from types import SimpleNamespace

import pygame
import pytest

from vector_drift import data
from vector_drift.account import community as community_module
from vector_drift.scenes.base import SceneManager
from vector_drift.scenes.community_levels import CommunityLevelsScene

pytestmark = pytest.mark.usefixtures("pygame_display")


ROW = {
    "id": "l-remote-1", "user_id": "other", "uploader_name": "Bob",
    "level_name": "Meteor Maze", "created_at": "2026-10-01T10:00:00Z",
    "level_data": {"id": 4321, "name": "Meteor Maze", "start": [-7.0, 0.0],
                   "target_center": [7.0, 0.0], "target_radius": 1.0,
                   "time_limit": 10.0,
                   "obstacles": [{"center": [0.0, 0.0], "radius": 0.6}],
                   "pickups": []},
    "play_count": 3, "clear_count": 1, "clear_players": ["a"],
}


def _audio():
    return SimpleNamespace(play=lambda *a, **k: None, start_loop=lambda *a, **k: None,
                           stop_loop=lambda *a, **k: None, update=lambda *a, **k: None,
                           set_music=lambda *a, **k: None, toggle_mute=lambda: None)


def _manager(account=None):
    account = account or SimpleNamespace(
        is_authenticated=lambda: True,
        is_configured=lambda: True,
        current_user=SimpleNamespace(id="me", email="me@example.com", name="Alice"),
        profile=SimpleNamespace(display_name="Alice"),
    )
    return SceneManager(_audio(), account_manager=account)


@pytest.fixture(autouse=True)
def _clean_registry():
    data.CUSTOM_LEVELS.clear()
    data.COMMUNITY_LEVELS.clear()
    yield
    data.CUSTOM_LEVELS.clear()
    data.COMMUNITY_LEVELS.clear()


def _scene(monkeypatch, rows=None):
    def fetch(on_success=None, on_error=None):
        if on_success:
            on_success(list(rows if rows is not None else [dict(ROW)]))

    monkeypatch.setattr(community_module, "fetch_community_levels", fetch)
    return CommunityLevelsScene(_manager())


def test_import_saves_a_private_copy(monkeypatch):
    scene = _scene(monkeypatch)
    scene._toggle_favorite(scene.levels[0])          # the ↓ button imports
    session = scene.manager.session
    assert len(session.custom_levels) == 1
    copy = session.custom_levels[0]
    assert copy.name == "Meteor Maze"
    # the local copy always gets a fresh editor id, never the remote one
    assert copy.id != 4321
    assert copy.id >= 1000
    assert copy.id in session.custom_level_ids
    assert "Imported" in scene.status


def test_import_never_overwrites_the_original(monkeypatch):
    scene = _scene(monkeypatch)
    session = scene.manager.session
    before = len(data.CUSTOM_LEVELS)
    scene._toggle_favorite(scene.levels[0])
    scene._toggle_favorite(scene.levels[0])
    assert len(session.custom_levels) == 2
    assert len(data.CUSTOM_LEVELS) == before + 2
    ids = [spec.id for spec in session.custom_levels]
    assert len(set(ids)) == 2


def test_import_button_rects_exist_for_every_card(monkeypatch):
    scene = _scene(monkeypatch, rows=[dict(ROW, id=f"l-{index}") for index in range(3)])
    scene._rebuild()
    assert len(scene.favorite_rects) == len(scene.cards) == 3


def test_import_of_a_broken_row_does_not_touch_custom_levels(monkeypatch):
    scene = _scene(monkeypatch)
    session = scene.manager.session
    scene._toggle_favorite({"id": "broken", "level_data": {"id": "bad"}})
    assert session.custom_levels == []
    assert "Invalid level data" in scene.status
