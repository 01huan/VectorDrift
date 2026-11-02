"""Profile read/write helpers for Supabase."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from .errors import ProfileError
from .models import PlayerProfile
from .supabase_client import get_client


def _parse_ts(value) -> Optional[datetime]:
    if value is None:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _profile_updated_at(profile: Optional[PlayerProfile]) -> Optional[str]:
    if profile is None:
        return None
    return getattr(profile, "updated_at", None)


def _ts_gte(a, b) -> bool:
    """Return True if timestamp ``a`` is newer than or equal to ``b``.

    A missing timestamp is treated as older than any present timestamp, so that
    local data without a timestamp never wins over cloud data that has one.
    """
    pa = _parse_ts(a)
    pb = _parse_ts(b)
    if pa is None:
        return False
    if pb is None:
        return True
    try:
        return pa >= pb
    except TypeError:
        # naive vs aware offset comparison; fall back to raw string compare
        return str(a) >= str(b)


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

    def upsert_if_newer(self, profile: PlayerProfile) -> tuple[bool, PlayerProfile]:
        """Timestamp-aware upsert: newest data wins.

        Returns ``(saved, winning_profile)``.  When a cloud row already exists and
        is newer than ``profile``, the upload is skipped (``saved=False``) and the
        newer cloud profile is returned so the caller can sync it down locally.
        Otherwise ``profile`` is uploaded and returned (``saved=True``).
        """
        try:
            existing = self.fetch(profile.user_id)
        except Exception:
            # Cannot read the cloud row: fall back to a blind upload.
            self.upsert(profile)
            return True, profile

        if existing is not None and _ts_gte(existing.updated_at, profile.updated_at):
            # Cloud is newer (or equal): do not clobber newer cloud data.
            return False, existing

        self.upsert(profile)
        return True, profile

    def ensure_exists(self, user_id: str, display_name: Optional[str] = None) -> PlayerProfile:
        existing = self.fetch(user_id)
        if existing is not None:
            return existing
        profile = PlayerProfile(user_id=user_id, display_name=display_name)
        self.upsert(profile)
        return profile
