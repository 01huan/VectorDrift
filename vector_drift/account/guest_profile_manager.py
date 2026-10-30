"""Local persistence for guest (non-authenticated) profiles."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from .models import PlayerProfile


def _storage_path() -> Path:
    base = Path.home() / ".vector_drift"
    base.mkdir(parents=True, exist_ok=True)
    return base / "guest_profile.json"


class LocalProfileManager:
    def __init__(self, path: Optional[Path] = None) -> None:
        self._path = Path(path) if path is not None else _storage_path()

    @property
    def path(self) -> Path:
        return self._path

    def exists(self) -> bool:
        return self._path.exists()

    def save(self, profile_or_session: Any = None) -> None:
        profile = self._coerce(profile_or_session)
        if profile is None:
            return
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps(profile.to_row(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass

    def save_profile(self, profile: PlayerProfile) -> None:
        self.save(profile)

    def save_session(self, session: Any) -> None:
        from .integration import session_to_profile
        try:
            profile = session_to_profile(session, "guest")
        except Exception:
            return
        self.save(profile)

    def load(self) -> Optional[PlayerProfile]:
        if not self._path.exists():
            return None
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, ValueError):
            return None
        if not isinstance(data, dict):
            return None
        try:
            return PlayerProfile.from_row(data, data.get("id") or "guest")
        except Exception:
            return None

    def load_profile(self) -> Optional[PlayerProfile]:
        return self.load()

    def clear(self) -> None:
        try:
            if self._path.exists():
                self._path.unlink()
        except OSError:
            pass

    def delete(self) -> None:
        self.clear()

    def delete_profile(self) -> None:
        self.clear()

    def reset(self) -> None:
        self.clear()

    @staticmethod
    def _coerce(value: Any) -> Optional[PlayerProfile]:
        if value is None:
            return None
        if isinstance(value, PlayerProfile):
            return value
        if hasattr(value, "money") and hasattr(value, "records"):
            try:
                from .integration import session_to_profile
                return session_to_profile(value, "guest")
            except Exception:
                return None
        if isinstance(value, dict):
            try:
                return PlayerProfile.from_row(value, value.get("id") or "guest")
            except Exception:
                return None
        return None


GuestProfileManager = LocalProfileManager
GuestManager = LocalProfileManager
LocalManager = LocalProfileManager
GuestSessionManager = LocalProfileManager
LocalSessionManager = LocalProfileManager
GuestStore = LocalProfileManager
LocalStore = LocalProfileManager
GuestProfileStore = LocalProfileManager
LocalProfileStore = LocalProfileManager
GuestDataStore = LocalProfileManager
LocalDataStore = LocalProfileManager


def load_guest_profile(path=None):
    return LocalProfileManager(path).load()


def save_guest_profile(profile_or_session=None, path=None):
    LocalProfileManager(path).save(profile_or_session)


def clear_guest_profile(path=None):
    LocalProfileManager(path).clear()


def delete_guest_profile(path=None):
    LocalProfileManager(path).clear()


def delete_local_records(path=None):
    LocalProfileManager(path).clear()


def delete_local_data(path=None):
    LocalProfileManager(path).clear()
