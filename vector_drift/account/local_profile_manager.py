"""Local persistence for guest (non-authenticated) profiles."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from .errors import ProfileError
from .models import PlayerProfile
from .persistence import atomic_write_text, default_dir

# The last PlayerProfile written per path: LocalProfileManager.save() skips a
# save whose game data equals it (see save()).
_last_written: dict = {}


def _storage_path() -> Path:
    return default_dir() / "guest_profile.json"


class LocalProfileManager:
    def __init__(self, path: Optional[Path] = None) -> None:
        # The default (~/.vector_drift) is resolved lazily so merely
        # constructing the manager does not create the folder.
        self._path: Optional[Path] = Path(path) if path is not None else None

    @property
    def path(self) -> Path:
        if self._path is None:
            self._path = _storage_path()
        return self._path

    def exists(self) -> bool:
        return self.path.exists()

    def save(self, profile_or_session: Any = None) -> None:
        profile = self._coerce(profile_or_session)
        if profile is None:
            return
        try:
            from .integration import profiles_equal
        except Exception:
            profiles_equal = None
        if profiles_equal is not None:
            last = _last_written.get(self.path)
            if last is not None and profiles_equal(last, profile):
                return  # nothing changed since the last write: skip it
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_text(
                self.path,
                json.dumps(profile.to_row(), ensure_ascii=False),
            )
            _last_written[self.path] = profile
        except OSError as exc:
            raise ProfileError(f"Failed to save local profile: {exc}") from exc

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
        if not self.path.exists():
            return None
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, ValueError):
            return None
        if not isinstance(data, dict):
            return None
        try:
            return PlayerProfile.from_row(data, data.get("id") or "guest")
        except Exception:
            return None

    def clear(self) -> None:
        try:
            if self.path.exists():
                self.path.unlink()
        except OSError:
            pass
        _last_written.pop(self.path, None)

    def delete_profile(self) -> None:
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





