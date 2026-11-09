"""Tests for community-level cascade helpers in ``vector_drift.account.community``.

Covers the behaviour requested when an account is renamed, its data is cleared,
or a player-created level is deleted/modified: the matching community uploads
should be removed or updated (uploader name / level name / content) so they do
not stay stale or orphaned.
"""
from types import SimpleNamespace

from vector_drift.account import community as community_module


class _FakeTable:
    def __init__(self, rows):
        self._rows = rows
        self._op = None
        self._values = None
        self._filters = []

    def select(self, *cols):
        self._op = "select"
        self._cols = cols
        return self

    def delete(self):
        self._op = "delete"
        return self

    def update(self, values):
        self._op = "update"
        self._values = values
        return self

    def eq(self, col, val):
        self._filters.append((col, "eq", val))
        return self

    def filter(self, col, op, val):
        self._filters.append((col, op, val))
        return self

    def execute(self):
        matched = []
        for row in self._rows:
            ok = True
            for col, _op, val in self._filters:
                if col == "level_data->>id":
                    rv = str(row.get("level_data", {}).get("id"))
                else:
                    rv = row.get(col)
                if str(rv) != str(val):
                    ok = False
                    break
            if ok:
                matched.append(row)
        if self._op == "delete":
            for r in matched:
                self._rows.remove(r)
        elif self._op == "update":
            for r in matched:
                r.update(self._values)
        return SimpleNamespace(data=list(matched))


class _FakeClient:
    def __init__(self, rows):
        self._rows = rows

    def table(self, _name):
        return _FakeTable(self._rows)


def _install_fake_client(monkeypatch, rows):
    monkeypatch.setattr(community_module, "get_client", lambda: _FakeClient(rows))


def _sync_run_async(monkeypatch):
    """Make ``_run_async`` execute synchronously so callbacks run inline."""

    def fake(fn, on_success=None, on_error=None):
        try:
            result = fn()
        except Exception as exc:  # noqa: BLE001 - surface errors to the test
            if on_error is not None:
                on_error(exc)
            return
        if on_success is not None:
            on_success(result)

    monkeypatch.setattr(community_module, "_run_async", fake)


def _account(authenticated=True, user_id="u1"):
    acc = SimpleNamespace()
    if authenticated:
        acc.is_authenticated = lambda: True
        acc.current_user = SimpleNamespace(id=user_id, email=f"{user_id}@example.com")
    else:
        acc.is_authenticated = lambda: False
        acc.current_user = None
    return acc


def _rows():
    return [
        {
            "id": "r1",
            "user_id": "u1",
            "uploader_name": "Old",
            "level_name": "L1",
            "level_data": {"id": 7001, "name": "C1", "start": [-7.0, 0.0]},
        },
        {
            "id": "r2",
            "user_id": "u1",
            "uploader_name": "Old",
            "level_name": "L2",
            "level_data": {"id": 7002, "name": "C2", "start": [-7.0, 0.0]},
        },
        {
            "id": "r3",
            "user_id": "u2",
            "uploader_name": "Other",
            "level_name": "L3",
            "level_data": {"id": 7003, "name": "C3", "start": [-7.0, 0.0]},
        },
    ]


def test_delete_user_community_levels_removes_only_owner_rows(monkeypatch):
    rows = _rows()
    _install_fake_client(monkeypatch, rows)
    _sync_run_async(monkeypatch)
    acc = _account(authenticated=True, user_id="u1")
    captured = {}
    community_module.delete_user_community_levels(
        acc, on_success=lambda n: captured.setdefault("count", n)
    )
    assert captured["count"] == 2
    assert [r["id"] for r in rows] == ["r3"]


def test_delete_user_community_levels_requires_auth(monkeypatch):
    rows = _rows()
    _install_fake_client(monkeypatch, rows)
    _sync_run_async(monkeypatch)
    acc = _account(authenticated=False)
    captured = {}
    community_module.delete_user_community_levels(
        acc, on_error=lambda exc: captured.setdefault("err", exc)
    )
    assert "err" in captured
    assert len(rows) == 3  # nothing removed when not logged in


def test_update_community_levels_uploader_name_syncs_owner_rows(monkeypatch):
    rows = _rows()
    _install_fake_client(monkeypatch, rows)
    _sync_run_async(monkeypatch)
    acc = _account(authenticated=True, user_id="u1")
    community_module.update_community_levels_uploader_name(acc, "Renamed")
    assert rows[0]["uploader_name"] == "Renamed"
    assert rows[1]["uploader_name"] == "Renamed"
    assert rows[2]["uploader_name"] == "Other"


def test_update_community_levels_uploader_name_requires_auth(monkeypatch):
    rows = _rows()
    _install_fake_client(monkeypatch, rows)
    _sync_run_async(monkeypatch)
    acc = _account(authenticated=False)
    captured = {}
    community_module.update_community_levels_uploader_name(
        acc, "X", on_error=lambda exc: captured.setdefault("err", exc)
    )
    assert "err" in captured
    assert all(r["uploader_name"] != "X" for r in rows)


def test_delete_community_level_by_local_id(monkeypatch):
    rows = _rows()
    _install_fake_client(monkeypatch, rows)
    _sync_run_async(monkeypatch)
    acc = _account(authenticated=True, user_id="u1")
    community_module.delete_community_level_by_local_id(acc, 7001)
    assert {r["id"] for r in rows} == {"r2", "r3"}


def test_delete_community_level_by_local_id_respects_ownership(monkeypatch):
    rows = _rows()
    _install_fake_client(monkeypatch, rows)
    _sync_run_async(monkeypatch)
    acc = _account(authenticated=True, user_id="u1")
    community_module.delete_community_level_by_local_id(acc, 7003)
    assert len(rows) == 3


def test_update_community_level_by_local_id_syncs_name_and_content(monkeypatch):
    rows = _rows()
    _install_fake_client(monkeypatch, rows)
    _sync_run_async(monkeypatch)
    acc = _account(authenticated=True, user_id="u1")
    new_data = {"id": 7001, "name": "Edited", "start": [0.0, 0.0],
                "target_center": [7.0, 0.0], "target_radius": 1.0}
    community_module.update_community_level_by_local_id(acc, 7001, "Edited", new_data)
    assert rows[0]["level_name"] == "Edited"
    assert rows[0]["level_data"] == new_data
    assert rows[1]["level_name"] == "L2"
    assert rows[1]["level_data"]["name"] == "C2"


def test_update_community_level_by_local_id_respects_ownership(monkeypatch):
    rows = _rows()
    _install_fake_client(monkeypatch, rows)
    _sync_run_async(monkeypatch)
    acc = _account(authenticated=True, user_id="u1")
    new_data = {"id": 7003, "name": "Hacked"}
    community_module.update_community_level_by_local_id(acc, 7003, "Hacked", new_data)
    assert rows[2]["level_name"] == "L3"