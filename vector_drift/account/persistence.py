"""Shared local-file persistence helpers for the account subsystem."""

from __future__ import annotations

import os
import uuid
from pathlib import Path


def default_dir() -> Path:
    """The ``~/.vector_drift`` directory, created on demand."""
    base = Path.home() / ".vector_drift"
    base.mkdir(parents=True, exist_ok=True)
    return base


def atomic_write_text(path: Path, text: str, private: bool = False) -> None:
    """Write ``text`` to ``path`` atomically (unique temp + fsync + rename).

    The temp name is unique per writer (pid + random), so two concurrent
    writers cannot clobber each other, and the file is flushed to disk before
    the rename so a crash right after the rename loses nothing.
    ``private`` additionally restricts the file to the owner on POSIX.
    """
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        try:
            fd = os.open(tmp, os.O_RDWR)
        except OSError:
            fd = None
        if fd is not None:
            try:
                os.fsync(fd)
            except OSError:
                pass  # fsync is best-effort; the rename is still atomic
            finally:
                os.close(fd)
        if private and os.name == "posix":
            os.chmod(tmp, 0o600)
        os.replace(tmp, path)
        if os.name == "posix":
            # The directory entry must survive too; a crash right after the
            # rename should not leave the file missing.
            try:
                dir_fd = os.open(path.parent, os.O_RDONLY)
            except OSError:
                dir_fd = None
            if dir_fd is not None:
                try:
                    os.fsync(dir_fd)
                except OSError:
                    pass
                finally:
                    os.close(dir_fd)
    except OSError:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise
