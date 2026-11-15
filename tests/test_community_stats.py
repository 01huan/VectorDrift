"""Tests for the community level statistics (plays, clears, clearers)."""

from types import SimpleNamespace

import pytest

from vector_drift.account import community as community_module
from vector_drift.account.player_identity import new_player_key, player_key


class _FakeRpc:
    def __init__(self, name, params):
        self.name = name
        self.params = params
        self.executed = False

    def execute(self):
        self.executed = True
        return SimpleNamespace(data=None)


class _FakeClient:
    def __init__(self, fail_select=False):
        self.calls = []
        self.fail_select = fail_select

    def table(self, name):
        client = self

        class _Table:
            def select(self, *columns):
                selected = columns[0]
                client.calls.append(("select", selected))
                if client.fail_select and "play_count" in selected:
                    # An older database does not know the statistics columns.
                    raise RuntimeError("column does not exist")

                class _Query:
                    def order(self, *_args, **_kwargs):
                        return self

                    def execute(self):
                        return SimpleNamespace(data=[{"id": "r1"}])

                return _Query()

        return _Table()

    def rpc(self, name, params):
        call = _FakeRpc(name, params)
        self.calls.append(("rpc", name, params))
        return call


@pytest.fixture
def sync_async(monkeypatch):
    """Run the background work inline so the callbacks fire right away."""

    def fake(fn, on_success=None, on_error=None):
        try:
            result = fn()
        except Exception as exc:  # noqa: BLE001 - the test wants the error
            if on_error is not None:
                on_error(exc)
            return
        if on_success is not None:
            on_success(result)

    monkeypatch.setattr(community_module, "_run_async", fake)


def _install(monkeypatch, client):
    monkeypatch.setattr(community_module, "get_client", lambda: client)


# --- fetching --------------------------------------------------------------

def test_fetch_asks_for_the_statistics_columns(monkeypatch, sync_async):
    client = _FakeClient()
    _install(monkeypatch, client)
    rows = []
    community_module.fetch_community_levels(on_success=rows.extend)
    assert rows == [{"id": "r1"}]
    selected = [call[1] for call in client.calls if call[0] == "select"]
    assert len(selected) == 1
    assert "play_count" in selected[0]
    assert "clear_count" in selected[0]
    assert "clear_players" in selected[0]


def test_fetch_falls_back_when_the_statistics_columns_are_missing(monkeypatch, sync_async):
    client = _FakeClient(fail_select=True)
    _install(monkeypatch, client)
    rows = []
    community_module.fetch_community_levels(on_success=rows.extend)
    assert rows == [{"id": "r1"}]
    selected = [call[1] for call in client.calls if call[0] == "select"]
    assert len(selected) == 2
    assert "play_count" not in selected[1]
    assert "level_name" in selected[1]


def test_fetch_reports_an_error(monkeypatch):
    def fake(fn, on_success=None, on_error=None):
        on_error(RuntimeError("offline"))

    monkeypatch.setattr(community_module, "_run_async", fake)
    errors = []
    community_module.fetch_community_levels(on_error=errors.append)
    assert "offline" in str(errors[0])


# --- recording -------------------------------------------------------------

def test_recording_a_play_calls_the_database_function(monkeypatch, sync_async):
    client = _FakeClient()
    _install(monkeypatch, client)
    community_module.record_community_play("row-1")
    calls = [call for call in client.calls if call[0] == "rpc"]
    assert calls == [("rpc", "community_level_record_play", {"p_level_id": "row-1"})]


def test_recording_a_clear_sends_the_player_key(monkeypatch, sync_async):
    client = _FakeClient()
    _install(monkeypatch, client)
    community_module.record_community_clear("row-1", "player-7")
    calls = [call for call in client.calls if call[0] == "rpc"]
    assert calls == [("rpc", "community_level_record_clear",
                      {"p_level_id": "row-1", "p_player_key": "player-7"})]


def test_recording_without_a_level_id_reports_an_error(monkeypatch, sync_async):
    client = _FakeClient()
    _install(monkeypatch, client)
    errors = []
    community_module.record_community_play("", on_error=errors.append)
    assert errors
    assert not [call for call in client.calls if call[0] == "rpc"]


def test_recording_survives_a_database_without_the_functions(monkeypatch):
    def fake(fn, on_success=None, on_error=None):
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 - the test wants the error
            on_error(exc)

    monkeypatch.setattr(community_module, "_run_async", fake)

    class _Broken:
        def table(self, _name):
            raise RuntimeError("no table")

        def rpc(self, *_args, **_kwargs):
            raise RuntimeError("function does not exist")

    _install(monkeypatch, _Broken())
    errors = []
    community_module.record_community_play("row-1", on_error=errors.append)
    assert errors and "function does not exist" in str(errors[0])


# --- the player key --------------------------------------------------------

def test_the_player_key_is_the_account_id_when_signed_in():
    session = SimpleNamespace(player_key=None)
    account = SimpleNamespace(current_user=SimpleNamespace(id="user-1"))
    assert player_key(session, account) == "user-1"
    assert session.player_key is None      # the account id needs no local key


def test_a_guest_gets_a_local_player_key():
    session = SimpleNamespace(player_key=None)
    account = SimpleNamespace(current_user=None)
    key = player_key(session, account)
    assert key
    assert session.player_key == key
    # The key stays the same for the next call.
    assert player_key(session, account) == key


def test_a_new_player_key_is_random():
    assert new_player_key() != new_player_key()
