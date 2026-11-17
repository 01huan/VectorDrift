"""Tests for the Level/Function community engagement loops.

Covers the favourite + rating machinery (mirroring functions for levels),
the "one player, one name" rule for community uploads and local libraries,
the local<->community sync of published functions, and usage attribution.

All network access goes through fakes.
"""

from types import SimpleNamespace

import pygame
import pytest

from vector_drift import data
from vector_drift.config import px
from vector_drift.account import community as community_module
from vector_drift.account import community_functions as cf
from vector_drift.scenes.base import SceneManager
from vector_drift.scenes.community_levels import CommunityLevelsScene
from vector_drift.scenes.function_lab import FunctionLabScene
from vector_drift.scenes.levels import LevelSelectScene
from vector_drift.function_library import SavedFunction, make_function

pytestmark = pytest.mark.usefixtures("pygame_display")

LEVEL_ROW = {
    "id": "l-remote-1", "user_id": "other", "uploader_name": "Bob",
    "level_name": "Nebula Drift", "created_at": "2026-10-02T10:00:00Z",
    "level_data": {"id": 7001, "name": "Nebula Drift", "start": [-7.0, 0.0],
                   "target_center": [7.0, 0.0], "target_radius": 1.0, "time_limit": 12.0,
                   "obstacles": [{"center": [0.0, 0.0], "radius": 0.6}],
                   "pickups": []},
    "play_count": 10, "clear_count": 3, "clear_players": ["a", "b"],
    "favorite_count": 2, "rating_count": 1, "rating_total": 5,
}

FUNCTION_ROW = {
    "id": "f-remote-1", "user_id": "someone-else", "uploader_name": "Bob",
    "function_name": "Vortex", "fx": "-y", "fy": "x",
    "created_at": "2026-10-02T10:00:00Z",
    "description": "", "tags": [],
    "usage_count": 10, "successful_usage_count": 8,
    "unique_user_count": 4, "favorite_count": 2, "rating_count": 1, "rating_total": 5,
}


# ------------------------------------------------------------- fake clients

class _FakeTable:
    def __init__(self, rows):
        self._rows = rows
        self._op = None
        self._payload = None
        self._filters = []
        self._select_cols = None

    def select(self, cols):
        self._op = "select"
        self._select_cols = cols
        return self

    def insert(self, payload):
        self._op = "insert"
        self._payload = payload
        return self

    def update(self, payload):
        self._op = "update"
        self._payload = payload
        return self

    def delete(self):
        self._op = "delete"
        return self

    def upsert(self, payload, on_conflict=None):
        self._op = "upsert"
        self._payload = payload
        self._on_conflict = on_conflict
        return self

    def eq(self, col, val):
        self._filters.append(("eq", col, val))
        return self

    def order(self, col, desc=False):
        return self

    def execute(self):
        matched = []
        for row in self._rows:
            ok = True
            for op, col, val in self._filters:
                if col == "level_data->>id":
                    rv = str((row.get("level_data") or {}).get("id"))
                else:
                    rv = row.get(col)
                if str(rv) != str(val):
                    ok = False
                    break
            if ok:
                matched.append(row)
        calls = getattr(self, "_client", None)
        if calls is not None:
            calls.append({"table": getattr(self, "_name", "?"), "op": self._op,
                          "payload": self._payload, "filters": list(self._filters),
                          "select": self._select_cols,
                          "on_conflict": getattr(self, "_on_conflict", None)})
        return SimpleNamespace(data=list(matched))


class _FakeClient:
    def __init__(self, rows):
        self.calls = []
        self._rows = rows

    def table(self, name):
        table = _FakeTable(self._rows)
        table._client = self.calls
        table._name = name
        return table


def _install_fake_client(monkeypatch, rows):
    client = _FakeClient(rows)
    monkeypatch.setattr(community_module, "get_client", lambda: client)
    return client


def _sync_run_async(monkeypatch):
    def fake(fn, on_success=None, on_error=None):
        try:
            result = fn()
        except Exception as exc:  # noqa: BLE001
            if on_error is not None:
                on_error(exc)
            return
        if on_success is not None:
            on_success(result)
    monkeypatch.setattr(community_module, "_run_async", fake)


