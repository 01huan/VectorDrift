"""Step-by-step hints for the fixed levels, read from hints.toml.

Each fixed level 1-6 has steps shown one at a time, then a last page with
answer_note and one or more answers (Fx, Fy, optional label). Random levels
use the AI Solver instead and never have a hint.
"""

import tomllib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

HINTS_PATH = Path(__file__).resolve().parent / "hints.toml"
HINT_LEVEL_IDS = range(1, 7)        # fixed levels 1-6


class HintFormatError(ValueError):
    """hints.toml is malformed; the message names the level and the field."""


@dataclass(frozen=True)
class HintAnswer:
    fx: str
    fy: str
    label: str | None = None


@dataclass(frozen=True)
class LevelHint:
    level_id: int
    steps: tuple                    # tuple[str, ...], shown one per page
    answer_note: str
    answers: tuple                  # tuple[HintAnswer, ...], all on the last page


def _text(value):
    return isinstance(value, str) and value.strip() != ""


def _parse_answer(where, n, entry):
    if not isinstance(entry, dict):
        raise HintFormatError(f"{where}: answer {n} must be a table with 'fx' and 'fy'")
    for key in ("fx", "fy"):
        if key not in entry:
            raise HintFormatError(f"{where}: answer {n} is missing '{key}'")
        if not _text(entry[key]):
            raise HintFormatError(f"{where}: answer {n} '{key}' must be a non-empty string")
    label = entry.get("label")
    if label is not None and not _text(label):
        raise HintFormatError(f"{where}: answer {n} 'label' must be a non-empty string")
    unknown = set(entry) - {"fx", "fy", "label"}
    if unknown:
        raise HintFormatError(f"{where}: answer {n} has unknown keys {sorted(unknown)}")
    return HintAnswer(fx=entry["fx"], fy=entry["fy"], label=label)


def _parse_level(key, entry):
    try:
        level_id = int(key)
    except ValueError:
        raise HintFormatError(f"hints.toml: level key '{key}' is not a level number") from None
    where = f"hints.toml level {level_id}"
    if level_id not in HINT_LEVEL_IDS:
        raise HintFormatError(f"{where}: hints are only for the fixed levels "
                              f"{HINT_LEVEL_IDS.start}-{HINT_LEVEL_IDS.stop - 1}")
    if not isinstance(entry, dict):
        raise HintFormatError(f"{where}: must be a table")

    steps = entry.get("steps")
    if not isinstance(steps, list) or not steps or not all(_text(s) for s in steps):
        raise HintFormatError(f"{where}: 'steps' must be a non-empty list of non-empty strings")
    if not _text(entry.get("answer_note")):
        raise HintFormatError(f"{where}: 'answer_note' must be a non-empty string")
    answers = entry.get("answers")
    if not isinstance(answers, list) or not answers:
        raise HintFormatError(f"{where}: 'answers' must be a non-empty list")
    unknown = set(entry) - {"steps", "answer_note", "answers"}
    if unknown:
        raise HintFormatError(f"{where}: unknown keys {sorted(unknown)}")

    return LevelHint(
        level_id=level_id,
        steps=tuple(steps),
        answer_note=entry["answer_note"],
        answers=tuple(_parse_answer(where, n, a) for n, a in enumerate(answers, start=1)),
    )


def parse_hints(data):
    """Check parsed TOML data and return {level_id: LevelHint}."""
    unknown = set(data) - {"level"}
    if unknown:
        raise HintFormatError(f"hints.toml: unknown top-level keys {sorted(unknown)}")
    levels = data.get("level", {})
    if not isinstance(levels, dict):
        raise HintFormatError("hints.toml: 'level' must be a table of [level.N] entries")
    return {hint.level_id: hint for hint in (_parse_level(k, v) for k, v in levels.items())}


def load_hints(path=HINTS_PATH):
    """Read and check a hints file; returns {level_id: LevelHint}."""
    with open(path, "rb") as f:
        try:
            data = tomllib.load(f)
        except tomllib.TOMLDecodeError as exc:
            raise HintFormatError(f"{Path(path).name}: {exc}") from None
    return parse_hints(data)


@lru_cache(maxsize=1)
def _hints():
    return load_hints()


def get_hint(level_id):
    """The hint for ``level_id``, or None if the level has none (random levels)."""
    return _hints().get(level_id)
