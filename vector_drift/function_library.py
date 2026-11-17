"""The Function Lab's library: the force functions the player saved.

A saved function is a named pair of expressions (``Fx`` and ``Fy``) the player
wrote in the Function Lab.  The library belongs to the player profile (the
local file and the cloud profile), so the functions survive a restart just
like the custom levels do.

Functions that came from the Community carry their origin with them
(``source="community"`` and ``community_id``), so the game can attribute the
usage statistics to the published row and the lab can show where a function
came from.

The module only knows about the data: the lab screen and the game screen's
function picker use it to store, list and restore the functions.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Iterable, Optional
from .community_function_browse import (
    MAX_DESCRIPTION_LEN,
    normalize_tags,
    parse_tags,
)

# A name is short enough to fit in a list row and a button.
MAX_NAME_LEN = 40
# How many functions one player may keep.
MAX_FUNCTIONS = 60
DEFAULT_NAME = "Untitled"
MAX_TAGS = 8
MAX_TAG_LEN = 24


@dataclass(frozen=True)
class SavedFunction:
    """A named pair of force expressions.

    ``source`` is ``"community"`` for a function imported from the Community
    page and ``None`` for one the player wrote.  ``community_id`` is the
    community row UUID an imported function came from (``None`` otherwise);
    it is what lets the game attribute usage to the published function.
    """

    id: str
    name: str
    fx: str
    fy: str
    description: str = ""
    tags: tuple = ()
    source: Optional[str] = None
    community_id: Optional[str] = None

    @property
    def from_community(self) -> bool:
        """True when the function was imported from the Community page."""
        return bool(self.community_id)

    def to_row(self) -> dict:
        """The plain data written into the player profile."""
        row = {"id": self.id, "name": self.name, "fx": self.fx, "fy": self.fy}
        if self.description:
            row["description"] = self.description
        if self.tags:
            row["tags"] = list(self.tags)
        if self.source:
            row["source"] = self.source
        if self.community_id:
            row["community_id"] = self.community_id
        return row

    @staticmethod
    def from_row(row: Any) -> Optional["SavedFunction"]:
        """Read one profile row; None when the row is not a function."""
        if not isinstance(row, dict):
            return None
        fx, fy = row.get("fx"), row.get("fy")
        if not isinstance(fx, str) or not isinstance(fy, str):
            return None
        raw_id = row.get("id")
        fid = str(raw_id) if isinstance(raw_id, (str, int)) and str(raw_id) else new_id()
        description = row.get("description")
        description = description.strip()[:MAX_DESCRIPTION_LEN] if isinstance(description, str) else ""
        tags = normalize_tags(row.get("tags")) if row.get("tags") is not None else ()
        source = row.get("source")
        source = str(source)[:40] if isinstance(source, str) and source.strip() else None
        community_id = row.get("community_id")
        community_id = str(community_id)[:80] if isinstance(community_id, str) and community_id.strip() else None
        return SavedFunction(id=fid, name=clean_name(row.get("name")), fx=fx, fy=fy,
                             description=description, tags=tags,
                             source=source, community_id=community_id)


def new_id() -> str:
    """A fresh id for a new function."""
    return uuid.uuid4().hex


def clean_name(name: Any) -> str:
    """A usable name: one line, not too long, never empty."""
    if not isinstance(name, str):
        name = ""
    name = " ".join(name.split())          # line breaks and runs of spaces become one space
    name = name[:MAX_NAME_LEN]
    return name or DEFAULT_NAME


def clean_description(description: Any) -> str:
    """A usable description: whitespace-collapsed, never too long."""
    if not isinstance(description, str):
        return ""
    return " ".join(description.split())[:MAX_DESCRIPTION_LEN]


def clean_tags(tags: Any) -> tuple:
    """A usable tag list: normalised, de-duplicated, capped."""
    if tags is None:
        return ()
    if isinstance(tags, str):
        return parse_tags(tags)
    return normalize_tags(tags)


def make_function(name: Any, fx: Any, fy: Any, *,
                  description: Any = "", tags: Any = (),
                  source: Optional[str] = None,
                  community_id: Optional[str] = None) -> SavedFunction:
    """A new saved function with a fresh id."""
    return SavedFunction(id=new_id(), name=clean_name(name),
                         fx="" if fx is None else str(fx),
                         fy="" if fy is None else str(fy),
                         description=clean_description(description),
                         tags=clean_tags(tags),
                         source=source, community_id=(str(community_id) if community_id else None))


def find_function(functions: Iterable[SavedFunction], fid: Any) -> Optional[SavedFunction]:
    """The function with this id, or None."""
    if not fid:
        return None
    for function in functions or ():
        if function.id == fid:
            return function
    return None


def unique_name(name: Any, functions: Iterable[SavedFunction]) -> str:
    """A name that does not collide with another function in the library.

    ``"Vortex"`` stays ``"Vortex"`` when it is free; otherwise the first free
    ``"Vortex (2)"``, ``"Vortex (3)"`` ... is returned.  Existing functions
    are never renamed or overwritten.
    """
    base = clean_name(name)
    taken = {clean_name(getattr(function, "name", "")).casefold() for function in functions or ()}
    if base.casefold() not in taken:
        return base
    for suffix in range(2, 1000):
        candidate = f"{base[:MAX_NAME_LEN - 5].rstrip()} ({suffix})"
        if candidate.casefold() not in taken:
            return candidate
    return f"{base[:MAX_NAME_LEN - 5].rstrip()} ({new_id()[:4]})"


def library_to_rows(functions: Iterable[SavedFunction]) -> list:
    """The library as plain rows for the player profile."""
    return [function.to_row() for function in (functions or ())]


def library_from_rows(rows: Any) -> list:
    """Profile rows -> a list of functions.

    Broken rows are skipped and duplicate ids get a new one, so a damaged
    profile can never break the lab.
    """
    functions, seen = [], set()
    for row in (rows if isinstance(rows, list) else ()):
        function = SavedFunction.from_row(row)
        if function is None:
            continue
        if function.id in seen:
            function = SavedFunction(id=new_id(), name=function.name,
                                     fx=function.fx, fy=function.fy,
                                     description=function.description,
                                     tags=function.tags,
                                     source=function.source,
                                     community_id=function.community_id)
        seen.add(function.id)
        functions.append(function)
    return functions[:MAX_FUNCTIONS]


__all__ = [
    "SavedFunction", "MAX_NAME_LEN", "MAX_FUNCTIONS", "DEFAULT_NAME",
    "MAX_TAGS", "MAX_TAG_LEN",
    "new_id", "clean_name", "clean_description", "clean_tags",
    "make_function", "find_function", "unique_name",
    "library_to_rows", "library_from_rows",
]