def _account(authenticated=True, user_id="u1", name="Alice"):
    acc = SimpleNamespace()
    if authenticated:
        acc.is_authenticated = lambda: True
        acc.current_user = SimpleNamespace(id=user_id, email=f"{user_id}@example.com", name=name)
        acc.profile = SimpleNamespace(display_name=name)
    else:
        acc.is_authenticated = lambda: False
        acc.current_user = None
        acc.profile = None
    return acc


def _advance_enqueue(monkeypatch):
    """Fields owned by function_library stay genuine objects; nothing to do."""


def _level(row_id="7001", name="Maze"):
    return data.LevelSpec(id=int(row_id), name=name, start=(-7.0, 0.0),
                          target_center=(7.0, 0.0), target_radius=1.0,
                          ship_id="ship01")


# ============================================================ account layer

def test_set_level_favorite_upserts_then_deletes(monkeypatch):
    rows = [LEVEL_ROW]
    client = _install_fake_client(monkeypatch, rows)
    _sync_run_async(monkeypatch)
    community_module.set_level_favorite("l-remote-1", True, _account())
    community_module.set_level_favorite("l-remote-1", False, _account())
    ops = [(c["table"], c["op"]) for c in client.calls]
    assert ("community_level_favorites", "upsert") in ops
    assert ("community_level_favorites", "delete") in ops
    upsert = next(c for c in client.calls if c["op"] == "upsert")
    assert upsert["payload"] == {"user_id": "u1", "level_id": "l-remote-1"}
    assert ("eq", "user_id", "u1") in next(c for c in client.calls if c["op"] == "delete")["filters"]


def test_set_level_rating_validates(monkeypatch):
    rows = [LEVEL_ROW]
    client = _install_fake_client(monkeypatch, rows)
    _sync_run_async(monkeypatch)
    errors = []
    for bad in ("0", "6", -1, 7, "abc", True):
        community_module.set_level_rating("l-remote-1", bad, _account(),
                                          on_error=errors.append)
    assert len(errors) == 6
    assert [c for c in client.calls if c["op"] == "upsert"] == []


def test_set_level_rating_upserts_one_row_per_user_and_level(monkeypatch):
    rows = [LEVEL_ROW]
    client = _install_fake_client(monkeypatch, rows)
    _sync_run_async(monkeypatch)
    community_module.set_level_rating("l-remote-1", 4, _account())
    call = next(c for c in client.calls if c["op"] == "upsert")
    assert call["table"] == "community_level_ratings"
    assert call["payload"] == {"user_id": "u1", "level_id": "l-remote-1", "rating": 4}
    assert call["on_conflict"] == "user_id,level_id"


def test_fetch_level_engagement_parses_rows(monkeypatch):
    rows = [
        {"user_id": "u1", "level_id": "a"},
        {"user_id": "u1", "level_id": "b"},
    ]
    rating_rows = [
        {"user_id": "u1", "level_id": "a", "rating": "5"},
        {"user_id": "u1", "level_id": "b", "rating": 2},
        {"user_id": "u1", "level_id": "broken", "rating": "x"},
    ]

    class _EngagementTable(_FakeTable):
        def execute(self):
            calls = self._client
            if self._name == "community_level_favorites":
                rows_out = list(rows)
            elif self._name == "community_level_ratings":
                rows_out = list(rating_rows)
            else:
                rows_out = []
            calls.append({"table": self._name, "op": self._op})
            return SimpleNamespace(data=rows_out)

    class _EngagementClient(_FakeClient):
        def table(self, name):
            table = _EngagementTable([])
            table._client = self.calls
            table._name = name
            return table

    monkeypatch.setattr(community_module, "get_client",
                        lambda: _EngagementClient([]))

    def fake(fn, on_success=None, on_error=None):
        result = fn()
        if on_success is not None:
            on_success(result)

    monkeypatch.setattr(community_module, "_run_async", fake)
    results = []
    community_module.fetch_level_engagement(_account(), on_success=results.append)
    assert results == [{"favorites": ["a", "b"], "ratings": {"a": 5, "b": 2}}]


def test_upload_community_level_rejects_a_name_another_of_yours_owns(monkeypatch):
    rows = [
        {"id": "mine-other", "user_id": "u1", "uploader_name": "Alice",
         "level_name": "Maze", "level_data": {"id": 9999}},
    ]
    client = _install_fake_client(monkeypatch, rows)
    _sync_run_async(monkeypatch)
    errors = []
    community_module.upload_community_level(_account(), "Maze", {"id": 1234},
                                            on_error=errors.append)
    assert errors and "already have" in str(errors[0])
    assert not [c for c in client.calls if c["op"] in {"insert", "update"}]


