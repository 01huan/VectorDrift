"""Community custom levels backed by Supabase.

Levels are stored in the ``public.community_levels`` table (see
``docs/supabase_schema.sql``).  Row level security is configured so that:

* anybody can read (SELECT) the community levels -- this is the public
  location every player can access;
* only signed-in users can INSERT a level they own (upload).

All network calls run on a background thread so the game never blocks while
uploading or fetching.  Callbacks are invoked on that background thread and
only touch simple scene attributes, which is safe under the GIL; scenes that
need to switch scenes on the main thread do so from ``update()``.
"""

from __future__ import annotations

import threading
from typing import Any, Callable, Optional

from .supabase_client import get_client

TABLE = "community_levels"


def _run_async(
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


def upload_community_level(
    account: Any,
    level_name: str,
    level_data: dict,
    on_success: Optional[Callable[[Any], None]] = None,
    on_error: Optional[Callable[[Exception], None]] = None,
) -> None:
    """Upload a player-created level to the public community table.

    Requires ``account`` to be authenticated.  ``level_data`` must be a
    JSON-serializable dict (a serialized ``LevelSpec``).
    """

    def _require_auth() -> None:
        if account is None or not account.is_authenticated() or account.current_user is None:
            raise RuntimeError("Not logged in. Please log in before uploading.")

    def _fn() -> Any:
        _require_auth()
        client = get_client()
        # 社區卡片顯示上傳者的帳號名稱，而非信箱；current_user.name 來自註冊時輸入的帳號 ID。
        # 永遠不以信箱作為顯示名稱：profile.display_name 在尚未設定顯示名稱時可能被寫入信箱，
        # 因此必須排除含 "@" 的值，避免社區卡片顯示完整信箱帳號。
        uploader_name = account.current_user.name or ""
        if (
            not uploader_name
            and account.profile
            and account.profile.display_name
            and "@" not in account.profile.display_name
        ):
            uploader_name = account.profile.display_name
        row = {
            "user_id": account.current_user.id,
            "uploader_email": account.current_user.email or "",
            "uploader_name": uploader_name,
            "level_name": level_name,
            "level_data": level_data,
        }
        return client.table(TABLE).insert(row).execute()

    _run_async(_fn, on_success=on_success, on_error=on_error)


def delete_community_level(
    level_id: str,
    account: Any,
    on_success: Optional[Callable[[], None]] = None,
    on_error: Optional[Callable[[Exception], None]] = None,
) -> None:
    """Delete a community level the current user uploaded.

    Row level security (``community_levels_delete_own``) also enforces that
    only the owner can delete the row; the extra ``eq("user_id", ...)`` below
    is a client-side guard so a wrong user never reaches the database.
    """

    def _fn() -> Any:
        if account is None or not account.is_authenticated() or account.current_user is None:
            raise RuntimeError("Not logged in.")
        client = get_client()
        return (
            client.table(TABLE)
            .delete()
            .eq("id", level_id)
            .eq("user_id", account.current_user.id)
            .execute()
        )

    _run_async(_fn, on_success=on_success, on_error=on_error)


def fetch_community_levels(
    on_success: Optional[Callable[[list[dict]], None]] = None,
    on_error: Optional[Callable[[Exception], None]] = None,
) -> None:
    """Fetch all public community levels, newest first."""

    def _fn() -> list[dict]:
        client = get_client()
        resp = (
            client.table(TABLE)
            .select(
                "id, user_id, uploader_email, uploader_name, level_name, level_data, created_at"
            )
            .order("created_at", desc=True)
            .execute()
        )
        return getattr(resp, "data", None) or []

    _run_async(_fn, on_success=on_success, on_error=on_error)


def serialize_level(level: Any) -> dict:
    """Serialize a ``LevelSpec`` into a JSON-friendly dict for storage."""

    return {
        "id": int(level.id),
        "name": level.name,
        "start": list(level.start),
        "target_center": list(level.target_center),
        "target_radius": float(level.target_radius),
        "ship_id": level.ship_id,
        "time_limit": float(level.time_limit),
        "lives": int(level.lives),
        "obstacles": [
            {
                "center": list(item.center),
                "radius": float(item.radius),
                "restitution": float(item.restitution),
                "kind": item.kind,
            }
            for item in level.obstacles
        ],
        "pickups": [
            {
                "center": list(item.center),
                "radius": float(item.radius),
                "kind": item.kind,
            }
            for item in level.pickups
        ],
        "holes": [
            {
                "black_center": list(item.black_center),
                "white_center": list(item.white_center),
                "radius": float(item.radius),
            }
            for item in getattr(level, "holes", ()) or ()
        ],
    }
