"""Shared machinery for the Community browsers.

The Community has several content types (levels today, functions as well,
and more can be added later).  Everything that is the *same* for every
content type lives here:

* text normalisation and fuzzy matching (:class:`FuzzyMatcher`);
* parsing of untrusted database rows (``_text`` / ``_int`` / ``_float`` /
  ``_timestamp``);
* the :class:`CommunityItemInfo` value object every content type reduces a
  row to;
* generic filtering and sorting (:func:`filter_items`, :func:`sort_label`);
* generic sort-key tables (:class:`SortOption`, :class:`SortTable`).

The module is deliberately free of pygame so it can be unit tested on its
own; each content type builds its browse rules on top of it (see
:mod:`vector_drift.community_browse` for levels and
:mod:`vector_drift.community_function_browse` for functions).
"""

from __future__ import annotations

import difflib
import unicodedata
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Optional, Sequence

__all__ = [
    "MIN_MATCH_SCORE", "MIN_COVERAGE",
    "normalize_text", "text_of", "int_of", "float_of", "timestamp_of",
    "average_rating", "round_half_up",
    "FuzzyMatcher", "fuzzy_score", "cached_matcher",
    "CommunityItemInfo",
    "SortOption", "SortTable",
    "filter_items", "sort_label_for",
    "SORT_NEWEST", "SORT_OLDEST",
]

SORT_NEWEST = "newest"
SORT_OLDEST = "oldest"

# A text only counts as a match from this similarity on.  Below it the item
# is dropped from the result list.
MIN_MATCH_SCORE = 0.30
# At least this share of the query has to be found in the text.  It keeps a
# long query from matching a short, unrelated name by accident.
MIN_COVERAGE = 0.50
# Upper bound on the per-matcher text-score cache (the matcher itself is
# kept in the smaller _MATCHER_CACHE).
_MATCHER_TEXT_CACHE_MAX = 512


# --- text helpers -----------------------------------------------------------

def normalize_text(text: Any) -> str:
    """Case-folded, accent-free, whitespace-collapsed text.

    Used for every comparison, so "Drift  Maze" and "drift maze" compare as
    the same query.  ``casefold`` handles non-ASCII casing; NFKD + dropping
    combining marks makes "Ünbound" match "unbound".
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


def text_of(value: Any, limit: int = 200) -> str:
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


def int_of(value: Any, default: int = 0) -> int:
    """A non-negative integer, or ``default`` when the value is unusable."""
    if isinstance(value, bool):
        return default
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return number if number >= 0 else default


def float_of(value: Any, default: float = 0.0) -> float:
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


def round_half_up(value: Any) -> int:
    """Round to a whole number, halves away from zero (4.5 -> 5).

    ``round()`` uses banker's rounding (4.5 -> 4), which makes a displayed
    average look one star short when the stored total lands exactly on a
    half.  Star widgets use this so the stars always agree with the text.
    """
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return 0
    if number != number or number in (float("inf"), float("-inf")):
        return 0
    return int(number + 0.5) if number >= 0 else -int(-number + 0.5)


def average_rating(rating_total: Any, rating_count: Any) -> float:
    """The mean rating (0.0 .. 5.0), or 0.0 when nobody has rated yet."""
    total = float_of(rating_total)
    count = int_of(rating_count)
    if count <= 0:
        return 0.0
    return max(0.0, min(5.0, total / count))


def timestamp_of(text: str) -> float:
    """Seconds since the epoch for an ISO-8601 timestamp (0.0 when unknown).

    A timestamp without an offset is read as UTC: database timestamps are
    UTC, and the local timezone must never change how items are ordered.
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


# --- the browsable item ------------------------------------------------------

@dataclass(frozen=True)
class CommunityItemInfo:
    """One community item, reduced to what the browser needs.

    Every field is already validated: the row comes from a public table that
    anybody can write to.  Content types either use this as is or subclass it
    (adding ``frozen=True`` fields with defaults).
    """

    row_id: str = ""
    name: str = ""
    uploader: str = ""
    names: tuple = ()               # every name the item can be found by
    created_at: str = ""
    created_ts: float = 0.0

    def search_texts(self) -> tuple:
        """The texts a name query is compared against."""
        return self.names or ((self.name,) if self.name else ())


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

    Scores are cached per text, so changing the sort order or the filters
    never re-scores anything.
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
        key = text if isinstance(text, str) else text_of(text, 200)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        if len(self._cache) >= _MATCHER_TEXT_CACHE_MAX:
            self._cache.clear()
        value = self._score(key)
        self._cache[key] = value
        return value

    def best(self, texts: Iterable[Any]) -> float:
        """The highest score over several texts (e.g. the item's names)."""
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
        # that cannot cover enough of the query, the item does not match.
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
# change of the filters (only a new query has to be scored again).  It is a
# small LRU: a handful of queries is kept, older ones are evicted one by one.
_MATCHER_CACHE: "OrderedDict[str, FuzzyMatcher]" = OrderedDict()
_MATCHER_CACHE_LIMIT = 16


