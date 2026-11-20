"""Search, filter and sort rules for the community Function browser.

The **Functions** tab of the Community page lists the force functions anybody
uploaded.  The rules mirror :mod:`vector_drift.community_browse` (levels) on
top of the shared machinery in :mod:`vector_drift.community_core`:

* :func:`function_info` turns one raw database row into a small, safe value
  object.  The row is untrusted, so every field is parsed defensively.
* :func:`filter_functions` combines the name query, the uploader query, the
  tag filter and the sort order into the final list.
* Tags are normalised (:func:`normalize_tags`, :func:`parse_tags`,
  :func:`tag_matches`) so the upload form and the browser always agree about
  what a tag is.

The module is deliberately free of pygame, so the rules can be unit tested
on their own.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Sequence

from .community_core import (
    SORT_NEWEST,
    SORT_OLDEST,
    CommunityItemInfo,
    FuzzyMatcher,
    SortOption,
    SortTable,
    average_rating,
    cached_matcher,
    filter_items,
    float_of,
    fuzzy_score,
    int_of,
    normalize_text,
    round_half_up,
    sort_label_for,
    text_of,
    timestamp_of,
)

__all__ = [
    "SORT_NEWEST", "SORT_OLDEST", "SORT_USES", "SORT_SUCCESS",
    "SORT_FAVORITES", "SORT_RATING",
    "SORT_OPTIONS", "SORT_KEYS", "SORT_LABELS", "SORT_DEFAULT_DESCENDING",
    "MAX_TAGS", "MAX_TAG_LEN", "MAX_DESCRIPTION_LEN",
    "CommunityFunctionInfo", "function_info", "filter_functions",
    "normalize_tags", "parse_tags", "tags_to_text", "tag_matches",
    "average_rating", "round_half_up", "sort_label", "FuzzyMatcher", "fuzzy_score", "normalize_text",
]

# --- limits ------------------------------------------------------------------
MAX_TAGS = 8                 # how many tags one function may carry
MAX_TAG_LEN = 24             # characters in one tag
MAX_DESCRIPTION_LEN = 280    # characters in the description

# --- sort options -----------------------------------------------------------
SORT_USES = "uses"
SORT_SUCCESS = "success"
SORT_FAVORITES = "favorites"
SORT_RATING = "rating"

# (key, label, default direction).  Newest first is the order the server
# sends, so it is the default; the numeric ones default to "most" first.
SORT_OPTIONS = (
    (SORT_NEWEST, "Newest", True),
    (SORT_OLDEST, "Oldest", False),
    (SORT_USES, "Most used", True),
    (SORT_SUCCESS, "Most successful", True),
    (SORT_FAVORITES, "Favorites", True),
    (SORT_RATING, "Highest rated", True),
)
SORT_KEYS = tuple(key for key, _label, _desc in SORT_OPTIONS)
SORT_LABELS = {key: label for key, label, _desc in SORT_OPTIONS}
SORT_DEFAULT_DESCENDING = {key: desc for key, _label, desc in SORT_OPTIONS}
SORT_TABLE = SortTable(tuple(SortOption(key, label, desc) for key, label, desc in SORT_OPTIONS))

# Re-exported shared pieces (kept under their historical names).
_text = text_of
_int = int_of
_float = float_of
_timestamp = timestamp_of
_cached_matcher = cached_matcher


# --- tags ---------------------------------------------------------------------

def normalize_tags(tags: Any):
    """Normalise a tag iterable: trimmed, de-duplicated, capped.

    Untrusted rows (and typed input) both go through this: anything that is
    not a short non-empty string is dropped, and at most ``MAX_TAGS`` tags
    survive.
    """
    if tags is None:
        return ()
    if isinstance(tags, str):
        tags = tags.split(",")
    seen = set()
    cleaned = []
    try:
        iterator = iter(tags)
    except TypeError:
        return ()
    for item in iterator:
        tag = text_of(item, MAX_TAG_LEN)
        if not tag:
            continue
        key = normalize_text(tag)
        if not key or key in seen:
            continue
        seen.add(key)
        cleaned.append(tag)
        if len(cleaned) >= MAX_TAGS:
            break
    return tuple(cleaned)


def parse_tags(text: Any):
    """Parse a comma separated tag entry into normalised tags.

    Used by the upload / edit forms; the inverse of :func:`tags_to_text`.
    """
    if not isinstance(text, str):
        return ()
    return normalize_tags(text.split(","))


def tags_to_text(tags: Any) -> str:
    """The normalised tags as one comma separated line (for the forms)."""
    return ", ".join(normalize_tags(tags))


def tag_matches(tag_query: Any, tags: Any) -> bool:
    """True when the (normalised) query equals or is contained in any tag."""
    query = normalize_text(tag_query)
    if not query:
        return True
    for tag in normalize_tags(tags):
        if query in normalize_text(tag):
            return True
    return False


# --- the browsable function ----------------------------------------------------

@dataclass(frozen=True)
class CommunityFunctionInfo(CommunityItemInfo):
    """One community function, reduced to what the browser needs.

    Every field is already validated: the row comes from a public table that
    anybody can write to.
    """

    fx: str = ""
    fy: str = ""
    description: str = ""
    tags: tuple = ()
    updated_at: str = ""
    updated_ts: float = 0.0
    usage_count: int = 0
    successful_usage_count: int = 0
    unique_user_count: int = 0
    favorite_count: int = 0
    rating_count: int = 0
    rating_total: int = 0

    @property
    def average_rating(self) -> float:
        """The mean rating (0.0 when nobody has rated yet)."""
        return average_rating(self.rating_total, self.rating_count)

    @property
    def success_rate(self) -> float:
        """The share of uses that succeeded (0.0 .. 1.0)."""
        if self.usage_count <= 0:
            return 0.0
        return max(0.0, min(1.0, self.successful_usage_count / self.usage_count))

    def detail_date(self) -> str:
        """The date shown on the card: the last update, or the creation."""
        return (self.updated_at or self.created_at or "")[:10]


def function_info(row: Any) -> CommunityFunctionInfo:
    """Build a :class:`CommunityFunctionInfo` from one raw database row.

    Untrusted input: a missing / broken field simply yields its zero value
    instead of raising, so one bad row never breaks the list.
    """
    if not isinstance(row, dict):
        return CommunityFunctionInfo(name="Untitled")

    fx = text_of(row.get("fx"), 400)
    fy = text_of(row.get("fy"), 400)
    description = text_of(row.get("description"), MAX_DESCRIPTION_LEN)
    tags = normalize_tags(row.get("tags"))

    created_at = text_of(row.get("created_at"))
    updated_at = text_of(row.get("updated_at"))

    name = text_of(row.get("function_name") or row.get("name")) or "Untitled"
    uploader = text_of(row.get("uploader_name"), 80)

    return CommunityFunctionInfo(
        row_id=text_of(row.get("id"), 80),
        name=name,
        uploader=uploader,
        names=(name,),
        created_at=created_at,
        created_ts=timestamp_of(created_at),
        fx=fx,
        fy=fy,
        description=description,
        tags=tags,
        updated_at=updated_at,
        updated_ts=timestamp_of(updated_at),
        usage_count=int_of(row.get("usage_count")),
        successful_usage_count=int_of(row.get("successful_usage_count")),
        unique_user_count=int_of(row.get("unique_user_count")),
        favorite_count=int_of(row.get("favorite_count")),
        rating_count=int_of(row.get("rating_count")),
        rating_total=int_of(row.get("rating_total")),
    )


# --- filtering and sorting ---------------------------------------------------

def sort_label(sort_key: str, descending: bool = False) -> str:
    """Human readable label of a sort option, e.g. ``"Most used ↓"``."""
    return sort_label_for(SORT_TABLE, sort_key, descending)


def _sort_value(info: CommunityFunctionInfo, sort_key: str) -> float:
    """The number a function is sorted by."""
    if sort_key == SORT_USES:
        return float(info.usage_count)
    if sort_key == SORT_SUCCESS:
        return float(info.successful_usage_count)
    if sort_key == SORT_FAVORITES:
        return float(info.favorite_count)
    if sort_key == SORT_RATING:
        return info.average_rating
    if sort_key == SORT_OLDEST:
        return info.created_ts
    # newest: the creation time (0.0 when it cannot be parsed)
    return info.created_ts


def filter_functions(
    infos: Sequence[CommunityFunctionInfo],
    *,
    name_query: str = "",
    uploader_query: str = "",
    tag_query: str = "",
    min_uses: int = 0,
    sort_key: str = SORT_NEWEST,
    descending: Optional[bool] = None,
) -> list:
    """The functions that match the query, in the requested order.

    The two text queries are ANDed with the tag filter: a function must be
    close to both the name and the uploader query, and carry at least one
    tag that contains the tag query.  When a query is used the closeness
    decides the order (the closest function comes first); the sort option
    breaks the ties.
    """
    minima = {"usage_count": int_of(min_uses)} if min_uses else None
    tag = normalize_text(tag_query)

    def sort_value(info, key):
        return _sort_value(info, key)

    matched = filter_items(
        [info for info in (infos or ()) if tag_matches(tag, info.tags)],
        name_query=name_query,
        uploader_query=uploader_query,
        minima=minima,
        sort_key=sort_key,
        sort_table=SORT_TABLE,
        sort_value=sort_value,
        descending=descending,
    )
    return matched
