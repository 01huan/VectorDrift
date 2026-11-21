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

from typing import Any, Callable, Optional

from .supabase_client import get_client
from .community_common import (delete_owned_item, delete_where_user_id, fetch_engagement,
                               fetch_rows_newest, require_user_id, run_async,
                               select_all_pages, update_where_user_id, uploader_name, norm_name)

TABLE = "community_levels"
FAVORITES_TABLE = "community_level_favorites"
RATINGS_TABLE = "community_level_ratings"

# Columns the browser needs.  The statistics columns were added after the
# first release of the table, so an older database does not have them yet:
# the fetch falls back to the plain column list when the extended one fails.
BASE_COLUMNS = "id, user_id, uploader_name, level_name, level_data, created_at"
STAT_COLUMNS = "play_count, clear_count, clear_players, favorite_count, rating_count, rating_total"

_run_async = run_async
_uploader_name = uploader_name


def upload_community_level(
    account: Any,
    level_name: str,
    level_data: dict,
    on_success: Optional[Callable[[Any], None]] = None,
    on_error: Optional[Callable[[Exception], None]] = None,
) -> None:
    """Upload a player-created level to the public community table.

    Requires ``account`` to be authenticated.  ``level_data`` must be a
    JSON-serializable dict (a serialized ``LevelSpec``).  The player's local
    custom level is never touched: publishing copies it.
    """

    def _require_auth() -> None:
        if account is None or not account.is_authenticated() or account.current_user is None:
            raise RuntimeError("Not logged in. Please log in before uploading.")

    def _fn() -> Any:
        _require_auth()
        client = get_client()
        # 社區卡片顯示上傳者的帳號名稱，而非信箱；current_user.name 來自註冊時輸入的帳號 ID。
        uploader_name = _uploader_name(account)
        row = {
            "user_id": account.current_user.id,
            "uploader_name": uploader_name,
            "level_name": level_name,
            "level_data": level_data,
        }
        target_id = str(level_data.get("id")) if level_data.get("id") is not None else ""
        own_rows = select_all_pages(
            lambda: client.table(TABLE).select("id, level_name, level_data").eq("user_id", account.current_user.id)
        )
        target = norm_name(level_name)
        paired_row_id = None
        for existing in own_rows:
            existing_ld = existing.get("level_data") or {}
            if target_id and str(existing_ld.get("id")) == target_id:
                paired_row_id = existing.get("id")
                continue
            if norm_name(existing.get("level_name")) == target:
                raise ValueError(f'You already have a community level called "{level_name}".')
        if paired_row_id is not None:
            # 同一個本機關卡 id 曾經上傳過：更新既有列，避免重複。
            return (
                client.table(TABLE)
                .update(row)
                .eq("id", paired_row_id)
                .eq("user_id", account.current_user.id)
                .execute()
            )
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
        user_id = require_user_id(account)
        return delete_owned_item(get_client(), TABLE, level_id, user_id)

    _run_async(_fn, on_success=on_success, on_error=on_error)


def fetch_community_levels(
    on_success: Optional[Callable[[list[dict]], None]] = None,
    on_error: Optional[Callable[[Exception], None]] = None,
) -> None:
    """Fetch all public community levels, newest first.

    The statistics columns (``play_count`` / ``clear_count`` /
    ``clear_players``) are requested too, but a database that was created
    before they existed answers with an error.  In that case the plain
    column list is used instead: the levels still show up, only without
    their counters.
    """

    def _fn() -> list[dict]:
        return fetch_rows_newest(get_client(), TABLE, BASE_COLUMNS, STAT_COLUMNS)

    _run_async(_fn, on_success=on_success, on_error=on_error)


