"""Scene-level tests for the Function Community tab.

All network access is patched out; the scenes talk to
:mod:`vector_drift.account.community`, so the mocks go there.
"""

from types import SimpleNamespace

import pygame
import pytest

from vector_drift import config, data
from vector_drift.account import community as community_module
from vector_drift.function_library import SavedFunction
from vector_drift.scenes.base import SceneManager
from vector_drift.scenes.community_functions import CommunityFunctionsScene
from vector_drift.scenes.community_levels import CommunityLevelsScene

pytestmark = pytest.mark.usefixtures("pygame_display")


ROW = {
    "id": "f-remote-1", "user_id": "other", "uploader_name": "Bob",
    "function_name": "Vortex", "fx": "-y", "fy": "x",
    "created_at": "2026-10-02T10:00:00Z", "updated_at": "2026-10-02T10:00:00Z",
    "description": "spiral", "tags": ["vortex"],
    "usage_count": 10, "successful_usage_count": 8,
    "unique_user_count": 4, "favorite_count": 2, "rating_count": 1, "rating_total": 5,
}


def _audio():
    return SimpleNamespace(play=lambda *a, **k: None, start_loop=lambda *a, **k: None,
                           stop_loop=lambda *a, **k: None, update=lambda *a, **k: None,
                           set_music=lambda *a, **k: None, toggle_mute=lambda: None)


def _account(user_id="me", authenticated=True, name="Alice"):
    if not authenticated:
        return SimpleNamespace(is_authenticated=lambda: False,
                               is_configured=lambda: True,
                               current_user=None,
                               profile=None)
    return SimpleNamespace(
        is_authenticated=lambda: True,
        is_configured=lambda: True,
        current_user=SimpleNamespace(id=user_id, email=f"{user_id}@example.com", name=name),
        profile=SimpleNamespace(display_name=name),
    )


def _manager(account=None):
    return SceneManager(_audio(), account_manager=account or _account())


@pytest.fixture(autouse=True)
def _clean_registry():
    data.CUSTOM_LEVELS.clear()
    data.COMMUNITY_LEVELS.clear()
    yield
    data.CUSTOM_LEVELS.clear()
    data.COMMUNITY_LEVELS.clear()


def _scene(monkeypatch, account=None, rows=None):
    def fetch(on_success=None, on_error=None):
        if on_success:
            on_success(list(rows if rows is not None else [dict(ROW)]))

    monkeypatch.setattr(community_module, "fetch_community_functions", fetch)
    monkeypatch.setattr(community_module, "fetch_function_engagement",
                        lambda acc, on_success=None, on_error=None: on_success(
                            {"favorites": [], "ratings": {}}))
    return CommunityFunctionsScene(_manager(account=account))


def test_guests_can_browse_but_not_rate_or_favorite(monkeypatch):
    scene = _scene(monkeypatch, account=_account(authenticated=False))
    row = scene.levels[0]
    scene._toggle_favorite(row)
    scene._rate(row, 3)
    assert "log in" in scene.status.lower()
    # no engagement was submitted: the counters did not move client-side
    assert row["favorite_count"] == 2
    assert row["rating_count"] == 1


def test_favorite_toggle_updates_local_state(monkeypatch):
    scene = _scene(monkeypatch)
    calls = []

    def favorite(function_id, wanted, account, on_success=None, on_error=None):
        calls.append((function_id, wanted))
        if on_success:
            on_success()

    monkeypatch.setattr(community_module, "set_function_favorite", favorite)
    row = scene.levels[0]
    scene._toggle_favorite(row)
    assert calls == [("f-remote-1", True)]
    assert row["favorite_count"] == 3
    scene._toggle_favorite(row)
    assert calls[-1] == ("f-remote-1", False)
    assert row["favorite_count"] == 2


def test_first_and_change_rating_bookkeeping(monkeypatch):
    scene = _scene(monkeypatch)
    monkeypatch.setattr(community_module, "set_function_rating",
                        lambda *a, on_success=None, **k: on_success())
    row = scene.levels[0]
    scene._my_ratings[str(row["id"])] = 5     # pretend we already rated 5 stars
    scene._rate(row, 3)
    assert row["rating_count"] == 1          # a change, not a new rating
    assert row["rating_total"] == 3

    scene._my_ratings.clear()                # pretend we never rated
    scene._rate(row, 4)
    assert row["rating_count"] == 2
    assert row["rating_total"] == 7


