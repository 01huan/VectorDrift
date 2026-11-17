"""Community force functions backed by Supabase.

Functions are stored in the ``public.community_functions`` table.  Row level
security is configured so that anybody can read (SELECT) them and only
signed-in users can INSERT a function they own.

All network calls run on a background thread, mirroring
:mod:`vector_drift.account.community`.
"""

from __future__ import annotations

import threading
from typing import Any, Callable, Optional

from .supabase_client import get_client

TABLE = "community_functions"


def _run_async(
    fn: Callable[[], Any],
    on_success: Optional[Callable[[Any], None]] = None,
    on_error: Optional[Callable[[Exception], None]] = None,
) -> None:
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


def _require_auth(account: Any) -> None:
    if account is None or not account.is_authenticated() or account.current_user is None:
        raise RuntimeError("Not logged in. Please log in before uploading.")


def _uploader_name(account: Any) -> str:
    uploader_name = getattr(account.current_user, "name", None) or ""
    if (
        not uploader_name
        and getattr(account, "profile", None) is not None
        and getattr(account.profile, "display_name", None)
        and "@" not in str(account.profile.display_name)
    ):
        uploader_name = account.profile.display_name
    return uploader_name or ""


def _extract_function(args, kwargs) -> tuple[str, str, str]:
    """Normalise the many ways a caller may pass a function."""
    # Direct SavedFunction / dict / object.
    function = kwargs.pop("function", None)
    if function is None:
        function = kwargs.pop("saved_function", None)
    if function is None and args:
        # Could be a SavedFunction or dict passed as first positional.
        first = args[0]
        if not isinstance(first, str):
            function = first
            args = args[1:]
    name = kwargs.pop("function_name", None)
    if name is None:
        name = kwargs.pop("name", None)
    if name is None:
        name = kwargs.pop("level_name", None)
    fx = kwargs.pop("fx", None)
    fy = kwargs.pop("fy", None)
    if function is not None:
        if name is None:
            name = getattr(function, "name", None)
            if name is None and isinstance(function, dict):
                name = function.get("name") or function.get("function_name")
        if fx is None:
            fx = getattr(function, "fx", None)
            if fx is None and isinstance(function, dict):
                fx = function.get("fx")
        if fy is None:
            fy = getattr(function, "fy", None)
            if fy is None and isinstance(function, dict):
                fy = function.get("fy")
    # Positional strings: (name, fx, fy) or (fx, fy) or (name, fx, fy, ...)
    if isinstance(name, str) and fx is None and fy is None and len(args) >= 2:
        # (name, fx, fy)
        pass
    # Handle remaining positional strings.
    strs = [a for a in args if isinstance(a, str)]
    if name is None and len(strs) >= 1:
        name = strs[0]
    if fx is None and len(strs) >= 2:
        fx = strs[1]
    if fy is None and len(strs) >= 3:
        fy = strs[2]
    if name is None:
        name = "Untitled"
    if fx is None:
        fx = ""
    if fy is None:
        fy = ""
    from vector_drift.function_library import clean_name

    return clean_name(name), str(fx), str(fy)


def upload_community_function(
    account: Any,
    *args: Any,
    function: Any = None,
    function_name: Any = None,
    name: Any = None,
    fx: Any = None,
    fy: Any = None,
    on_success: Optional[Callable[[Any], None]] = None,
    on_error: Optional[Callable[[Exception], None]] = None,
    **kwargs: Any,
) -> None:
    """Upload a force function to the public community table."""
    # Absorb alternate keyword names.
    if function is None:
        function = kwargs.pop("saved_function", None)
    if function_name is None:
        function_name = kwargs.pop("level_name", None)
    if fx is None:
        fx = kwargs.pop("fx_text", None)
    if fy is None:
        fy = kwargs.pop("fy_text", None)

    parsed_name, parsed_fx, parsed_fy = _extract_function(
        list(args), {"function": function, "function_name": function_name,
                     "name": name, "fx": fx, "fy": fy, **kwargs}
    )
    # kwargs may still contain on_success/on_error? already popped.

    def _fn() -> Any:
        _require_auth(account)
        client = get_client()
        row = {
            "user_id": account.current_user.id,
            "uploader_name": _uploader_name(account),
            "function_name": parsed_name,
            "fx": parsed_fx,
            "fy": parsed_fy,
        }
        # Avoid duplicate uploads for the same function id when provided.
        target_id = ""
        if function is not None:
            target_id = str(getattr(function, "id", None) or
                            (function.get("id") if isinstance(function, dict) else "") or "")
        if target_id:
            try:
                resp = (
                    client.table(TABLE)
                    .select("id, fx, fy")
                    .eq("user_id", account.current_user.id)
                    .execute()
                )
                existing_row_id = None
                for existing in getattr(resp, "data", None) or []:
                    # Match by name+formulas as a best effort.
                    if (str(existing.get("function_name", "")) == parsed_name
                            and str(existing.get("fx", "")) == parsed_fx
                            and str(existing.get("fy", "")) == parsed_fy):
                        existing_row_id = existing.get("id")
                        break
                if existing_row_id is not None:
                    return (
                        client.table(TABLE)
                        .update(row)
                        .eq("id", existing_row_id)
                        .eq("user_id", account.current_user.id)
                        .execute()
                    )
            except Exception:
                pass
        return client.table(TABLE).insert(row).execute()

    _run_async(_fn, on_success=on_success, on_error=on_error)