def record_community_play(
    level_id: str,
    on_success: Optional[Callable[[Any], None]] = None,
    on_error: Optional[Callable[[Exception], None]] = None,
) -> None:
    """Count one play of a community level.

    The counter lives on the level row and is raised by a database function
    (``community_level_record_play``), so two players never overwrite each
    other's count.  A database without that function simply does not count
    the play: the error is reported to the caller, never raised into the
    game loop.
    """
    if not level_id:
        if on_error is not None:
            on_error(ValueError("no community level id"))
        return

    def _fn() -> Any:
        client = get_client()
        return client.rpc("community_level_record_play", {"p_level_id": str(level_id)}).execute()

    _run_async(_fn, on_success=on_success, on_error=on_error)


def record_community_clear(
    level_id: str,
    player_key: Optional[str] = None,
    on_success: Optional[Callable[[Any], None]] = None,
    on_error: Optional[Callable[[Exception], None]] = None,
) -> None:
    """Count one clear of a community level.

    ``player_key`` identifies the player (the account id, or the local
    player id for a guest).  The database keeps a per-level hash of the keys
    of the players who cleared the level, so it can also report how many
    *different* players cleared it without storing the ids themselves.
    """
    if not level_id:
        if on_error is not None:
            on_error(ValueError("no community level id"))
        return

    def _fn() -> Any:
        client = get_client()
        return client.rpc(
            "community_level_record_clear",
            {"p_level_id": str(level_id), "p_player_key": player_key or ""},
        ).execute()

    _run_async(_fn, on_success=on_success, on_error=on_error)


# --- favorites and ratings ---------------------------------------------------

def set_level_favorite(
    level_id: str,
    favorite: bool,
    account: Any,
    on_success: Optional[Callable[[Any], None]] = None,
    on_error: Optional[Callable[[Exception], None]] = None,
) -> None:
    """Favorite (``favorite=True``) or unfavorite a community level.

    One row per (user, level) is enforced by the primary key of the
    favorites table; the ``favorite_count`` on the level row is maintained
    by a database trigger, so duplicate toggles can never inflate it.
    """
    if not level_id:
        if on_error is not None:
            on_error(ValueError("no community level id"))
        return

    def _fn() -> Any:
        if account is None or not account.is_authenticated() or account.current_user is None:
            raise RuntimeError("Not logged in.")
        client = get_client()
        if favorite:
            return (
                client.table(FAVORITES_TABLE)
                .upsert({
                    "user_id": account.current_user.id,
                    "level_id": str(level_id),
                }, on_conflict="user_id,level_id")
                .execute()
            )
        return (
            client.table(FAVORITES_TABLE)
            .delete()
            .eq("level_id", str(level_id))
            .eq("user_id", account.current_user.id)
            .execute()
        )

    _run_async(_fn, on_success=on_success, on_error=on_error)


def set_level_rating(
    level_id: str,
    rating: Any,
    account: Any,
    on_success: Optional[Callable[[Any], None]] = None,
    on_error: Optional[Callable[[Exception], None]] = None,
) -> None:
    """Rate a community level from 1 to 5 stars.

    One rating per (user, level) is enforced by the primary key of the
    ratings table: submitting again *changes* the rating instead of adding a
    new one.  The average and the count on the level row are maintained by a
    database trigger.
    """
    if not level_id:
        if on_error is not None:
            on_error(ValueError("no community level id"))
        return
    try:
        stars = int(rating)
    except (TypeError, ValueError):
        if on_error is not None:
            on_error(ValueError("The rating must be a whole number of stars."))
        return
    if isinstance(rating, bool) or stars < 1 or stars > 5:
        if on_error is not None:
            on_error(ValueError("The rating must be between 1 and 5 stars."))
        return

    def _fn() -> Any:
        if account is None or not account.is_authenticated() or account.current_user is None:
            raise RuntimeError("Not logged in.")
        client = get_client()
        return (
            client.table(RATINGS_TABLE)
            .upsert({
                "user_id": account.current_user.id,
                "level_id": str(level_id),
                "rating": stars,
            }, on_conflict="user_id,level_id")
            .execute()
        )

    _run_async(_fn, on_success=on_success, on_error=on_error)


