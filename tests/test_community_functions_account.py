"""Tests for the community Function data layer (Supabase).

The database calls go through a fake client so the exact queries, payloads
and ownership guards can be checked without a network.
"""

from types import SimpleNamespace

import pytest

from vector_drift.account import community as community_module
from vector_drift.account import community_functions as cf


class _FakeTable:
    """Records operations; returns canned rows for the select that checks for
    an existing upload."""

    def __init__(self, client, name):
        self.client = client
        self.name = name
        self._op = None
        self._payload = None
        self._filters = []
        self._select_cols = None
        self._order = None
        self._upsert_conflict = None

    # query builders -------------------------------------------------
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
        self._upsert_conflict = on_conflict
        return self

    def eq(self, col, val):
        self._filters.append(("eq", col, val))
        return self

    def order(self, col, desc=False):
        self._order = (col, desc)
        return self

    def execute(self):
        self.client.calls.append({
            "table": self.name,
            "op": self._op,
            "payload": self._payload,
            "filters": list(self._filters),
            "select": self._select_cols,
            "order": self._order,
            "on_conflict": self._upsert_conflict,
        })
        if self._op == "select":
            if self.name == "community_functions" and self._select_cols == "id":
                return SimpleNamespace(data=[])     # no existing row: falls back to insert
            if self._op == "select" and self._select_cols and "description" in str(self._select_cols):
                raise RuntimeError("column description does not exist")
            return SimpleNamespace(data=[{"id": "r1"}])
        return SimpleNamespace(data=[{"id": "r1"}])


class _FakeRpc:
    def __init__(self, client, name, params):
        self.client = client
        self.name = name
        self.params = params

    def execute(self):
        self.client.calls.append({"rpc": self.name, "params": self.params})
        return SimpleNamespace(data=None)


class _FakeClient:
    def __init__(self):
        self.calls = []

    def table(self, name):
        return _FakeTable(self, name)

    def rpc(self, name, params):
        return _FakeRpc(self, name, params)


@pytest.fixture
def fake_client(monkeypatch):
    client = _FakeClient()
    monkeypatch.setattr(cf, "get_client", lambda: client)
    return client


@pytest.fixture
def sync_async(monkeypatch):
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
    return fake


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


# --- fetching ---------------------------------------------------------------

def test_fetch_asks_for_the_statistics_columns(fake_client, sync_async):
    cf.fetch_community_functions(on_success=lambda rows: None)
    call = fake_client.calls[0]
    assert call["table"] == "community_functions"
    assert "usage_count" in call["select"]
    assert "favorite_count" in call["select"]
    assert "rating_total" in call["select"]
    assert call["order"] == ("created_at", True)


def test_fetch_falls_back_on_an_older_database(fake_client, sync_async):
    calls = []
    cf.fetch_community_functions(on_success=calls.append)
    assert len(calls) == 1
    selects = [c["select"] for c in fake_client.calls]
    assert any("usage_count" not in s for s in selects)


# --- publishing ---------------------------------------------------------------

def test_upload_requires_authentication(fake_client, sync_async):
    errors = []
    cf.upload_community_function(_account(authenticated=False), "n", "x", "y",
                                 on_error=errors.append)
    assert errors and "log in" in str(errors[0]).lower()
    assert not fake_client.calls


def test_upload_rejects_empty_formulas(fake_client, sync_async):
    errors = []
    cf.upload_community_function(_account(), "n", "", "y", on_error=errors.append)
    cf.upload_community_function(_account(), "n", "fx", "   ", on_error=errors.append)
    assert len(errors) == 2
    assert not fake_client.calls


def test_upload_inserts_only_content_columns(fake_client, sync_async):
    cf.upload_community_function(_account(), "My Field", "-y", "x",
                                 description="a field", tags=["vortex", "Calm"])
    call = next(c for c in fake_client.calls if c["op"] == "insert")
    payload = call["payload"]
    assert payload["user_id"] == "u1"
    assert payload["uploader_name"] == "Alice"
    assert payload["function_name"] == "My Field"
    assert payload["fx"] == "-y" and payload["fy"] == "x"
    assert payload["description"] == "a field"
    # statistics are never submitted by the client
    assert "usage_count" not in payload
    assert "favorite_count" not in payload
    assert payload["tags"] == ["vortex", "Calm"]