def test_upload_community_level_same_local_id_updates_in_place(monkeypatch):
    rows = [
        {"id": "mine", "user_id": "u1", "uploader_name": "Alice",
         "level_name": "Maze", "level_data": {"id": 1234}},
    ]
    client = _install_fake_client(monkeypatch, rows)
    _sync_run_async(monkeypatch)
    community_module.upload_community_level(_account(), "Maze", {"id": 1234})
    updates = [c for c in client.calls if c["op"] == "update"]
    assert updates and ("eq", "id", "mine") in updates[0]["filters"]


def test_upload_community_level_name_is_fine_for_another_player(monkeypatch):
    rows = [
        {"id": "theirs", "user_id": "u2", "uploader_name": "Bob",
         "level_name": "Maze", "level_data": {"id": 9999}},
    ]
    client = _install_fake_client(monkeypatch, rows)
    _sync_run_async(monkeypatch)
    community_module.upload_community_level(_account(), "Maze", {"id": 1234})
    inserts = [c for c in client.calls if c["op"] == "insert"]
    assert inserts and inserts[0]["payload"]["level_name"] == "Maze"


def test_upload_community_function_rejects_name_for_different_formulas(monkeypatch):
    fake_rows = [
        {"id": "mine-other", "user_id": "u1", "function_name": "Vortex",
         "fx": "1", "fy": "0"},
    ]
    _install_fake_for_functions(monkeypatch, fake_rows)
    errors = []
    cf.upload_community_function(_account(), "Vortex", "-y", "x", on_error=errors.append)
    assert errors and "already have" in str(errors[0])


def _install_fake_for_functions(monkeypatch, rows):
    client = _FakeClient(rows)
    monkeypatch.setattr(cf, "get_client", lambda: client)

    def fake(fn, on_success=None, on_error=None):
        try:
            result = fn()
        except Exception as exc:  # noqa: BLE001
            if on_error is not None:
                on_error(exc)
            return
        if on_success is not None:
            on_success(result)

    monkeypatch.setattr(cf, "_run_async", fake)
    return client


def test_upload_community_function_update_in_place_keeps_the_name(monkeypatch):
    fake_rows = [
        {"id": "mine", "user_id": "u1", "function_name": "Vortex",
         "fx": "-y", "fy": "x"},
    ]
    client = _install_fake_for_functions(monkeypatch, fake_rows)
    cf.upload_community_function(_account(), "Vortex", "-y", "x", community_id="mine")
    updates = [c for c in client.calls if c["op"] == "update"]
    assert updates and ("eq", "id", "mine") in updates[0]["filters"]


def test_upload_community_function_rejects_rename_into_another_own_row(monkeypatch):
    fake_rows = [
        {"id": "mine", "user_id": "u1", "function_name": "Vortex",
         "fx": "-y", "fy": "x"},
        {"id": "mine-2", "user_id": "u1", "function_name": "Orbit",
         "fx": "1", "fy": "1"},
    ]
    client = _install_fake_for_functions(monkeypatch, fake_rows)
    errors = []
    cf.upload_community_function(_account(), "Orbit", "1", "1",
                                 community_id="mine", on_error=errors.append)
    assert errors and "already have" in str(errors[0])
    updates = [c for c in client.calls if c["op"] == "update"]
    assert not updates


def test_update_community_function_rejects_rename_into_another_own_row(monkeypatch):
    fake_rows = [
        {"id": "mine", "user_id": "u1", "function_name": "Vortex"},
        {"id": "mine-2", "user_id": "u1", "function_name": "Orbit"},
    ]
    _install_fake_for_functions(monkeypatch, fake_rows)
    errors = []
    cf.update_community_function("mine-2", _account(), function_name="Vortex",
                                 on_error=errors.append)
    assert errors and "already have" in str(errors[0])


# ================================================================= scenes

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


def _level_scene(monkeypatch, rows=None, account=None):
    def fetch(on_success=None, on_error=None):
        if on_success is not None:
            on_success(list(rows if rows is not None else [dict(LEVEL_ROW)]))

    monkeypatch.setattr(community_module, "fetch_community_levels", fetch)
    monkeypatch.setattr(community_module, "fetch_level_engagement",
                        lambda acc, on_success=None, on_error=None: on_success(
                            {"favorites": [], "ratings": {}}))
    return CommunityLevelsScene(_manager(account=account or _account()))


