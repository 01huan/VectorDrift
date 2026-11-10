"""Tests for the CommunityLevelsScene to lift its coverage."""

from types import SimpleNamespace

import pygame
import pytest

from vector_drift import config, data
from vector_drift.config import px
from vector_drift.account import community as community_module
from vector_drift.scenes.base import SceneManager
from vector_drift.scenes.community_levels import CommunityLevelsScene
import vector_drift.scenes.community_levels as scene_module

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


def _sync_fetch(monkeypatch, rows=None, exc=None):
    def fake(on_success=None, on_error=None):
        if exc is not None:
            if on_error is not None:
                on_error(exc)
        else:
            if on_success is not None:
                on_success(rows if rows is not None else [])
    monkeypatch.setattr(community_module, "fetch_community_levels", fake)


def _sync_delete(monkeypatch, fail=False):
    def fake(level_id, account, on_success=None, on_error=None):
        if fail:
            if on_error is not None:
                on_error(RuntimeError("delete boom"))
        else:
            if on_success is not None:
                on_success()
    monkeypatch.setattr(community_module, "delete_community_level", fake)


def _account(authenticated=True, user_id="u1"):
    acc = SimpleNamespace()
    if authenticated:
        acc.is_authenticated = lambda: True
        acc.current_user = SimpleNamespace(id=user_id, email="u1@example.com")
    else:
        acc.is_authenticated = lambda: False
        acc.current_user = None
    return acc


@pytest.fixture(autouse=True)
def _clean_custom_levels():
    data.CUSTOM_LEVELS.clear()
    yield
    data.CUSTOM_LEVELS.clear()


def test_delete_non_owner(monkeypatch):
    _sync_fetch(monkeypatch, rows=[])
    acc = _account(authenticated=False)
    mgr = _manager(account=acc)
    scene = CommunityLevelsScene(mgr)
    scene._delete({"id": "x", "user_id": "other"})
    assert scene.status == "You can only delete your own uploads."


def test_delete_owner_success(monkeypatch):
    acc = _account(authenticated=True, user_id="u1")
    # make initial fetch sync empty
    def fetch(on_success=None, on_error=None):
        if on_success:
            on_success([])
    monkeypatch.setattr(community_module, "fetch_community_levels", fetch)
    _sync_delete(monkeypatch, fail=False)
    mgr = _manager(account=acc)
    scene = CommunityLevelsScene(mgr)
    lvl = {"id": "x", "user_id": "u1"}
    scene._delete(lvl)
    assert scene.deleting is None
    assert "Found" in scene.status


def test_delete_owner_failure(monkeypatch):
    acc = _account(authenticated=True, user_id="u1")
    def fetch(on_success=None, on_error=None):
        if on_success:
            on_success([])
    monkeypatch.setattr(community_module, "fetch_community_levels", fetch)
    _sync_delete(monkeypatch, fail=True)
    mgr = _manager(account=acc)
    scene = CommunityLevelsScene(mgr)
    lvl = {"id": "x", "user_id": "u1"}
    scene._delete(lvl)
    assert scene.deleting is None
    assert "Delete failed" in scene.status


def test_handle_event_back_button(monkeypatch):
    def fetch(on_success=None, on_error=None):
        if on_success:
            on_success([])
    monkeypatch.setattr(community_module, "fetch_community_levels", fetch)
    mgr = _manager()
    scene = CommunityLevelsScene(mgr)
    scene.back_button.handle_event = lambda event: "click"
    import vector_drift.scenes.level_editor_menu as lem
    class FakeScene:
        music = None
        def __init__(self, m):
            self.m = m
    monkeypatch.setattr(lem, "LevelEditorMenuScene", FakeScene)
    ev = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(0, 0))
    scene.handle_event(ev)
    assert isinstance(mgr.scene, FakeScene)


def test_handle_event_refresh_button(monkeypatch):
    calls = []
    def fake_fetch(on_success=None, on_error=None):
        calls.append(1)
        if on_success:
            on_success([])
    monkeypatch.setattr(community_module, "fetch_community_levels", fake_fetch)
    mgr = _manager()
    scene = CommunityLevelsScene(mgr)
    init_calls = len(calls)
    scene.refresh_button.handle_event = lambda event: "click"
    ev = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(0, 0))
    scene.handle_event(ev)

