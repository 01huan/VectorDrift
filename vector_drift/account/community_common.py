"""Shared helpers for the community tables.

All community operations (levels and functions) follow the same rules:

* every network call runs on a daemon thread so the game never blocks;
* callbacks are invoked on that background thread and only touch simple
  attributes, which is safe under the GIL; scenes that need to switch
  scenes on the main thread do so from ``update()``;
* a signed-in account is required for every write, and the uploader name
  is derived from the account — never from the caller.
"""

from __future__ import annotations

import threading
from typing import Any, Callable, Optional

__all__ = [
    "run_async", "require_auth", "uploader_name",
]


def run_async(
    fn: Callable[[], Any],
    on_success: Optional[Callable[[Any], None]] = None,
    on_error: Optional[Callable[[Exception], None]] = None,
) -> None:
    """Run ``fn`` on a daemon thread, then call back with the result."""

    def _worker() -> None:
        try:
            result = fn()
        except Exception as exc:  # noqa: BLE001 - report to the caller
            if on_error is not None:
                on_error(exc)
            return
        if on_success is not None:
            on_success(result)

    threading.Thread(target=_worker, daemon=True).start()


def require_auth(account: Any) -> None:
    """Raise when the account is not a signed-in user."""
    if account is None or not account.is_authenticated() or account.current_user is None:
        raise RuntimeError("Not logged in. Please log in first.")


def uploader_name(account: Any) -> str:
    """The uploader name shown on community cards.

    The account ID (the name chosen at registration) is used, never the
    email address: ``profile.display_name`` may hold the email when no
    display name was set, so values containing "@" are rejected here.
    """
    name = getattr(account.current_user, "name", None) or ""
    profile = getattr(account, "profile", None)
    if not name and profile is not None:
        display = getattr(profile, "display_name", None)
        if display and "@" not in str(display):
            name = str(display)
    return name or ""
