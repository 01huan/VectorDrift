import os

import pytest

from vector_drift.account import supabase_client as sc


def test_get_supabase_url_missing(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    with pytest.raises(RuntimeError):
        sc.get_supabase_url()


def test_get_supabase_url_present(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "  https://x.supabase.co  ")
    assert sc.get_supabase_url() == "https://x.supabase.co"


def test_get_supabase_anon_key_prefers_supabase_key(monkeypatch):
    monkeypatch.setenv("SUPABASE_KEY", "key1")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "key2")
    assert sc.get_supabase_anon_key() == "key1"


def test_get_supabase_anon_key_fallback(monkeypatch):
    monkeypatch.delenv("SUPABASE_KEY", raising=False)
    monkeypatch.setenv("SUPABASE_ANON_KEY", "key2")
    assert sc.get_supabase_anon_key() == "key2"


def test_get_supabase_anon_key_missing(monkeypatch):
    monkeypatch.delenv("SUPABASE_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_ANON_KEY", raising=False)
    with pytest.raises(RuntimeError):
        sc.get_supabase_anon_key()


def test_is_configured_true(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "key1")
    assert sc.is_configured() is True


def test_is_configured_false(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_ANON_KEY", raising=False)
    assert sc.is_configured() is False