def test_upload_with_own_community_id_updates_the_row_in_place(fake_client, sync_async):
    fake_client_calls_before = len(fake_client.calls)

    class _OwnTable(_FakeTable):
        pass

    original_table = fake_client.table

    def table(name):
        table_obj = original_table(name)
        if name == "community_functions":
            original_execute = table_obj.execute

            def execute():
                if table_obj._op == "update":
                    table_obj.client.calls.append({
                        "table": name,
                        "op": "update",
                        "payload": table_obj._payload,
                        "filters": list(table_obj._filters),
                        "select": None,
                        "order": None,
                        "on_conflict": None,
                    })
                    return SimpleNamespace(data=[{"id": "mine"}])
                return original_execute()

            table_obj.execute = execute
        return table_obj

    fake_client.table = table
    cf.upload_community_function(_account(), "Name", "x", "y", community_id="mine")
    updates = [c for c in fake_client.calls if c["op"] == "update"]
    assert updates, "expected an in-place update of the owned row"
    assert ("eq", "id", "mine") in updates[0]["filters"]
    assert ("eq", "user_id", "u1") in updates[0]["filters"]
    assert "user_id" not in updates[0]["payload"]      # ownership is the server's decision
    assert fake_client_calls_before >= 0


def test_upload_duplicate_formulas_match_existing_row(fake_client, sync_async):
    class _MatchTable(_FakeTable):
        def execute(self):
            if self._op == "select" and "fx" in str(self._select_cols):
                return SimpleNamespace(data=[{"id": "existing-row",
                                              "function_name": "Name",
                                              "fx": "fx", "fy": "fy"}])
            return super().execute()

    fake_client.table = lambda name: _MatchTable(fake_client, name)
    cf.upload_community_function(_account(), "Name", "fx", "fy")
    updates = [c for c in fake_client.calls if c["op"] == "update"]
    assert updates and ("eq", "id", "existing-row") in updates[0]["filters"]


# --- updating -----------------------------------------------------------------

def test_update_only_writes_content_columns(fake_client, sync_async):
    cf.update_community_function("row-9", _account(), function_name="New",
                                 fx="1", fy="2", description="d", tags=["t"])
    call = next(c for c in fake_client.calls if c["op"] == "update")
    assert set(call["payload"]) == {"function_name", "fx", "fy", "description", "tags"}
    assert ("eq", "id", "row-9") in call["filters"]
    assert ("eq", "user_id", "u1") in call["filters"]


def test_update_rejects_invalid_fields(fake_client, sync_async):
    errors = []
    cf.update_community_function("row-9", _account(), fx="   ", on_error=errors.append)
    cf.update_community_function("", _account(), fx="1", on_error=errors.append)
    cf.update_community_function("row-9", _account(), function_name="", on_error=errors.append)
    assert len(errors) == 3
    assert not fake_client.calls


# --- ratings -------------------------------------------------------------------

def test_rating_validation(fake_client, sync_async):
    errors = []
    for bad in ("0", "6", -1, 7, "abc", True):
        cf.set_function_rating("row-1", bad, _account(), on_error=errors.append)
    assert len(errors) == 6
    assert not fake_client.calls


def test_rating_upserts_one_row_per_user_and_function(fake_client, sync_async):
    cf.set_function_rating("row-1", 4, _account())
    call = fake_client.calls[0]
    assert call["op"] == "upsert"
    assert call["table"] == "community_function_ratings"
    assert call["payload"] == {"user_id": "u1", "function_id": "row-1", "rating": 4}
    assert call["on_conflict"] == "user_id,function_id"


