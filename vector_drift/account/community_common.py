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
    "run_async", "require_auth", "uploader_name", "norm_name",
    "select_all_pages", "require_user_id", "delete_where_user_id",
    "update_where_user_id", "delete_owned_item", "fetch_rows_newest",
    "fetch_engagement",
]

# PostgREST responses are capped server-side (Supabase defaults to 1000
# rows), and the extra rows are dropped silently.  Any select that is
# expected to return everything must page through the table.

def select_all_pages(make_query, page_size: int = 1000, max_rows: int = 20000):
    """Fetch every row of a select in offset pages.

    ``make_query`` is a zero-arg factory returning a fresh PostgREST
    builder (filters / order applied, no ``.range`` yet): a builder
    instance cannot be re-used for multiple pages, calling ``.range``
    more than once would send duplicate offset/limit params.

    Returns at most ``max_rows`` rows.  A failed query raises, so callers
    keep their fail-closed behaviour.  Builders without offset paging
    (older or mock clients) degrade to a single unpaged query.
    """
    rows: list = []
    offset = 0
    while True:
        query = make_query()
        if not hasattr(query, "range"):
            resp = query.execute()
            batch = getattr(resp, "data", None)
            return list(batch) if isinstance(batch, list) else []
        resp = query.range(offset, offset + page_size - 1).execute()
        batch = getattr(resp, "data", None)
        if not isinstance(batch, list):
            batch = []
        rows.extend(batch)
        if len(batch) < page_size or len(rows) >= max_rows:
            return rows[:max_rows]
        offset += page_size


def norm_name(value: Any) -> str:
    """How two names are compared for the "one player, one name" rule.

    Names are compared ignoring case and repeated whitespace; display text
    keeps the original spelling.
    """
    return " ".join(str(value or "").split()).casefold()


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


def require_user_id(account: Any) -> str:
    """The current user's id, raising when the account is not signed in."""
    if account is None or not account.is_authenticated() or account.current_user is None:
        raise RuntimeError("Not logged in.")
    return account.current_user.id


def delete_where_user_id(client: Any, table: str, user_id: str) -> int:
    """Delete every row of ``table`` owned by ``user_id``; return the count."""
    resp = client.table(table).delete().eq("user_id", user_id).execute()
    return len(getattr(resp, "data", None) or [])


def update_where_user_id(client: Any, table: str, user_id: str, values: dict) -> int:
    """Update every row of ``table`` owned by ``user_id``; return the count."""
    resp = client.table(table).update(values).eq("user_id", user_id).execute()
    return len(getattr(resp, "data", None) or [])


def delete_owned_item(client: Any, table: str, item_id: Any, user_id: str) -> Any:
    """Delete the community row with ``id`` owned by ``user_id``; return the response."""
    return (
        client.table(table)
        .delete()
        .eq("id", item_id)
        .eq("user_id", user_id)
        .execute()
    )


def fetch_rows_newest(client: Any, table: str, base_columns: str, stat_columns: str) -> list[dict]:
    """Fetch a community table newest first.

    The statistics columns may be missing on an older database; on failure
    the plain column list is used instead (rows still show, counters missing).
    """
    try:
        return select_all_pages(
            lambda: client.table(table).select(f"{base_columns}, {stat_columns}").order("created_at", desc=True)
        )
    except Exception:
        return select_all_pages(
            lambda: client.table(table).select(base_columns).order("created_at", desc=True)
        )


def fetch_engagement(client: Any, favorites_table: str, ratings_table: str,
                     id_key: str, user_id: str) -> tuple[list, dict]:
    """Fetch the caller's favorites and ratings from the per-user tables."""
    favorites: list = []
    ratings: dict = {}
    try:
        for row in select_all_pages(
                lambda: client.table(favorites_table).select(id_key).eq("user_id", user_id)):
            fid = row.get(id_key)
            if fid:
                favorites.append(str(fid))
    except Exception:
        pass
    try:
        for row in select_all_pages(
                lambda: client.table(ratings_table).select(f"{id_key}, rating").eq("user_id", user_id)):
            fid = row.get(id_key)
            if fid:
                try:
                    ratings[str(fid)] = int(row.get("rating"))
                except (TypeError, ValueError):
                    continue
    except Exception:
        pass
    return favorites, ratings
