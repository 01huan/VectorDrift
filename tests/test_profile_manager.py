from unittest.mock import MagicMock

import pytest

from vector_drift.account.profile_manager import ProfileManager
from vector_drift.account.errors import ProfileError
from vector_drift.account.models import PlayerProfile


class FakeResponse:
    def __init__(self, data):
        self.data = data


class FakeQuery:
    def __init__(self, data):
        self._data = data
        self._upsert_data = None

    def select(self, *a, **k):
        return self

    def eq(self, *a, **k):
        return self

    def execute(self):
        return FakeResponse(self._data)

    def upsert(self, row):
        self._upsert_row = row
        return self


class FakeClient:
    def __init__(self, data=None, raise_on=None):
        self._data = data if data is not None else []
        self._raise_on = raise_on
        self._query = FakeQuery(self._data)

    def table(self, name):
        if self._raise_on == "table":
            raise RuntimeError("table boom")
        return self._query


def test_fetch_returns_none_when_no_rows():
    pm = ProfileManager()
    pm._client = FakeClient(data=[])
    assert pm.fetch("u1") is None


def test_fetch_returns_profile():
    pm = ProfileManager()
    pm._client = FakeClient(data=[{"money": 7, "display_name": "A"}])
    p = pm.fetch("u1")
    assert p is not None
    assert p.money == 7
    assert p.display_name == "A"


def test_fetch_raises_profile_error():
    pm = ProfileManager()
    pm._client = FakeClient(raise_on="table")
    with pytest.raises(ProfileError):
        pm.fetch("u1")


def test_upsert_success():
    pm = ProfileManager()
    pm._client = FakeClient(data=[])
    profile = PlayerProfile(user_id="u1", money=3)
    pm.upsert(profile)  # should not raise


def test_upsert_raises_profile_error():
    pm = ProfileManager()
    pm._client = FakeClient(raise_on="table")
    profile = PlayerProfile(user_id="u1", money=3)
    with pytest.raises(ProfileError):
        pm.upsert(profile)


def test_ensure_exists_returns_existing():
    pm = ProfileManager()
    pm._client = FakeClient(data=[{"money": 9}])
    p = pm.ensure_exists("u1", "Name")
    assert p.money == 9


def test_ensure_exists_creates_and_upserts(monkeypatch):
    pm = ProfileManager()
    # first fetch returns None, second not needed; upsert on empty query
    client = FakeClient(data=[])
    pm._client = client
    # make fetch return None by empty data already
    p = pm.ensure_exists("u2", "New")
    assert p.user_id == "u2"
    assert p.display_name == "New"