def test_level_favorite_toggle_updates_local_state(monkeypatch):
    scene = _level_scene(monkeypatch)
    calls = []

    def favorite(row_id, wanted, account, on_success=None, on_error=None):
        calls.append((row_id, wanted))
        if on_success:
            on_success()

    monkeypatch.setattr(community_module, "set_level_favorite", favorite)
    row = scene.levels[0]
    scene._toggle_favorite(row)
    assert calls == [("l-remote-1", True)]
    assert row["favorite_count"] == 3
    scene._toggle_favorite(row)
    assert calls[-1] == ("l-remote-1", False)
    assert row["favorite_count"] == 2


def test_level_guests_cannot_favorite_or_rate(monkeypatch):
    scene = _level_scene(monkeypatch, account=_account(authenticated=False))
    row = scene.levels[0]
    scene._toggle_favorite(row)
    scene._rate(row, 3)
    assert "log in" in scene.status.lower()
    assert row["favorite_count"] == 2
    assert row["rating_count"] == 1


def test_level_first_and_change_rating_bookkeeping(monkeypatch):
    scene = _level_scene(monkeypatch)
    monkeypatch.setattr(community_module, "set_level_rating",
                        lambda *a, on_success=None, **k: on_success())
    row = scene.levels[0]
    scene._my_ratings[str(row["id"])] = 5
    scene._rate(row, 3)
    assert row["rating_count"] == 1          # a change, not a new rating
    assert row["rating_total"] == 3

    scene._my_ratings.clear()                # never rated
    scene._rate(row, 4)
    assert row["rating_count"] == 2
    assert row["rating_total"] == 7


def test_level_star_button_click_rates_the_row(monkeypatch):
    scene = _level_scene(monkeypatch)
    rated = []
    monkeypatch.setattr(community_module, "set_level_rating",
                        lambda row_id, stars, account, on_success=None, on_error=None:
                        (rated.append((row_id, stars)), on_success()))
    scene._rebuild()
    stars = scene.star_rects[0]
    assert stars and len(stars) == 5
    target = stars[2]                        # third star -> 3 of 5
    ev = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=target.center)
    scene.handle_event(ev)
    assert rated == [("l-remote-1", 3)]


def test_level_import_uses_a_unique_local_name(monkeypatch):
    monkeypatch.setattr(data, "LEVELS", list(data.LEVELS))
    monkeypatch.setattr(data, "CUSTOM_LEVELS", dict(data.CUSTOM_LEVELS))
    scene = _level_scene(monkeypatch)
    mgr = scene.manager
    mgr.session.custom_levels = [_level("8101", "Nebula Drift")]
    mgr.session.custom_level_ids = {8101}
    scene._import_action(scene.levels[0])
    names = [lv.name for lv in mgr.session.custom_levels]
    assert names == ["Nebula Drift", "Nebula Drift (2)"]


def test_level_favorite_button_rects_follow_ownership(monkeypatch):
    rows = [dict(LEVEL_ROW, id="mine", user_id="me"),
            dict(LEVEL_ROW, id="theirs", user_id="u2")]
    scene = _level_scene(monkeypatch, rows=rows, account=_account(user_id="me"))
    scene._rebuild()
    assert scene.favorite_rects[0].x == scene.cards[0][1].right - px(78)
    assert scene.favorite_rects[1].x == scene.cards[1][1].right - px(26)


# ====================================================== functions: the lab

def _lab_manager(account=None):
    audio = SimpleNamespace(
        play=lambda *a, **k: None,
        start_loop=lambda *a, **k: None,
        stop_loop=lambda *a, **k: None,
        set_music=lambda *a, **k: None,
        toggle_mute=lambda *a, **k: None,
        update=lambda *a, **k: None,
    )
    return SceneManager(audio, account_manager=account)


def _lab_scene(monkeypatch, account=None):
    from vector_drift.scenes import function_lab as lab_module
    return FunctionLabScene(_lab_manager(account=account or _account()))


def test_function_lab_rejects_a_duplicate_name_on_save(monkeypatch):
    scene = _lab_scene(monkeypatch)
    mgr = scene.manager
    mgr.session.function_library = [make_function("vortex", "1", "1")]
    scene.editor.set_lines(["-y", "x"])
    scene.name_input.set_text("vortex")
    saved = scene._save()
    assert saved is False
    assert "already exists" in scene.message
    assert len(mgr.session.function_library) == 1