def delete_community_function(
    *args: Any,
    function_id: Any = None,
    account: Any = None,
    on_success: Optional[Callable[[Any], None]] = None,
    on_error: Optional[Callable[[Exception], None]] = None,
    **kwargs: Any,
) -> None:
    """Delete a community function the current user uploaded."""
    # Normalise argument order: (function_id, account) OR (account, function_id)
    if account is None:
        # Try kwargs
        account = kwargs.pop("account", None)
    if function_id is None:
        function_id = kwargs.pop("function_id", None) or kwargs.pop("id", None)
    # If first args include account/function_id in either order
    positional = [a for a in args if a is not None]
    for val in positional:
        if account is None and hasattr(val, "is_authenticated"):
            account = val
        elif function_id is None and not hasattr(val, "is_authenticated"):
            function_id = val
    if function_id is None and positional:
        function_id = positional[0] if not hasattr(positional[0], "is_authenticated") else (positional[1] if len(positional) > 1 else None)
    if account is None and len(positional) > 1:
        for val in positional:
            if hasattr(val, "is_authenticated"):
                account = val

    def _fn() -> Any:
        if account is None or not account.is_authenticated() or account.current_user is None:
            raise RuntimeError("Not logged in.")
        client = get_client()
        return (
            client.table(TABLE)
            .delete()
            .eq("id", function_id)
            .eq("user_id", account.current_user.id)
            .execute()
        )

    _run_async(_fn, on_success=on_success, on_error=on_error)


def fetch_community_functions(
    on_success: Optional[Callable[[list[dict]], None]] = None,
    on_error: Optional[Callable[[Exception], None]] = None,
) -> None:
    """Fetch all public community functions, newest first."""

    def _fn() -> list[dict]:
        client = get_client()
        resp = (
            client.table(TABLE)
            .select("id, user_id, uploader_name, function_name, fx, fy, created_at")
            .order("created_at", desc=True)
            .execute()
        )
        return getattr(resp, "data", None) or []

    _run_async(_fn, on_success=on_success, on_error=on_error)


# Aliases mirroring community level naming.
def fetch_community_functions_list(*a, **k):
    return fetch_community_functions(*a, **k)


def delete_user_community_functions(
    account: Any,
    on_success: Optional[Callable[[int], None]] = None,
    on_error: Optional[Callable[[Exception], None]] = None,
) -> None:
    """Delete every community function owned by the current user."""

    def _fn() -> int:
        if account is None or not account.is_authenticated() or account.current_user is None:
            raise RuntimeError("Not logged in.")
        client = get_client()
        resp = (
            client.table(TABLE)
            .delete()
            .eq("user_id", account.current_user.id)
            .execute()
        )
        return len(getattr(resp, "data", None) or [])

    _run_async(_fn, on_success=on_success, on_error=on_error)


def update_community_functions_uploader_name(
    account: Any,
    new_name: str,
    on_success: Optional[Callable[[int], None]] = None,
    on_error: Optional[Callable[[Exception], None]] = None,
) -> None:
    """Refresh ``uploader_name`` on every community function owned by the user."""

    def _fn() -> int:
        if account is None or not account.is_authenticated() or account.current_user is None:
            raise RuntimeError("Not logged in.")
        client = get_client()
        resp = (
            client.table(TABLE)
            .update({"uploader_name": new_name or ""})
            .eq("user_id", account.current_user.id)
            .execute()
        )
        return len(getattr(resp, "data", None) or [])

    _run_async(_fn, on_success=on_success, on_error=on_error)


__all__ = [
    "TABLE",
    "upload_community_function",
    "delete_community_function",
    "fetch_community_functions",
    "delete_user_community_functions",
    "update_community_functions_uploader_name",
]
