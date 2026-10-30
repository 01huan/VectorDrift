"""Supabase client factory for Vector Drift.

All Supabase access goes through this module so that:
* credentials come only from environment variables (never hard-coded secrets);
* a single client instance is shared across the account subsystem.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
import httpx
from supabase import Client, ClientOptions, create_client


def _load_env() -> None:
    root = Path(__file__).resolve().parents[2]
    env_file = root / ".env"
    if env_file.exists():
        load_dotenv(env_file, override=False)
    load_dotenv(override=False)


_load_env()


def get_supabase_url() -> str:
    url = os.getenv("SUPABASE_URL", "").strip()
    if not url:
        raise RuntimeError("SUPABASE_URL is not set (check .env)")
    return url


def get_supabase_anon_key() -> str:
    key = os.getenv("SUPABASE_KEY", "").strip() or os.getenv("SUPABASE_ANON_KEY", "").strip()
    if not key:
        raise RuntimeError("SUPABASE_KEY / SUPABASE_ANON_KEY is not set (check .env)")
    return key


@lru_cache(maxsize=1)
def get_client() -> Client:
    options = ClientOptions(
        httpx_client=httpx.Client(timeout=10.0),
        postgrest_client_timeout=10,
        storage_client_timeout=10,
        function_client_timeout=10,
    )
    return create_client(get_supabase_url(), get_supabase_anon_key(), options=options)


def is_configured() -> bool:
    try:
        get_supabase_url()
        get_supabase_anon_key()
    except RuntimeError:
        return False
    return True
