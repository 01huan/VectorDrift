"""Profile read/write helpers for Supabase."""

from __future__ import annotations

from typing import Optional

from .errors import ProfileError
from .models import PlayerProfile
from .supabase_client import get_client


class ProfileManager:
    def __init__(self) -> None:
        self._client = None

    def _client_or_raise(self):
        if self._client is None:
            from .supabase_client import get_client

            self._client = get_client()
        return self._client

    def fetch(self, user_id: str) -> Optional[PlayerProfile]:
        try:
            client = self._client_or_raise()
            resp = client.table("profiles").select("*").eq("id", user_id).execute()
        except Exception as exc:  # noqa: BLE001
            raise ProfileError(f"Failed to fetch profile: {exc}") from exc
        rows = getattr(resp, "data", None) or []
        if not rows:
            return None
        return PlayerProfile.from_row(rows[0], user_id)

    def upsert(self, profile: PlayerProfile) -> None:
        try:
            client = self._client_or_raise()
            client.table("profiles").upsert(profile.to_row()).execute()
        except Exception as exc:  # noqa: BLE001
            raise ProfileError(f"Failed to save profile: {exc}") from exc

    def ensure_exists(self, user_id: str, display_name: Optional[str] = None) -> PlayerProfile:
        existing = self.fetch(user_id)
        if existing is not None:
            return existing
        profile = PlayerProfile(user_id=user_id, display_name=display_name)
        self.upsert(profile)
        return profile
