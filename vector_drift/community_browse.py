"""Search, filter and sort rules for the community level browser.

The **Levels** tab of the Community page lists the levels anybody uploaded.
This module owns every rule about *which* levels are listed and *in which
order*:

* :func:`level_info` turns one raw database row into a small, safe value
  object (name, uploader, time limit, obstacle / pickup counts, play
  statistics).  The row is untrusted, so every field is parsed defensively.
* The text matching and the generic filter machinery live in
  :mod:`vector_drift.community_core` (shared with the other content types).
* :func:`filter_levels` combines the two text queries, the numeric minimum
  filters and the sort order into the final list.

The module is deliberately free of pygame: the browser scene only draws what
this module decides, and the rules can be unit tested on their own.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Sequence

from .community_core import (
    MIN_COVERAGE,
    MIN_MATCH_SCORE,
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
    text_of,
    timestamp_of,
)

__all__ = [
    "PICKUP_KINDS", "PICKUP_LABELS", "DEFAULT_PICKUP_KIND",
    "SORT_OPTIONS", "SORT_KEYS", "SORT_LABELS", "SORT_DEFAULT_DESCENDING",
    "SORT_NEWEST", "SORT_OLDEST", "SORT_TIME", "SORT_OBSTACLES",
    "SORT_PICKUPS", "SORT_PICKUP", "SORT_PLAYS", "SORT_CLEARS",
    "SORT_CLEARERS", "SORT_FAVORITES", "SORT_RATING",
    "CommunityLevelInfo", "level_info", "FuzzyMatcher", "fuzzy_score",
    "filter_levels", "sort_label", "normalize_text",
]

# --- pickup kinds -----------------------------------------------------------
# The kinds the game knows about (sprites.PICKUP_RENDERERS).  They are listed
# here so the browser can sort by "how many of this pickup" without importing
# pygame; tests keep the two lists in sync.
PICKUP_KINDS = ("shockwave", "extratime", "shield", "life", "money", "unbound")
PICKUP_LABELS = {
    "shockwave": "Shockwave",
    "extratime": "Extra time",
    "shield": "Shield",
    "life": "Life",
    "money": "Money",
    "unbound": "Unbound",
}
DEFAULT_PICKUP_KIND = "money"

# --- sort options -----------------------------------------------------------
SORT_NEWEST = "newest"
SORT_OLDEST = "oldest"
SORT_TIME = "time"
SORT_OBSTACLES = "obstacles"
SORT_PICKUPS = "pickups"
SORT_PICKUP = "pickup"
SORT_PLAYS = "plays"
SORT_CLEARS = "clears"
SORT_CLEARERS = "clearers"
SORT_FAVORITES = "favorites"
SORT_RATING = "rating"

# (key, label, default direction).  "newest" is the order the server sends,
# so it is the default; the numeric ones default to the useful direction
# (easiest first for the layout numbers, most played first for the stats).
SORT_OPTIONS = (
    (SORT_NEWEST, "Newest", True),
    (SORT_OLDEST, "Oldest", False),
    (SORT_TIME, "Time limit", False),
    (SORT_OBSTACLES, "Obstacles", False),
    (SORT_PICKUPS, "Pickups", False),
    (SORT_PICKUP, "Pickup kind", False),
    (SORT_PLAYS, "Plays", True),
    (SORT_CLEARS, "Clears", True),
    (SORT_CLEARERS, "Clearers", True),
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


# --- the browsable level ----------------------------------------------------

@dataclass(frozen=True)
class CommunityLevelInfo(CommunityItemInfo):
    """One community level, reduced to what the browser needs.

    Every field is already validated: the row comes from a public table that
    anybody can write to.
    """

    time_limit: float = 0.0
    obstacle_count: int = 0
    pickup_count: int = 0
    pickup_counts: tuple = ()       # ((kind, count), ...) sorted by kind
    play_count: int = 0
    clear_count: int = 0
    clear_player_count: int = 0
    favorite_count: int = 0
    rating_count: int = 0
    rating_total: int = 0
    level_data: dict = field(default_factory=dict)

    @property
    def average_rating(self) -> float:
        """The mean rating (0.0 when nobody has rated yet)."""
        return average_rating(self.rating_total, self.rating_count)

    def count_of(self, kind: str) -> int:
        """How many pickups of ``kind`` the level holds (0 for unknown kinds)."""
        for name, count in self.pickup_counts:
            if name == kind:
                return int(count)
        return 0


def level_info(row: Any) -> CommunityLevelInfo:
    """Build a :class:`CommunityLevelInfo` from one raw database row.

    Untrusted input: a missing / broken ``level_data`` simply yields zero
    counts instead of raising, so one bad row never breaks the list.
    """
    if not isinstance(row, dict):
        return CommunityLevelInfo()

    data = row.get("level_data")
    if not isinstance(data, dict):
        data = {}

    row_name = text_of(row.get("level_name"))
    data_name = text_of(data.get("name"))
    name = row_name or data_name or "Community"
    names = tuple(dict.fromkeys(n for n in (row_name, data_name) if n))

    sections = data.get("sections")
    if isinstance(sections, (list, tuple)) and sections:
        obstacle_count = 0
        pickup_list = []
        for s in sections:
            if not isinstance(s, dict):
                continue
            obs = s.get("obstacles")
            if isinstance(obs, (list, tuple)):
                obstacle_count += len(obs)
            ps = s.get("pickups")
            if isinstance(ps, (list, tuple)):
                pickup_list.extend(ps)
        pickups = pickup_list
    else:
        obstacles = data.get("obstacles")
        obstacle_count = len(obstacles) if isinstance(obstacles, (list, tuple)) else 0
        pickups = data.get("pickups")

    pickup_counts: dict = {}
    pickup_count = 0
    if isinstance(pickups, (list, tuple)):
        for item in pickups:
            pickup_count += 1
            kind = "shockwave"
            if isinstance(item, dict):
                kind = text_of(item.get("kind"), 40).lower() or "shockwave"
            pickup_counts[kind] = pickup_counts.get(kind, 0) + 1

    created_at = text_of(row.get("created_at"))
    clear_players = row.get("clear_players")
    if isinstance(clear_players, (list, tuple)):
        clear_player_count = len(clear_players)
    else:
        clear_player_count = int_of(row.get("clear_player_count"))

    return CommunityLevelInfo(
        row_id=text_of(row.get("id"), 80),
        name=name,
        uploader=text_of(row.get("uploader_name"), 80),
        names=names,
        created_at=created_at,
        created_ts=timestamp_of(created_at),
        time_limit=float_of((sections[0].get("time_limit") if isinstance(sections, (list, tuple)) and sections and isinstance(sections[0], dict) else data.get("time_limit")), 0.0),
        obstacle_count=obstacle_count,
        pickup_count=pickup_count,
        pickup_counts=tuple(sorted(pickup_counts.items())),
        play_count=int_of(row.get("play_count")),
        clear_count=int_of(row.get("clear_count")),
        clear_player_count=clear_player_count,
        favorite_count=int_of(row.get("favorite_count")),
        rating_count=int_of(row.get("rating_count")),
        rating_total=int_of(row.get("rating_total")),
        level_data=data,
    )


# --- filtering and sorting --------------------------------------------------

def sort_label(sort_key: str, descending: bool = False) -> str:
    """Human readable label of a sort option, e.g. ``"Time limit ↑"``."""
    return SORT_TABLE.label(sort_key, descending)


def _sort_value(info: CommunityLevelInfo, sort_key: str, pickup_kind: str) -> float:
    """The number a level is sorted by."""
    if sort_key == SORT_TIME:
        return info.time_limit
    if sort_key == SORT_OBSTACLES:
        return float(info.obstacle_count)
    if sort_key == SORT_PICKUPS:
        return float(info.pickup_count)
    if sort_key == SORT_PICKUP:
        return float(info.count_of(pickup_kind))
    if sort_key == SORT_PLAYS:
        return float(info.play_count)
    if sort_key == SORT_CLEARS:
        return float(info.clear_count)
    if sort_key == SORT_CLEARERS:
        return float(info.clear_player_count)
    if sort_key == SORT_FAVORITES:
        return float(info.favorite_count)
    if sort_key == SORT_RATING:
        return info.average_rating
    # newest / oldest: the upload time (0.0 when it cannot be parsed)
    return info.created_ts


def filter_levels(
    infos: Sequence[CommunityLevelInfo],
    *,
    name_query: str = "",
    uploader_query: str = "",
    min_plays: int = 0,
    min_clears: int = 0,
    min_clearers: int = 0,
    sort_key: str = SORT_NEWEST,
    descending: Optional[bool] = None,
    pickup_kind: str = DEFAULT_PICKUP_KIND,
) -> list:
    """The levels that match the query, in the requested order."""
    kind = pickup_kind if pickup_kind else DEFAULT_PICKUP_KIND

    return filter_items(
        infos,
        name_query=name_query,
        uploader_query=uploader_query,
        minima={
            "play_count": min_plays,
            "clear_count": min_clears,
            "clear_player_count": min_clearers,
        },
        sort_key=sort_key,
        sort_table=SORT_TABLE,
        sort_value=lambda info, key: _sort_value(info, key, kind),
        descending=descending,
    )
