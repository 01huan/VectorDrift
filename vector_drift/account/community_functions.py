"""Community force functions backed by Supabase.

Functions are stored in the ``public.community_functions`` table.  Row level
security is configured so that anybody can read (SELECT) them and only
signed-in users can INSERT a function they own; their favorites and ratings
live in ``community_function_favorites`` / ``community_function_ratings``
(see ``docs/supabase_schema.sql``).

All network calls run on a background thread, mirroring
:mod:`vector_drift.account.community`.  Ownership and statistics are never
taken from the client: the server decides who owns a row and the database
maintains the counters.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from .supabase_client import get_client
from .community_common import require_auth, run_async, uploader_name, norm_name, select_all_pages

TABLE = "community_functions"
FAVORITES_TABLE = "community_function_favorites"
RATINGS_TABLE = "community_function_ratings"

# Columns the browser needs.  The statistics columns were added after the
# first release of the table, so an older database does not have them yet:
# the fetch falls back to the plain column list when the extended one fails.
BASE_COLUMNS = "id, user_id, uploader_name, function_name, fx, fy, created_at"
STAT_COLUMNS = ("description, tags, updated_at, "
                "usage_count, successful_usage_count, unique_user_count, "
                "favorite_count, rating_count, rating_total")

# Statistics an owner may never write from the client; they are maintained
# by the database (triggers and security-definer functions).
def _stat_columns_note() -> str:  # pragma: no cover - documentation helper
    return "usage_count, successful_usage_count, unique_user_count, favorite_count, rating_count, rating_total"


_run_async = run_async
_require_auth = require_auth
_uploader_name = uploader_name


def _own_function_rows(client: Any, user_id: str, columns: str = "id, fx, fy, function_name") -> list:
    """The rows this player already owns.

    Used to spot name conflicts: the comparison happens here, not in the
    query, so it does not depend on how the database collates strings.

    A failed query raises so callers can fail-closed instead of treating
    a read error as "no rows" and accidentally creating duplicates.
    """
    return select_all_pages(
        lambda: client.table(TABLE).select(columns).eq("user_id", user_id)
    )


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


def _clean_description(value: Any) -> str:
    from vector_drift.function_library import clean_description

    return clean_description(value)


def _clean_tags(value: Any) -> list:
    from vector_drift.function_library import clean_tags

    return list(clean_tags(value))


def upload_community_function(
    account: Any,
    *args: Any,
    function: Any = None,
    function_name: Any = None,
    name: Any = None,
    fx: Any = None,
    fy: Any = None,
    description: Any = None,
    tags: Any = None,
    community_id: Any = None,
    on_success: Optional[Callable[[Any], None]] = None,
    on_error: Optional[Callable[[Exception], None]] = None,
    **kwargs: Any,
) -> None:
    """Upload a force function to the public community table.

    ``description`` / ``tags`` describe the function for the public card.
    ``community_id`` identifies the community row this function came from (an
    imported function); when the signed-in user owns that row it is updated
    in place, otherwise a brand-new row owned by the user is created.

    Never writes statistics: those belong to the database.
    """
    # Absorb alternate keyword names.
    if function is None:
        function = kwargs.pop("saved_function", None)
    if function_name is None:
        function_name = kwargs.pop("level_name", None)
    if fx is None:
        fx = kwargs.pop("fx_text", None)
    if fy is None:
        fy = kwargs.pop("fy_text", None)
    if description is None:
        description = kwargs.pop("description_text", None) or kwargs.pop("desc", None)
    if tags is None:
        tags = kwargs.pop("tag_list", None)
    if community_id is None:
        community_id = kwargs.pop("community_row_id", None)

    parsed_name, parsed_fx, parsed_fy = _extract_function(
        list(args), {"function": function, "function_name": function_name,
                     "name": name, "fx": fx, "fy": fy, **kwargs}
    )
    # The description and tags may also travel on the passed function object.
    if description is None and function is not None:
        description = getattr(function, "description", None)
        if description is None and isinstance(function, dict):
            description = function.get("description")
    if tags is None and function is not None:
        tags = getattr(function, "tags", None)
        if tags is None and isinstance(function, dict):
            tags = function.get("tags")
    if community_id is None and function is not None:
        community_id = getattr(function, "community_id", None)
        if community_id is None and isinstance(function, dict):
            community_id = function.get("community_id")

    parsed_description = _clean_description(description)
    parsed_tags = _clean_tags(tags)
    parsed_community_id = str(community_id).strip() if community_id else ""
    if not parsed_fx.strip() or not parsed_fy.strip():
        if on_error is not None:
            on_error(ValueError("Fx and Fy must not be empty."))
        return

    def _fn() -> Any:
        require_auth(account)
        client = get_client()
        user_id = account.current_user.id
        row = {
            "user_id": user_id,
            "uploader_name": uploader_name(account),
            "function_name": parsed_name,
            "fx": parsed_fx,
            "fy": parsed_fy,
            "description": parsed_description,
            "tags": parsed_tags,
        }
        update_payload = {k: v for k, v in row.items() if k != "user_id"}

        # --- name conflicts ----------------------------------------------
        # One player may not own two community functions with the same
        # name (the comparison ignores case and repeated spaces).  Rows
        # owned by other players are never considered, so two different
        # players may use the same name.
        own_rows = _own_function_rows(client, user_id)
        same_name = [entry for entry in own_rows
                     if norm_name(entry.get("function_name")) == norm_name(parsed_name)]
        duplicate_note = f'You already have a community function called "{parsed_name}".'

        # An imported function keeps its community identity: when the signed
        # in user owns that row the upload updates it in place, otherwise it
        # becomes a brand-new row owned by the user.
        if parsed_community_id:
            if any(str(entry.get("id") or "") != parsed_community_id for entry in same_name):
                raise ValueError(duplicate_note)
            try:
                resp = (
                    client.table(TABLE)
                    .update(update_payload)
                    .eq("id", parsed_community_id)
                    .eq("user_id", user_id)
                    .execute()
                )
                if getattr(resp, "data", None):
                    return resp
            except Exception:
                # The row is not ours or the update failed: fall through to
                # the shared tail, which never creates an own-row duplicate
                # under a name the player already uses.
                pass

        formula_row = next(
            (entry for entry in same_name
             if str(entry.get("fx")) == parsed_fx and str(entry.get("fy")) == parsed_fy),
            None,
        )
        if same_name:
            if formula_row is None:
                raise ValueError(duplicate_note)
            # Same name, same formulas: update that row instead of
            # duplicating it (statistics survive an update).
            return (
                client.table(TABLE)
                .update(update_payload)
                .eq("id", str(formula_row.get("id") or ""))
                .eq("user_id", user_id)
                .execute()
            )
        return client.table(TABLE).insert(row).execute()

    _run_async(_fn, on_success=on_success, on_error=on_error)


def update_community_function(
    function_id: str,
    account: Any,
    *,
    function_name: Any = None,
    fx: Any = None,
    fy: Any = None,
    description: Any = None,
    tags: Any = None,
    on_success: Optional[Callable[[Any], None]] = None,
    on_error: Optional[Callable[[Exception], None]] = None,
) -> None:
    """Update one of the signed-in user's published functions.

    Only the content columns are written; the row id is fixed by the caller
    and ownership is enforced both here (``eq("user_id", ...)``) and by row
    level security.  Statistics and the uploader name are never touched.
    """
    from vector_drift.function_library import clean_name

    if function_id is None or str(function_id).strip() == "":
        if on_error is not None:
            on_error(ValueError("no community function id"))
        return
    payload: dict = {}
    if function_name is not None:
        raw_name = str(function_name).strip()
        if not raw_name:
            if on_error is not None:
                on_error(ValueError("The function needs a name."))
            return
        payload["function_name"] = clean_name(raw_name)
    if fx is not None:
        fx_text = str(fx)
        if not fx_text.strip():
            if on_error is not None:
                on_error(ValueError("Fx cannot be empty."))
            return
        payload["fx"] = fx_text
    if fy is not None:
        fy_text = str(fy)
        if not fy_text.strip():
            if on_error is not None:
                on_error(ValueError("Fy cannot be empty."))
            return
        payload["fy"] = fy_text
    if description is not None:
        payload["description"] = _clean_description(description)
    if tags is not None:
        payload["tags"] = _clean_tags(tags)
    if not payload:
        if on_success is not None:
            on_success(None)
        return

    def _fn() -> Any:
        require_auth(account)
        client = get_client()
        user_id = account.current_user.id
        # --- name conflicts ----------------------------------------------
        # Renaming must not give this player a second row under a name they
        # already use.  Other players' rows are never considered.
        if "function_name" in payload:
            own_rows = _own_function_rows(client, user_id, "id, function_name")
            target = norm_name(payload["function_name"])
            wanted_id = str(function_id)
            for entry in own_rows:
                if str(entry.get("id") or "") == wanted_id:
                    continue
                if norm_name(entry.get("function_name")) == target:
                    raise ValueError(
                        f'You already have a community function called "{payload["function_name"]}".')
        return (
            client.table(TABLE)
            .update(payload)
            .eq("id", str(function_id))
            .eq("user_id", user_id)
            .execute()
        )

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
        account = kwargs.pop("account", None)
    if function_id is None:
        function_id = kwargs.pop("function_id", None) or kwargs.pop("id", None)
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
    """Fetch all public community functions, newest first.

    The statistics columns are requested too; a database created before they
    existed answers with an error, and the plain column list is used instead:
    the functions still show up, only without their counters.
    """

    def _fn() -> list[dict]:
        client = get_client()
        try:
            return select_all_pages(
                lambda: client.table(TABLE).select(f"{BASE_COLUMNS}, {STAT_COLUMNS}").order("created_at", desc=True)
            )
        except Exception:
            return select_all_pages(
                lambda: client.table(TABLE).select(BASE_COLUMNS).order("created_at", desc=True)
            )

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


# --- usage statistics ---------------------------------------------------------

def record_community_function_usage(
    function_id: str,
    success: bool = False,
    player_key: Optional[str] = None,
    on_success: Optional[Callable[[Any], None]] = None,
    on_error: Optional[Callable[[Exception], None]] = None,
) -> None:
    """Count one usage of a community function.

    The counter lives on the function row and is raised by a database
    function (``community_function_record_usage``), so concurrent uses never
    overwrite each other; the same player only counts once toward the
    unique-user counter.  A database without that function simply does not
    count the usage: the error is reported to the caller, never raised into
    the game loop.
    """
    if not function_id:
        if on_error is not None:
            on_error(ValueError("no community function id"))
        return

    def _fn() -> Any:
        client = get_client()
        return client.rpc(
            "community_function_record_usage",
            {
                "p_function_id": str(function_id),
                "p_success": bool(success),
                "p_player_key": player_key or "",
            },
        ).execute()

    _run_async(_fn, on_success=on_success, on_error=on_error)


# --- favorites ----------------------------------------------------------------

def set_function_favorite(
    function_id: str,
    favorite: bool,
    account: Any,
    on_success: Optional[Callable[[Any], None]] = None,
    on_error: Optional[Callable[[Exception], None]] = None,
) -> None:
    """Favorite (``favorite=True``) or unfavorite a community function.

    One row per (user, function) is enforced by the primary key of the
    favorites table; the ``favorite_count`` on the function row is maintained
    by a database trigger, so duplicate toggles can never inflate it.
    """
    if not function_id:
        if on_error is not None:
            on_error(ValueError("no community function id"))
        return

    def _fn() -> Any:
        require_auth(account)
        client = get_client()
        if favorite:
            return (
                client.table(FAVORITES_TABLE)
                .upsert({
                    "user_id": account.current_user.id,
                    "function_id": str(function_id),
                }, on_conflict="user_id,function_id")
                .execute()
            )
        return (
            client.table(FAVORITES_TABLE)
            .delete()
            .eq("function_id", str(function_id))
            .eq("user_id", account.current_user.id)
            .execute()
        )

    _run_async(_fn, on_success=on_success, on_error=on_error)


def set_function_rating(
    function_id: str,
    rating: Any,
    account: Any,
    on_success: Optional[Callable[[Any], None]] = None,
    on_error: Optional[Callable[[Exception], None]] = None,
) -> None:
    """Rate a community function from 1 to 5 stars.

    One rating per (user, function) is enforced by the primary key of the
    ratings table: submitting again *changes* the rating instead of adding a
    new one.  The average and the count on the function row are maintained by
    a database trigger.
    """
    if not function_id:
        if on_error is not None:
            on_error(ValueError("no community function id"))
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
        require_auth(account)
        client = get_client()
        return (
            client.table(RATINGS_TABLE)
            .upsert({
                "user_id": account.current_user.id,
                "function_id": str(function_id),
                "rating": stars,
            }, on_conflict="user_id,function_id")
            .execute()
        )

    _run_async(_fn, on_success=on_success, on_error=on_error)


def fetch_function_engagement(
    account: Any,
    on_success: Optional[Callable[[dict], None]] = None,
    on_error: Optional[Callable[[Exception], None]] = None,
) -> None:
    """Fetch the signed-in user's own favorites and ratings.

    Returns ``{"favorites": [function_id, ...], "ratings": {function_id:
    rating}}``.  Guests (or a missing account) get empty containers: the
    public page works without an account, only the per-user state is missing.
    """

    def _fn() -> dict:
        empty = {"favorites": [], "ratings": {}}
        if (
            account is None
            or not account.is_authenticated()
            or account.current_user is None
        ):
            return empty
        client = get_client()
        user_id = account.current_user.id
        favorites: list[str] = []
        ratings: dict = {}
        try:
            for row in select_all_pages(
                lambda: client.table(FAVORITES_TABLE).select("function_id").eq("user_id", user_id)
            ):
                fid = row.get("function_id")
                if fid:
                    favorites.append(str(fid))
        except Exception:
            pass
        try:
            for row in select_all_pages(
                lambda: client.table(RATINGS_TABLE).select("function_id, rating").eq("user_id", user_id)
            ):
                fid = row.get("function_id")
                if fid:
                    try:
                        ratings[str(fid)] = int(row.get("rating"))
                    except (TypeError, ValueError):
                        continue
        except Exception:
            pass
        return {"favorites": favorites, "ratings": ratings}

    _run_async(_fn, on_success=on_success, on_error=on_error)


def delete_user_function_engagement(
    account: Any,
    on_success: Optional[Callable[[bool], None]] = None,
    on_error: Optional[Callable[[Exception], None]] = None,
) -> None:
    """Delete every favorite and rating the current user left on community
    functions.  Called when the account data is cleared / the player returns
    to guest, so rows pointing at the player do not stay behind."""

    def _fn() -> bool:
        if account is None or not account.is_authenticated() or account.current_user is None:
            raise RuntimeError("Not logged in.")
        client = get_client()
        client.table(RATINGS_TABLE).delete().eq("user_id", account.current_user.id).execute()
        client.table(FAVORITES_TABLE).delete().eq("user_id", account.current_user.id).execute()
        return True

    _run_async(_fn, on_success=on_success, on_error=on_error)


__all__ = [
    "TABLE",
    "FAVORITES_TABLE",
    "RATINGS_TABLE",
    "BASE_COLUMNS",
    "STAT_COLUMNS",
    "upload_community_function",
    "update_community_function",
    "delete_community_function",
    "fetch_community_functions",
    "fetch_community_functions_list",
    "delete_user_community_functions",
    "update_community_functions_uploader_name",
    "record_community_function_usage",
    "set_function_favorite",
    "set_function_rating",
    "fetch_function_engagement",
    "delete_user_function_engagement",
]