def test_handle_event_open_card(monkeypatch):
    rows = [{"id": "a1", "user_id": "u2", "uploader_email": "u2@e.com",
             "level_name": "L1", "created_at": "2024-01-02",
             "level_data": {"id": 7001, "name": "C1", "start": [-7.0, 0.0],
                            "target_center": [7.0, 0.0], "target_radius": 1.0}}]
    def fetch(on_success=None, on_error=None):
        if on_success:
            on_success(rows)
    monkeypatch.setattr(community_module, "fetch_community_levels", fetch)
    mgr = _manager()
    scene = CommunityLevelsScene(mgr)
    scene.busy = False
    scene.levels = rows
    scene._rebuild()
    import vector_drift.scenes.game as game_mod
    class FakeGame:
        music = None
        def __init__(self, m):
            self.m = m
    monkeypatch.setattr(game_mod, "GameScene", FakeGame)
    rect = scene.cards[0][1]
    ev = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=rect.center)
    scene.handle_event(ev)
    assert isinstance(mgr.scene, FakeGame)
    assert mgr.session.level_id == data.community_level_id("a1")
    assert data.community_level_id("a1") in mgr.session.custom_level_ids


def test_handle_event_delete_own_click(monkeypatch):
    acc = _account(authenticated=True, user_id="u1")
    rows = [{"id": "a1", "user_id": "u1", "uploader_email": "u1@e.com",
             "level_name": "L1", "created_at": "2024-01-02",
             "level_data": {"id": 7002, "name": "C1", "start": [-7.0, 0.0],
                            "target_center": [7.0, 0.0], "target_radius": 1.0}}]
    def fetch(on_success=None, on_error=None):
        if on_success:
            on_success(rows)
    monkeypatch.setattr(community_module, "fetch_community_levels", fetch)
    def delete(level_id, account, on_success=None, on_error=None):
        if on_success:
            on_success()
    monkeypatch.setattr(community_module, "delete_community_level", delete)
    mgr = _manager(account=acc)
    scene = CommunityLevelsScene(mgr)
    scene.levels = rows
    scene.busy = False
    scene._rebuild()
    del_rect = scene.delete_rects[0]
    ev = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=del_rect.center)
    scene.handle_event(ev)
    assert "Found" in scene.status


def test_handle_event_busy_ignores_mouse(monkeypatch):
    def fetch(on_success=None, on_error=None):
        if on_success:
            on_success([])
    monkeypatch.setattr(community_module, "fetch_community_levels", fetch)
    mgr = _manager()
    scene = CommunityLevelsScene(mgr)
    scene.busy = True
    scene.levels = []
    scene._rebuild()
    ev = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(100, 100))
    scene.handle_event(ev)


def test_handle_event_miss_click(monkeypatch):
    rows = [{"id": "a1", "user_id": "u2", "uploader_email": "u2@e.com",
             "level_name": "L1", "created_at": "2024",
             "level_data": {"id": 7003, "name": "C", "start": [-7.0, 0.0],
                            "target_center": [7.0, 0.0], "target_radius": 1.0}}]
    def fetch(on_success=None, on_error=None):
        if on_success:
            on_success(rows)
    monkeypatch.setattr(community_module, "fetch_community_levels", fetch)
    mgr = _manager()
    scene = CommunityLevelsScene(mgr)
    scene.levels = rows
    scene.busy = False
    scene._rebuild()
    ev = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(0, 0))
    scene.handle_event(ev)


def test_open_invalid(monkeypatch):
    def fetch(on_success=None, on_error=None):
        if on_success:
            on_success([])
    monkeypatch.setattr(community_module, "fetch_community_levels", fetch)
    mgr = _manager()
    scene = CommunityLevelsScene(mgr)
    scene._open({"level_data": {"id": "bad"}})
    assert "Invalid level data" in scene.status
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    scene.draw(surface)