def test_import_creates_an_attributed_unique_local_function(monkeypatch):
    scene = _scene(monkeypatch)
    mgr = scene.manager
    mgr.session.function_library = [SavedFunction(id="local1", name="Vortex", fx="0", fy="0")]
    scene._open_detail(dict(ROW))
    scene._open_import(scene._detail_row)
    assert scene._import_input.text == "Vortex (2)"
    scene._confirm_import()
    lib = mgr.session.function_library
    assert len(lib) == 2
    new = lib[1]
    assert (new.fx, new.fy) == ("-y", "x")
    assert new.source == "community" and new.community_id == "f-remote-1"
    assert mgr.session.function_library[0] == SavedFunction(id="local1", name="Vortex", fx="0", fy="0")


def test_import_rejects_broken_formulas_before_the_network(monkeypatch):
    scene = _scene(monkeypatch)
    scene._open_detail(dict(ROW, fx="x +"))
    scene._open_import(scene._detail_row)
    scene._confirm_import()
    assert "Cannot import" in scene._overlay_message
    assert scene.manager.session.function_library == []


def test_import_does_not_overwrite_a_same_named_local_function(monkeypatch):
    scene = _scene(monkeypatch)
    mgr = scene.manager
    mgr.session.function_library = [SavedFunction(id="p1", name="Vortex", fx="a", fy="b")]
    scene._open_detail(dict(ROW))
    scene._open_import(scene._detail_row)
    scene._confirm_import()
    names = [f.name for f in mgr.session.function_library]
    assert names == ["Vortex", "Vortex (2)"]


def test_edit_is_owner_only(monkeypatch):
    scene = _scene(monkeypatch, account=_account(user_id="me"))
    scene._edit(dict(ROW, id="x", user_id="someone-else"))
    assert scene._edit_mode is False
    assert "edit your own uploads" in scene.status


def test_update_pushes_only_content_columns(monkeypatch):
    scene = _scene(monkeypatch, account=_account(user_id="me"))
    captured = {}

    def update(function_id, account, **kwargs):
        captured["id"] = function_id
        captured.update(kwargs)
        kwargs["on_success"]()

    monkeypatch.setattr(community_module, "update_community_function", update)
    row = dict(ROW, id="mine-1", user_id="me")
    scene._open_detail(row, edit_mode=True)
    scene._edit_fields["name"].set_text("My Vortex")
    scene._edit_fields["tags"].set_text("a, b")
    scene._edit_fields["fx"].set_text("-y*2")
    scene._edit_fields["fy"].set_text("x*2")
    scene._save_edit()
    assert captured["id"] == "mine-1"
    assert captured["fx"] == "-y*2" and captured["fy"] == "x*2"
    assert captured["function_name"] == "My Vortex"
    assert tuple(captured["tags"]) == ("a", "b")


def test_tab_switching_round_trips(monkeypatch):
    level_rows = [{"id": "l1", "user_id": "u2", "uploader_name": "Ann",
                   "level_name": "Maze", "created_at": "2026-01-01T00:00:00Z",
                   "level_data": {"id": 7001, "name": "Maze", "start": [-7.0, 0.0],
                                  "target_center": [7.0, 0.0], "target_radius": 1.0}}]

    def fetch_levels(on_success=None, on_error=None):
        if on_success:
            on_success(list(level_rows))

    monkeypatch.setattr(community_module, "fetch_community_levels", fetch_levels)
    monkeypatch.setattr(community_module, "fetch_community_functions",
                        lambda on_success=None, on_error=None: on_success([dict(ROW)]))
    monkeypatch.setattr(community_module, "fetch_function_engagement",
                        lambda acc, on_success=None, on_error=None: on_success(
                            {"favorites": [], "ratings": {}}))
    mgr = _manager(_account())
    levels_scene = CommunityLevelsScene(mgr)
    mgr.switch(levels_scene)
    ev = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1,
                            pos=levels_scene.tab_functions.rect.center)
    levels_scene.handle_event(ev)
    assert isinstance(mgr.scene, CommunityFunctionsScene)
    back = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1,
                              pos=mgr.scene.tab_levels.rect.center)
    mgr.scene.handle_event(back)
    assert isinstance(mgr.scene, CommunityLevelsScene)


def test_delete_only_own_uploads_from_the_card(monkeypatch):
    scene = _scene(monkeypatch, account=_account(user_id="someone-else"))
    scene.levels = [dict(ROW, id="theirs", user_id="other")]
    scene._rebuild()
    scene._delete(scene.levels[0])
    assert scene.status == "You can only delete your own uploads."