def test_favorite_upsert_then_delete(fake_client, sync_async):
    cf.set_function_favorite("row-1", True, _account())
    cf.set_function_favorite("row-1", False, _account())
    insert_call, delete_call = fake_client.calls
    assert insert_call["op"] == "upsert"
    assert insert_call["table"] == "community_function_favorites"
    assert delete_call["op"] == "delete"
    assert ("eq", "user_id", "u1") in delete_call["filters"]


# --- usage statistics -----------------------------------------------------------

def test_record_usage_uses_the_atomic_database_function(fake_client, sync_async):
    cf.record_community_function_usage("row-1", success=True, player_key="player-7")
    call = fake_client.calls[0]
    assert call["rpc"] == "community_function_record_usage"
    assert call["params"] == {"p_function_id": "row-1", "p_success": True,
                             "p_player_key": "player-7"}


def test_record_usage_requires_an_id(fake_client, sync_async):
    errors = []
    cf.record_community_function_usage("", on_error=errors.append)
    assert errors and not fake_client.calls


# --- facade re-exports ---------------------------------------------------------

def test_facade_reexports_the_function_operations():
    for name in ("upload_community_function", "update_community_function",
                 "delete_community_function", "fetch_community_functions",
                 "delete_user_community_functions", "update_community_functions_uploader_name",
                 "record_community_function_usage", "set_function_favorite",
                 "set_function_rating", "fetch_function_engagement"):
        assert callable(getattr(community_module, name, None)), name


# --- _own_function_rows fail-closed behaviour -------------------------------

def test_upload_rejects_when_own_rows_query_fails(fake_client, sync_async):
    class _FailingTable(_FakeTable):
        def execute(self):
            if self._op == "select":
                raise RuntimeError("connection lost")
            return super().execute()

    fake_client.table = lambda name: _FailingTable(fake_client, name)
    errors = []
    cf.upload_community_function(_account(), "My Field", "-y", "x",
                                 on_error=errors.append)
    assert errors, "expected upload to be rejected when own-rows query fails"
    inserts = [c for c in fake_client.calls if c["op"] == "insert"]
    assert not inserts, "no insert should happen when the query fails"


def test_upload_allows_when_own_rows_returns_empty(fake_client, sync_async):
    class _EmptyTable(_FakeTable):
        def execute(self):
            if self._op == "select" and "fx" in str(self._select_cols):
                return SimpleNamespace(data=[])
            return super().execute()

    fake_client.table = lambda name: _EmptyTable(fake_client, name)
    cf.upload_community_function(_account(), "My Field", "-y", "x")
    inserts = [c for c in fake_client.calls if c["op"] == "insert"]
    assert inserts, "expected insert when no existing rows"


def test_upload_rejects_when_same_name_exists(fake_client, sync_async):
    class _SameNameTable(_FakeTable):
        def execute(self):
            if self._op == "select" and "fx" in str(self._select_cols):
                # Same name, different formulas -> conflict, must reject.
                return SimpleNamespace(data=[{
                    "id": "r1", "function_name": "My Field", "fx": "a", "fy": "b"}])
            return super().execute()

    fake_client.table = lambda name: _SameNameTable(fake_client, name)
    errors = []
    cf.upload_community_function(_account(), "My Field", "-y", "x", on_error=errors.append)
    assert errors, "expected upload to be rejected when same name exists"
    inserts = [c for c in fake_client.calls if c["op"] == "insert"]
    assert not inserts, "no insert should happen when name is taken"


def test_upload_allows_when_no_same_name(fake_client, sync_async):
    class _NoConflictTable(_FakeTable):
        def execute(self):
            if self._op == "select" and "fx" in str(self._select_cols):
                return SimpleNamespace(data=[{
                    "id": "r1", "function_name": "Other Name", "fx": "a", "fy": "b"}])
            return super().execute()

    fake_client.table = lambda name: _NoConflictTable(fake_client, name)
    cf.upload_community_function(_account(), "My Field", "-y", "x")
    inserts = [c for c in fake_client.calls if c["op"] == "insert"]
    assert inserts, "expected insert when no name conflict"