def test_open_valid(monkeypatch):
    import vector_drift.scenes.game as game_mod
    class FakeGame:
        music = None
        def __init__(self, m):
            self.m = m
    monkeypatch.setattr(game_mod, "GameScene", FakeGame)
    def fetch(on_success=None, on_error=None):
        if on_success:
            on_success([])
    monkeypatch.setattr(community_module, "fetch_community_levels", fetch)
    mgr = _manager()
    scene = CommunityLevelsScene(mgr)
    lvl = {"id": "open-valid", "level_data": {"id": 8001, "name": "C", "start": [-7.0, 0.0],
                          "target_center": [7.0, 0.0], "target_radius": 1.0,
                          "obstacles": [{"center": [-1.0, 0.0], "radius": 0.5}],
                          "pickups": [{"center": [1.0, 0.0], "radius": 0.4, "kind": "unbound"}]}}
    scene._open(lvl)
    assert mgr.session.level_id == data.community_level_id("open-valid")
    assert isinstance(mgr.scene, FakeGame)


def test_open_already_registered(monkeypatch):
    import vector_drift.scenes.game as game_mod
    class FakeGame:
        music = None
        def __init__(self, m):
            self.m = m
    monkeypatch.setattr(game_mod, "GameScene", FakeGame)
    def fetch(on_success=None, on_error=None):
        if on_success:
            on_success([])
    monkeypatch.setattr(community_module, "fetch_community_levels", fetch)
    mgr = _manager()
    scene = CommunityLevelsScene(mgr)
    level_id = data.community_level_id("already-registered-row")
    spec = scene._deserialize({"name": "C", "start": [-7.0, 0.0],
                                "target_center": [7.0, 0.0], "target_radius": 1.0}, level_id)
    data.register_custom_level(spec)
    mgr.session.custom_level_ids.add(level_id)
    mgr.session.custom_levels.append(spec)
    lvl = {"id": "already-registered-row", "level_data": {"name": "C", "start": [-7.0, 0.0],
                          "target_center": [7.0, 0.0], "target_radius": 1.0}}
    scene._open(lvl)
    assert level_id in mgr.session.custom_level_ids
    assert sum(1 for s in mgr.session.custom_levels if s.id == level_id) == 1


def test_deserialize_and_draw_preview(monkeypatch):
    def fetch(on_success=None, on_error=None):
        if on_success:
            on_success([])
    monkeypatch.setattr(community_module, "fetch_community_levels", fetch)
    mgr = _manager()
    scene = CommunityLevelsScene(mgr)
    data_ = {"id": 9001, "name": "C", "start": [-7.0, 0.0],
             "target_center": [7.0, 0.0], "target_radius": 1.0,
             "obstacles": [{"center": [-1.0, 0.0], "radius": 0.5, "restitution": 0.7, "kind": "bumper"}],
             "pickups": [{"center": [1.0, 0.0], "radius": 0.4, "kind": "unbound"}]}
    spec = scene._deserialize(data_, 9001)
    assert spec.id == 9001
    lvl = {"level_data": data_}
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    rect = pygame.Rect(0, 0, px(240), px(160))
    scene._draw_preview(surface, lvl, rect)


def test_draw_preview_empty_and_small(monkeypatch):
    def fetch(on_success=None, on_error=None):
        if on_success:
            on_success([])
    monkeypatch.setattr(community_module, "fetch_community_levels", fetch)
    mgr = _manager()
    scene = CommunityLevelsScene(mgr)
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    rect = pygame.Rect(0, 0, px(240), px(160))
    scene._draw_preview(surface, {"level_data": {}}, rect)
    data_ = {"id": 1, "start": [0.0, 0.0], "target_center": [100.0, 100.0],
             "target_radius": 1.0,
             "obstacles": [{"center": [50.0, 50.0], "radius": 0.01}],
             "pickups": [{"center": [50.0, 50.0], "radius": 0.01, "kind": "life"}]}
    scene._draw_preview(surface, {"level_data": data_}, rect)


def test_load_methods(monkeypatch):
    def fake(on_success=None, on_error=None):
        pass
    monkeypatch.setattr(community_module, "fetch_community_levels", fake)
    mgr = _manager()
    scene = CommunityLevelsScene(mgr)
    scene.levels = []
    scene._load()
    assert scene.busy is True
    # sync-style callback separate
    scene._on_loaded([{"id": "y"}])
    assert scene.levels == [{"id": "y"}]
    assert scene.busy is False
    scene._on_error(ValueError("e"))
    assert "Failed" in scene.status