def fetch_level_engagement(
    account: Any,
    on_success: Optional[Callable[[dict], None]] = None,
    on_error: Optional[Callable[[Exception], None]] = None,
) -> None:
    """Fetch the signed-in user's own favorites and ratings.

    Returns ``{"favorites": [level_id, ...], "ratings": {level_id: rating}}``.
    Guests (or a missing account) get empty containers: the public page
    works without an account, only the per-user state is missing.
    """

    def _fn() -> dict:
        if account is None or not account.is_authenticated() or account.current_user is None:
            return {"favorites": [], "ratings": {}}
        client = get_client()
        favorites, ratings = fetch_engagement(
            client, FAVORITES_TABLE, RATINGS_TABLE, "level_id", account.current_user.id)
        return {"favorites": favorites, "ratings": ratings}

    _run_async(_fn, on_success=on_success, on_error=on_error)


def delete_user_level_engagement(
    account: Any,
    on_success: Optional[Callable[[bool], None]] = None,
    on_error: Optional[Callable[[Exception], None]] = None,
) -> None:
    """Delete every favorite and rating the current user left on community
    levels.  Called when the account data is cleared / the player returns to
    guest, so rows pointing at the player do not stay behind."""

    def _fn() -> bool:
        user_id = require_user_id(account)
        client = get_client()
        client.table(RATINGS_TABLE).delete().eq("user_id", user_id).execute()
        client.table(FAVORITES_TABLE).delete().eq("user_id", user_id).execute()
        return True

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
        "sections": [
            {
                "start": list(s.start),
                "target_center": list(s.target_center),
                "target_radius": float(s.target_radius),
                "time_limit": float(s.time_limit),
                "obstacles": [
                    {
                        "center": list(o.center),
                        "radius": float(o.radius),
                        "restitution": float(o.restitution),
                        "kind": o.kind,
                    }
                    for o in s.obstacles
                ],
                "pickups": [
                    {
                        "center": list(p.center),
                        "radius": float(p.radius),
                        "kind": p.kind,
                    }
                    for p in s.pickups
                ],
                "holes": [
                    {
                        "black_center": list(h.black_center),
                        "white_center": list(h.white_center),
                        "radius": float(h.radius),
                    }
                    for h in s.holes
                ],
            }
            for s in getattr(level, "sections", ()) or ()
        ],
    }


def delete_user_community_levels(
    account: Any,
    on_success: Optional[Callable[[int], None]] = None,
    on_error: Optional[Callable[[Exception], None]] = None,
) -> None:
    """Delete every community level owned by the current user.

    Called when the account data is cleared / the player returns to guest, so
    the uploader's rows do not stay orphaned once the account is no longer active.
    """

    def _fn() -> int:
        return delete_where_user_id(get_client(), TABLE, require_user_id(account))

    _run_async(_fn, on_success=on_success, on_error=on_error)


def update_community_levels_uploader_name(
    account: Any,
    new_name: str,
    on_success: Optional[Callable[[int], None]] = None,
    on_error: Optional[Callable[[Exception], None]] = None,
) -> None:
    """Refresh ``uploader_name`` on every community level owned by the user.

    Called after the account name is renamed so public cards keep showing the
    current display name instead of a stale one.  Requires the
    ``community_levels_update_own`` row-level-security policy.
    """

    def _fn() -> int:
        return update_where_user_id(
            get_client(), TABLE, require_user_id(account), {"uploader_name": new_name or ""})

    _run_async(_fn, on_success=on_success, on_error=on_error)


def _community_row_id_for_local_level(
    client: Any, account: Any, local_level_id: int
) -> Optional[str]:
    """Return the community row id whose serialized ``level_data.id`` matches
    ``local_level_id`` for the given account, or ``None`` when not found.

    We cannot rely on PostgREST JSON-column filters (``level_data->>id``), so we
    fetch the user's rows and compare in Python instead.
    """
    target = str(int(local_level_id))
    resp = (
        client.table(TABLE)
        .select("id, level_data")
        .eq("user_id", account.current_user.id)
        .execute()
    )
    for row in getattr(resp, "data", None) or []:
        level_data = row.get("level_data") or {}
        if str(level_data.get("id")) == target:
            return row.get("id")
    return None