def cached_matcher(query: Any) -> FuzzyMatcher:
    """The matcher for ``query`` (reused, so its scores stay cached)."""
    key = normalize_text(query)
    if not key:
        return FuzzyMatcher(query)
    matcher = _MATCHER_CACHE.get(key)
    if matcher is not None:
        _MATCHER_CACHE.move_to_end(key)
        return matcher
    if len(_MATCHER_CACHE) >= _MATCHER_CACHE_LIMIT:
        _MATCHER_CACHE.popitem(last=False)
    matcher = FuzzyMatcher(query)
    _MATCHER_CACHE[key] = matcher
    return matcher


# --- sort tables --------------------------------------------------------------

@dataclass(frozen=True)
class SortOption:
    """One sortable order: its key, its label and its default direction."""

    key: str
    label: str
    default_descending: bool


@dataclass(frozen=True)
class SortTable:
    """The sort options of one content type, with their key lookup."""

    options: tuple  # tuple[SortOption]

    @property
    def keys(self) -> tuple:
        return tuple(option.key for option in self.options)

    @property
    def labels(self) -> dict:
        return {option.key: option.label for option in self.options}

    @property
    def default_descending(self) -> dict:
        return {option.key: option.default_descending for option in self.options}

    def label(self, key: str, descending: bool = False) -> str:
        """Human readable label of a sort option, e.g. ``"Name ↑"``."""
        text = self.labels.get(key, str(key))
        return f"{text} {'↓' if descending else '↑'}"


def sort_label_for(table: SortTable, sort_key: str, descending: bool = False) -> str:
    """Human readable label of a sort option in ``table``."""
    return table.label(sort_key, descending)


# --- filtering and sorting ---------------------------------------------------

def filter_items(
    infos: Sequence,
    *,
    name_query: str = "",
    uploader_query: str = "",
    minima: Optional[dict] = None,
    sort_key: str,
    sort_table: SortTable,
    sort_value: Callable[[Any, str], float],
    descending: Optional[bool] = None,
) -> list:
    """The items that match the query, in the requested order.

    The two text queries are ANDed: an item must be close to *both* the name
    and the uploader query.  When a query is used the closeness decides the
    order (the closest item comes first); the sort option breaks the ties.
    Without a query the sort option alone decides the order.

    ``minima`` maps an attribute name on the item info to the smallest value
    it may have (larger values keep the item).  ``sort_value(info, key)``
    returns the number an item is sorted by for ``key``.
    """
    name_matcher = cached_matcher(name_query)
    uploader_matcher = cached_matcher(uploader_query)

    minima = {attr: max(0, int_of(value)) for attr, value in (minima or {}).items()}

    keys = sort_table.keys
    defaults = sort_table.default_descending
    key = sort_key if sort_key in keys else (keys[0] if keys else SORT_NEWEST)
    reverse = defaults.get(key, False) if descending is None else bool(descending)
    query_active = name_matcher.active or uploader_matcher.active

    matched = []
    for info in infos or ():
        skip = False
        for attr, minimum in minima.items():
            if minimum and int_of(getattr(info, attr, 0)) < minimum:
                skip = True
                break
        if skip:
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
        # The sort value is kept with the item so it can be the tie-breaker
        # of a single sort below.
        matched.append((score, info, sort_value(info, key)))

    if query_active:
        # Two stable sorts (sort value, then closeness, descending) collapse
        # into one: closeness descending first; ties break by the requested
        # order direction.  (``-t[0]`` is only used when ``reverse`` is
        # False: the closeness is still descending, the tie-break ascending.)
        if reverse:
            matched.sort(key=lambda t: (t[0], t[2]), reverse=True)
        else:
            matched.sort(key=lambda t: (-t[0], t[2]), reverse=False)
    else:
        matched.sort(key=lambda t: t[2], reverse=reverse)
    return [info for _score, info, _sv in matched]
