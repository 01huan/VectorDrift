"""Local persistence of auth session (refresh token only, never password)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from .errors import AccountError


def _storage_path() -> Path:
    base = Path.home() / ".vector_drift"
    base.mkdir(parents=True, exist_ok=True)
    return base / "account_session.json"


def _atomic_write_text(path: Path, text: str, private: bool = False) -> None:
    """Write ``text`` to ``path`` atomically (temp file + rename).

    ``private`` additionally restricts the file to the owner on POSIX.
    """
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        if private and os.name == "posix":
            os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except OSError:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


class SessionManager:
    def __init__(self, path: Optional[Path] = None) -> None:
        self._path = path or _storage_path()

    def save(self, data: Dict[str, Any]) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            _atomic_write_text(
                self._path,
                json.dumps(data, ensure_ascii=False, indent=2),
                private=True,
            )
        except OSError as exc:
            raise AccountError(f"Failed to save session: {exc}") from exc

    def load(self) -> Optional[Dict[str, Any]]:
        if not self._path.exists():
            return None
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def clear(self) -> None:
        try:
            if self._path.exists():
                self._path.unlink()
        except OSError:
            pass
