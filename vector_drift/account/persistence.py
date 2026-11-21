"""Shared local-file persistence helpers for the account subsystem."""

from __future__ import annotations

import os
from pathlib import Path


def default_dir() -> Path:
    """The ``~/.vector_drift`` directory, created on demand."""
    base = Path.home() / ".vector_drift"
    base.mkdir(parents=True, exist_ok=True)
    return base


def atomic_write_text(path: Path, text: str, private: bool = False) -> None:
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
