"""Search, filter and sort rules for the community level browser.

The **Public Levels** page shows levels anybody uploaded.  This module owns
every rule about *which* levels are listed and *in which order*:

* :func:`level_info` turns one raw database row into a small, safe value
  object (name, uploader, time limit, obstacle / pickup counts, play
  statistics).  The row is untrusted, so every field is parsed defensively.
* :class:`FuzzyMatcher` scores how close a query is to a text (0..1).  The
  score is cached per text, so re-sorting never re-scores anything.
* :func:`filter_levels` combines the two text queries, the numeric minimum
  filters and the sort order into the final list.

The module is deliberately free of pygame: the browser scene only draws what
this module decides, and the rules can be unit tested on their own.
"""

from __future__ import annotations

import difflib
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Optional, Sequence

__all__ = [
    "PICKUP_KINDS", "PICKUP_LABELS", "DEFAULT_PICKUP_KIND",
    "SORT_OPTIONS", "SORT_KEYS", "SORT_LABELS", "SORT_DEFAULT_DESCENDING",
    "SORT_NEWEST", "SORT_OLDEST", "SORT_TIME", "SORT_OBSTACLES",
    "SORT_PICKUPS", "SORT_PICKUP", "SORT_PLAYS", "SORT_CLEARS",
    "SORT_CLEARERS",
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
)
SORT_KEYS = tuple(key for key, _label, _desc in SORT_OPTIONS)
SORT_LABELS = {key: label for key, label, _desc in SORT_OPTIONS}
SORT_DEFAULT_DESCENDING = {key: desc for key, _label, desc in SORT_OPTIONS}

# A text only counts as a match from this similarity on.  Below it the level
# is dropped from the result list.
MIN_MATCH_SCORE = 0.30
# At least this share of the query has to be found in the text.  It keeps a
# long query from matching a short, unrelated name by accident.
MIN_COVERAGE = 0.50


# --- text helpers -----------------------------------------------------------

def normalize_text(text: Any) -> str:
    """Case-folded, accent-free, whitespace-collapsed text.

    Used for every comparison, so "Drift  Maze" and "drift maze" compare as
    the same query.  ``casefold`` handles non-ASCII casing;
    NFKD + dropping combining marks makes "Ünbound" match "unbound".
    """
    if text is None:
        return ""
    if not isinstance(text, str):
        try:
            text = str(text)
        except Exception:  # pragma: no cover - defensive
            return ""
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join(stripped.casefold().split())


def _text(value: Any, limit: int = 200) -> str:
    """A trimmed string, never longer than ``limit`` characters."""
    if value is None:
        return ""
    if not isinstance(value, str):
        try:
            value = str(value)
        except Exception:  # pragma: no cover - defensive
            return ""
    value = value.strip()
    return value[:limit]


def _int(value: Any, default: int = 0) -> int:
    """A non-negative integer, or ``default`` when the value is unusable."""
    if isinstance(value, bool):
        return default
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return number if number >= 0 else default


def _float(value: Any, default: float = 0.0) -> float:
    """A finite float, or ``default`` when the value is unusable."""
    if isinstance(value, bool):
        return default
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    if number != number or number in (float("inf"), float("-inf")):
        return default
    return number


def _timestamp(text: str) -> float:
    """Seconds since the epoch for an ISO-8601 timestamp (0.0 when unknown).

    A timestamp without an offset is read as UTC: database timestamps are
    UTC, and the local timezone must never change how levels are ordered.
    """
    if not text:
        return 0.0
    cleaned = text.strip()
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(cleaned)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp()
    except (TypeError, ValueError, OverflowError, OSError):
        # OSError: Windows mktime() rejects dates outside its range.
        return 0.0


# --- the browsable level ----------------------------------------------------