def delete_community_level_by_local_id(
    account: Any,
    local_level_id: int,
    on_success: Optional[Callable[[], None]] = None,
    on_error: Optional[Callable[[Exception], None]] = None,
) -> None:
    """Delete the community upload whose serialized ``level_data.id`` matches a
    local level that the player just deleted.  Only the owner's row is touched.
    """

    def _fn() -> None:
        if account is None or not account.is_authenticated() or account.current_user is None:
            raise RuntimeError("Not logged in.")
        client = get_client()
        row_id = _community_row_id_for_local_level(client, account, local_level_id)
        if row_id is None:
            return
        (
            client.table(TABLE)
            .delete()
            .eq("id", row_id)
            .eq("user_id", account.current_user.id)
            .execute()
        )

    _run_async(_fn, on_success=on_success, on_error=on_error)


def update_community_level_by_local_id(
    account: Any,
    local_level_id: int,
    level_name: str,
    level_data: dict,
    on_success: Optional[Callable[[], None]] = None,
    on_error: Optional[Callable[[Exception], None]] = None,
) -> None:
    """Update the community upload whose serialized ``level_data.id`` matches a
    local level that the player just modified, so the public card shows the new
    name/content.  Only the owner's row is touched.

    A name that another of the player's community levels already uses is
    rejected (one player, one name), so a local edit can never split the
    public list into duplicates either.
    """

    def _fn() -> None:
        if account is None or not account.is_authenticated() or account.current_user is None:
            raise RuntimeError("Not logged in.")
        client = get_client()
        own_rows = select_all_pages(
            lambda: client.table(TABLE).select("id, level_name, level_data").eq("user_id", account.current_user.id)
        )
        target = norm_name(level_name)
        row_id = None
        for entry in own_rows:
            entry_data = entry.get("level_data") or {}
            if str(entry_data.get("id")) == str(local_level_id):
                # This row is the sync target, never a conflict.
                row_id = entry.get("id")
                continue
            if norm_name(entry.get("level_name")) == target:
                raise ValueError(f'You already have a community level called "{level_name}".')
        if row_id is None:
            return
        (
            client.table(TABLE)
            .update({"level_name": level_name, "level_data": level_data})
            .eq("id", row_id)
            .eq("user_id", account.current_user.id)
            .execute()
        )

    _run_async(_fn, on_success=on_success, on_error=on_error)


# --- Community functions (re-exported) ---
try:
    from . import community_functions as _community_functions
    upload_community_function = _community_functions.upload_community_function
    update_community_function = _community_functions.update_community_function
    delete_community_function = _community_functions.delete_community_function
    fetch_community_functions = _community_functions.fetch_community_functions
    delete_user_community_functions = _community_functions.delete_user_community_functions
    update_community_functions_uploader_name = _community_functions.update_community_functions_uploader_name
    record_community_function_usage = _community_functions.record_community_function_usage
    set_function_favorite = _community_functions.set_function_favorite
    set_function_rating = _community_functions.set_function_rating
    fetch_function_engagement = _community_functions.fetch_function_engagement
    delete_user_function_engagement = _community_functions.delete_user_function_engagement
except Exception:  # noqa: BLE001
    pass

__all__ = [
    "TABLE",
    "FAVORITES_TABLE",
    "RATINGS_TABLE",
    "BASE_COLUMNS",
    "STAT_COLUMNS",
    "upload_community_level",
    "delete_community_level",
    "fetch_community_levels",
    "record_community_play",
    "record_community_clear",
    "set_level_favorite",
    "set_level_rating",
    "fetch_level_engagement",
    "delete_user_level_engagement",
    "serialize_level",
    "delete_user_community_levels",
    "update_community_levels_uploader_name",
    "delete_community_level_by_local_id",
    "update_community_level_by_local_id",
]