def test_function_lab_saving_other_name_works(monkeypatch):
    scene = _lab_scene(monkeypatch)
    mgr = scene.manager
    mgr.session.function_library = [make_function("vortex", "1", "1")]
    scene.editor.set_lines(["-y", "x"])
    scene.name_input.set_text("orbit")
    assert scene._save() is True
    assert [f.name for f in mgr.session.function_library] == ["vortex", "orbit"]


def test_function_lab_delete_removes_the_community_copy(monkeypatch):
    account = _account()
    scene = _lab_scene(monkeypatch, account=account)
    mgr = scene.manager
    published = SavedFunction(id="local-1", name="vortex", fx="-y", fy="x",
                              community_id="remote-1")
    mgr.session.function_library = [published]
    deleted = []

    def delete(function_id=None, account=None, on_success=None, on_error=None, **kwargs):
        deleted.append((function_id, account))
        if on_success:
            on_success()

    monkeypatch.setattr(community_module, "delete_community_function", delete)
    scene._delete(published)
    assert deleted == [("remote-1", account)]
    assert mgr.session.function_library == []


def test_function_lab_save_syncs_a_published_function(monkeypatch):
    account = _account()
    scene = _lab_scene(monkeypatch, account=account)
    mgr = scene.manager
    published = SavedFunction(id="local-1", name="vortex", fx="-y", fy="x",
                              community_id="remote-1")
    mgr.session.function_library = [published]
    synced = []

    def update(function_id, account, **kwargs):
        synced.append((function_id, kwargs))
        if kwargs.get("on_success"):
            kwargs["on_success"]()

    monkeypatch.setattr(community_module, "update_community_function", update)
    scene.editing_id = "local-1"
    scene.editor.set_lines(["-y", "x"])
    scene.name_input.set_text("vortex")
    scene.desc_input.set_text("")
    scene.tags_input.set_text("")
    assert scene._save() is True
    assert synced and synced[0][0] == "remote-1"
    assert synced[0][1]["function_name"] == "vortex"
    assert synced[0][1]["fx"] == "-y"


# ======================================================= functions: usage

def _audio():
    return SimpleNamespace(play=lambda *a, **k: None, start_loop=lambda *a, **k: None,
                           stop_loop=lambda *a, **k: None, update=lambda *a, **k: None,
                           set_music=lambda *a, **k: None, toggle_mute=lambda: None)


def test_picking_a_saved_function_marks_it_for_usage_counting(monkeypatch):
    from vector_drift.scenes.game_functions import load
    scene = SimpleNamespace()
    scene.session = SceneManager(_audio()).session
    scene.editor = SimpleNamespace(
        lines=["-y", "x"], set_lines=lambda lines: setattr(scene.editor, "lines", lines))
    scene.lab_popup = True
    scene._on_text_change = lambda editor: None
    scene.lab_page = 0
    community_function = SavedFunction(id="imp-1", name="vortex", fx="-y", fy="x",
                                      community_id="remote-1")
    load(scene, community_function)
    assert scene.session.imported_function_id == "imp-1"


def test_load_marks_imported_id_chosen_in_the_popup(monkeypatch):
    # the community usage pipeline keys off imported_function_id: make sure
    # picking from the in-game library registers it
    from vector_drift.scenes.game_functions import load
    scene = SimpleNamespace()
    scene.session = SceneManager(_audio()).session
    scene.session.function_library = [make_function("own", "1", "1")]
    scene.editor = SimpleNamespace(
        lines=["1", "1"], set_lines=lambda lines: setattr(scene.editor, "lines", lines))
    scene.lab_popup = True
    scene._on_text_change = lambda editor: None
    scene.lab_page = 0
    target = scene.session.function_library[0]
    load(scene, target)
    assert scene.session.imported_function_id == target.id


# ========================================================== unique names

def test_unique_level_name_suffixes_until_free():
    existing = [_level("8101", "Maze"), _level("8102", "Maze (2)")]
    assert data.unique_level_name("Maze", existing) == "Maze (3)"
    assert data.unique_level_name("New Name", existing) == "New Name"


def test_unique_level_name_is_case_insensitive():
    existing = [_level("8101", "Maze")]
    assert data.unique_level_name("maze", existing) == "maze (2)"