@dataclass(frozen=True)
class CommunityLevelInfo:
    """One community level, reduced to what the browser needs.

    Every field is already validated: the row comes from a public table that
    anybody can write to.
    """

    row_id: str = ""
    name: str = ""
    uploader: str = ""
    names: tuple = ()               # every name the level can be found by
    created_at: str = ""
    created_ts: float = 0.0
    time_limit: float = 0.0
    obstacle_count: int = 0
    pickup_count: int = 0
    pickup_counts: tuple = ()       # ((kind, count), ...) sorted by kind
    play_count: int = 0
    clear_count: int = 0
    clear_player_count: int = 0
    level_data: dict = field(default_factory=dict)

    def count_of(self, kind: str) -> int:
        """How many pickups of ``kind`` the level holds (0 for unknown kinds)."""
        for name, count in self.pickup_counts:
            if name == kind:
                return int(count)
        return 0

    def search_texts(self) -> tuple:
        """The texts a name query is compared against."""
        return self.names or ((self.name,) if self.name else ())


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

    row_name = _text(row.get("level_name"))
    data_name = _text(data.get("name"))
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
                kind = _text(item.get("kind"), 40).lower() or "shockwave"
            pickup_counts[kind] = pickup_counts.get(kind, 0) + 1

    created_at = _text(row.get("created_at"))
    clear_players = row.get("clear_players")
    if isinstance(clear_players, (list, tuple)):
        clear_player_count = len(clear_players)
    else:
        clear_player_count = _int(row.get("clear_player_count"))

    return CommunityLevelInfo(
        row_id=_text(row.get("id"), 80),
        name=name,
        uploader=_text(row.get("uploader_name"), 80),
        names=names,
        created_at=created_at,
        created_ts=_timestamp(created_at),
        time_limit=_float((sections[0].get("time_limit") if isinstance(sections, (list, tuple)) and sections and isinstance(sections[0], dict) else data.get("time_limit")), 0.0),
        obstacle_count=obstacle_count,
        pickup_count=pickup_count,
        pickup_counts=tuple(sorted(pickup_counts.items())),
        play_count=_int(row.get("play_count")),
        clear_count=_int(row.get("clear_count")),
        clear_player_count=clear_player_count,
        level_data=data,
    )


# --- fuzzy matching ---------------------------------------------------------

class FuzzyMatcher:
    """Scores how close a query is to a text (0.0 .. 1.0).

    * an exact match scores 1.0;
    * a query contained in the text scores 0.9 .. 1.0 (a longer text is a
      slightly weaker match);
    * otherwise the matched characters decide: *coverage* is the share of the
      query that was found (too little and the text does not match at all),
      *precision* is the share of the text the query explains.  Their product
      puts the closest text first.

    Scores are cached per text, so changing the sort order or the numeric
    filters never re-scores the levels.
    """

    def __init__(self, query: Any = ""):
        self.query = normalize_text(query)
        self._cache: dict = {}
        self._matcher = difflib.SequenceMatcher(None, self.query) if self.query else None

    @property
    def active(self) -> bool:
        """True when there is a query to match against."""
        return bool(self.query)

    def score(self, text: Any) -> float:
        """Similarity of ``text`` to the query (0.0 when there is no query)."""
        if self._matcher is None:
            return 0.0
        key = text if isinstance(text, str) else _text(text, 200)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        value = self._score(key)
        self._cache[key] = value
        return value

    def best(self, texts: Iterable[Any]) -> float:
        """The highest score over several texts (the level's names)."""
        best = 0.0
        for text in texts or ():
            value = self.score(text)
            if value > best:
                best = value
                if best >= 1.0:
                    break
        return best

    def _score(self, text: str) -> float:
        target = normalize_text(text)
        if not target:
            return 0.0
        query = self.query
        if target == query:
            return 1.0
        if query in target:
            # Contained: a strong match, slightly weaker the longer the text is.
            return 0.90 + 0.10 * (len(query) / len(target))

        matcher = self._matcher
        matcher.set_seq2(target)
        # Cheap upper bound on the number of matching characters: when even
        # that cannot cover enough of the query, the level does not match.
        upper = matcher.quick_ratio() * (len(query) + len(target)) / 2.0
        if upper / len(query) < MIN_COVERAGE:
            return 0.0
        blocks = matcher.get_matching_blocks()
        matched = sum(block.size for block in blocks)
        if not matched:
            return 0.0
        # How much of the query was found (coverage) and how much of the text
        # it explains (precision).  Both matter: the first keeps unrelated
        # names out, the second puts the closest name first.
        coverage = matched / len(query)
        if coverage < MIN_COVERAGE:
            return 0.0
        precision = matched / len(target)
        score = coverage * (0.5 + 0.5 * precision)
        return score if score >= MIN_MATCH_SCORE else 0.0