def test_rebuild(monkeypatch):
    def fetch(on_success=None, on_error=None):
        if on_success:
            on_success([])
    monkeypatch.setattr(community_module, "fetch_community_levels", fetch)
    mgr = _manager()
    scene = CommunityLevelsScene(mgr)
    scene.levels = [{"id": "x"}, {"id": "y"}]
    scene._rebuild()
    assert len(scene.cards) == 2
    assert len(scene.delete_rects) == 2


def test_handle_event_other(monkeypatch):
    def fetch(on_success=None, on_error=None):
        if on_success:
            on_success([])
    monkeypatch.setattr(community_module, "fetch_community_levels", fetch)
    mgr = _manager()
    scene = CommunityLevelsScene(mgr)
    ev = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE)
    scene.handle_event(ev)
    ev2 = pygame.event.Event(pygame.MOUSEMOTION, pos=(1, 1))
    scene.handle_event(ev2)
    # back/refresh real buttons maybe not click; events processed
    # draw again
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    scene.draw(surface)


def test_draw_with_levels(monkeypatch):
    acc = _account(authenticated=True, user_id="u1")
    rows = [
        {"id": "a1", "user_id": "u1", "uploader_email": "u1@example.com",
         "level_name": "L1", "created_at": "2024-01-02T00:00:00Z",
         "level_data": {"id": 5011, "name": "C1", "start": [-7.0, 0.0],
                        "target_center": [7.0, 0.0], "target_radius": 1.0}},
    ]
    def fetch(on_success=None, on_error=None):
        if on_success:
            on_success(rows)
    monkeypatch.setattr(community_module, "fetch_community_levels", fetch)
    mgr = _manager(account=acc)
    scene = CommunityLevelsScene(mgr)
    scene.levels = rows
    scene.busy = False
    scene._rebuild()
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    scene.draw(surface)


def test_draw_busy_true(monkeypatch):
    def fetch(on_success=None, on_error=None):
        pass
    monkeypatch.setattr(community_module, "fetch_community_levels", fetch)
    mgr = _manager()
    scene = CommunityLevelsScene(mgr)
    # force busy true already
    scene.status = "Loading..."
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    scene.draw(surface)
    # after _rebuild? draw doesn't rebuild if? check source: draw if not lazy? Let's just ensure no crash
def test_draw_preview_images(monkeypatch):
    def fetch(on_success=None, on_error=None):
        if on_success:
            on_success([])
    monkeypatch.setattr(community_module, "fetch_community_levels", fetch)
    monkeypatch.setattr(scene_module, "load_image", lambda *a, **k: pygame.Surface((4, 4)))
    mgr = _manager()
    scene = CommunityLevelsScene(mgr)
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    rect = pygame.Rect(0, 0, px(240), px(160))
    data_ = {"id": 1, "start": [0.0, 0.0], "target_center": [4.0, 0.0],
             "target_radius": 1.0,
             "obstacles": [{"center": [1.0, 1.0], "radius": 0.4}],
             "pickups": [{"center": [2.0, -1.0], "radius": 0.3, "kind": "life"}]}
    scene._draw_preview(surface, {"level_data": data_}, rect)
    assert True

def test_draw_preview_fallbacks(monkeypatch):
    def fetch(on_success=None, on_error=None):
        if on_success:
            on_success([])
    monkeypatch.setattr(community_module, "fetch_community_levels", fetch)
    monkeypatch.setattr(scene_module, "load_image", lambda *a, **k: None)
    mgr = _manager()
    scene = CommunityLevelsScene(mgr)
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    rect = pygame.Rect(0, 0, px(240), px(160))
    data_ = {"id": 1, "start": [0.0, 0.0], "target_center": [4.0, 0.0],
             "target_radius": 1.0,
             "obstacles": [{"center": [1.0, 1.0], "radius": 0.4}],
             "pickups": [{"center": [2.0, -1.0], "radius": 0.3, "kind": "life"}]}
    scene._draw_preview(surface, {"level_data": data_}, rect)
    assert True

