"""The Function Lab's library: the force functions the player saved.

A saved function is a named pair of expressions (``Fx`` and ``Fy``) the player
wrote in the Function Lab.  The library belongs to the player profile (the
local file and the cloud profile), so the functions survive a restart just
like the custom levels do.

The module only knows about the data: the lab screen and the game screen's
function picker use it to store, list and restore the functions.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Iterable, Optional

# A name is short enough to fit in a list row and a button.
MAX_NAME_LEN = 40
# How many functions one player may keep.
MAX_FUNCTIONS = 60
DEFAULT_NAME = "Untitled"


@dataclass(frozen=True)
class SavedFunction:
    """A named pair of force expressions."""

    id: str
    name: str
    fx: str
    fy: str

    def to_row(self) -> dict:
        """The plain data written into the player profile."""
        return {"id": self.id, "name": self.name, "fx": self.fx, "fy": self.fy}

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
        return SavedFunction(id=fid, name=clean_name(row.get("name")), fx=fx, fy=fy)


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


def make_function(name: Any, fx: Any, fy: Any) -> SavedFunction:
    """A new saved function with a fresh id."""
    return SavedFunction(id=new_id(), name=clean_name(name),
                         fx="" if fx is None else str(fx),
                         fy="" if fy is None else str(fy))


def find_function(functions: Iterable[SavedFunction], fid: Any) -> Optional[SavedFunction]:
    """The function with this id, or None."""
    if not fid:
        return None
    for function in functions or ():
        if function.id == fid:
            return function
    return None


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
                                     fx=function.fx, fy=function.fy)
        seen.add(function.id)
        functions.append(function)
    return functions[:MAX_FUNCTIONS]


__all__ = [
    "SavedFunction", "MAX_NAME_LEN", "MAX_FUNCTIONS", "DEFAULT_NAME",
    "new_id", "clean_name", "make_function", "find_function",
    "library_to_rows", "library_from_rows",
]