def fuzzy_score(query: Any, text: Any) -> float:
    """Similarity of ``text`` to ``query`` (0.0 .. 1.0).

    Convenience wrapper around :class:`FuzzyMatcher` for one-off use.
    """
    return FuzzyMatcher(query).score(text)


# One matcher per query text, so its score cache survives a re-sort or a
# change of the numeric filters (only a new query has to be scored again).
_MATCHER_CACHE: dict = {}
_MATCHER_CACHE_LIMIT = 8


def _cached_matcher(query: Any) -> FuzzyMatcher:
    """The matcher for ``query`` (reused, so its scores stay cached)."""
    key = normalize_text(query)
    if not key:
        return FuzzyMatcher(query)
    matcher = _MATCHER_CACHE.get(key)
    if matcher is None:
        if len(_MATCHER_CACHE) >= _MATCHER_CACHE_LIMIT:
            _MATCHER_CACHE.clear()
        matcher = FuzzyMatcher(query)
        _MATCHER_CACHE[key] = matcher
    return matcher


# --- filtering and sorting --------------------------------------------------

def sort_label(sort_key: str, descending: bool = False) -> str:
    """Human readable label of a sort option, e.g. ``"Time limit ↑"``."""
    label = SORT_LABELS.get(sort_key, str(sort_key))
    return f"{label} {'↓' if descending else '↑'}"


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
    """The levels that match the query, in the requested order.

    The two text queries are ANDed: a level must be close to *both* the name
    and the uploader query.  When a query is used the closeness decides the
    order (the closest level comes first); the sort option breaks the ties.
    Without a query the sort option alone decides the order.
    """
    name_matcher = _cached_matcher(name_query)
    uploader_matcher = _cached_matcher(uploader_query)

    min_plays = max(0, _int(min_plays))
    min_clears = max(0, _int(min_clears))
    min_clearers = max(0, _int(min_clearers))

    key = sort_key if sort_key in SORT_KEYS else SORT_NEWEST
    reverse = SORT_DEFAULT_DESCENDING[key] if descending is None else bool(descending)
    kind = pickup_kind if pickup_kind else DEFAULT_PICKUP_KIND

    matched = []
    for info in infos or ():
        if min_plays and info.play_count < min_plays:
            continue
        if min_clears and info.clear_count < min_clears:
            continue
        if min_clearers and info.clear_player_count < min_clearers:
            continue
        score = 1.0
        if name_matcher.active:
            value = name_matcher.best(info.search_texts())
            if value <= 0.0:
                continue
            score = min(score, value)
        if uploader_matcher.active:
            value = uploader_matcher.score(info.uploader)
            if value <= 0.0:
                continue
            score = min(score, value)
        matched.append((score, info))

    # First the requested order, then the closeness (a stable sort keeps the
    # requested order inside equally close levels).
    matched.sort(key=lambda pair: _sort_value(pair[1], key, kind), reverse=reverse)
    if name_matcher.active or uploader_matcher.active:
        matched.sort(key=lambda pair: pair[0], reverse=True)
    return [info for _score, info in matched]
