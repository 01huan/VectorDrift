"""Step-by-step hints for the fixed levels, read from hints.toml.

Every fixed level (data.LEVELS, random levels excluded) has steps shown one
at a time, then a last page with answer_note and one or more answers (Fx,
Fy, optional label). A multi-section level has one such hint per section
instead, as [level.N.section.K] tables (K = 1 .. number of sections).
Random levels use the AI Solver instead and never have a hint.
"""

import tomllib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

HINTS_PATH = Path(__file__).resolve().parent / "hints.toml"
HINT_KEYS = {"steps", "answer_note", "answers"}


def hint_level_ids():
    """Ids that may have a hint: every fixed level in data.LEVELS, never a random one."""
    from .data import LEVELS
    from .level_presets import is_dynamic_level
    return tuple(lv.id for lv in LEVELS if not is_dynamic_level(lv.id))


def _level_sections(level_id):
    """How many sections hints.toml must give ``level_id`` (0 = one-screen level)."""
    from .data import get_level
    return len(get_level(level_id).sections)


class HintFormatError(ValueError):
    """hints.toml is malformed; the message names the level (and section) and the field."""


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
    section: int | None = None      # 1-based section number on multi-section levels


@dataclass(frozen=True)
class SectionedHint:
    """The hints of a multi-section level: ``sections[k]`` is section k + 1's."""

    level_id: int
    sections: tuple                 # tuple[LevelHint, ...]


def hint_sections(hint):
    """Every per-screen LevelHint of a parsed hint (a one-screen level has one)."""
    return hint.sections if isinstance(hint, SectionedHint) else (hint,)


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


def _parse_hint(where, level_id, entry, section=None):
    """One screen's hint: steps, answer_note and answers."""
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
    unknown = set(entry) - HINT_KEYS
    if unknown:
        raise HintFormatError(f"{where}: unknown keys {sorted(unknown)}")

    return LevelHint(
        level_id=level_id,
        steps=tuple(steps),
        answer_note=entry["answer_note"],
        answers=tuple(_parse_answer(where, n, a) for n, a in enumerate(answers, start=1)),
        section=section,
    )


def _parse_sections(where, level_id, sections, expected):
    """[level.N.section.K] tables: exactly K = 1 .. expected, each a full hint."""
    if not isinstance(sections, dict):
        raise HintFormatError(f"{where}: 'section' must be a table of "
                              f"[level.{level_id}.section.K] entries")
    if not expected:
        raise HintFormatError(f"{where}: is a one-screen level; give its hint without 'section'")
    numbers = []
    for key in sections:
        try:
            numbers.append(int(key))
        except ValueError:
            raise HintFormatError(f"{where} section '{key}': not a section number") from None
    for want, got in enumerate(sorted(numbers), start=1):
        if got != want:
            raise HintFormatError(f"{where} section {got}: sections must be numbered "
                                  f"1-{expected} in a row (section {want} is missing)")
    if len(numbers) < expected:
        raise HintFormatError(f"{where} section {len(numbers) + 1}: missing; the level has "
                              f"{expected} sections and each needs a hint")
    if len(numbers) > expected:
        raise HintFormatError(f"{where} section {expected + 1}: the level has only "
                              f"{expected} sections")
    by_number = {int(k): v for k, v in sections.items()}
    return SectionedHint(level_id=level_id, sections=tuple(
        _parse_hint(f"{where} section {n}", level_id, by_number[n], section=n)
        for n in range(1, expected + 1)))


def _parse_level(key, entry):
    try:
        level_id = int(key)
    except ValueError:
        raise HintFormatError(f"hints.toml: level key '{key}' is not a level number") from None
    where = f"hints.toml level {level_id}"
    allowed = hint_level_ids()
    if level_id not in allowed:
        raise HintFormatError(f"{where}: hints are only for the fixed levels "
                              f"{', '.join(map(str, allowed))} (random levels use the AI Solver)")
    if not isinstance(entry, dict):
        raise HintFormatError(f"{where}: must be a table")

    expected = _level_sections(level_id)
    if "section" in entry:
        mixed = sorted(set(entry) & HINT_KEYS)
        if mixed:
            raise HintFormatError(f"{where}: give either 'section' tables or {mixed}, not both")
        unknown = set(entry) - {"section"}
        if unknown:
            raise HintFormatError(f"{where}: unknown keys {sorted(unknown)}")
        return _parse_sections(where, level_id, entry["section"], expected)
    if expected:
        raise HintFormatError(f"{where}: has {expected} sections; give one "
                              f"[level.{level_id}.section.K] per section (K = 1-{expected})")
    return _parse_hint(where, level_id, entry)


def parse_hints(data):
    """Check parsed TOML data and return {level_id: LevelHint or SectionedHint}."""
    unknown = set(data) - {"level"}
    if unknown:
        raise HintFormatError(f"hints.toml: unknown top-level keys {sorted(unknown)}")
    levels = data.get("level", {})
    if not isinstance(levels, dict):
        raise HintFormatError("hints.toml: 'level' must be a table of [level.N] entries")
    return {hint.level_id: hint for hint in (_parse_level(k, v) for k, v in levels.items())}


def load_hints(path=HINTS_PATH):
    """Read and check a hints file; returns {level_id: LevelHint or SectionedHint}."""
    with open(path, "rb") as f:
        try:
            data = tomllib.load(f)
        except tomllib.TOMLDecodeError as exc:
            raise HintFormatError(f"{Path(path).name}: {exc}") from None
    return parse_hints(data)


@lru_cache(maxsize=1)
def _hints():
    return load_hints()


def get_hint(level_id, section=0):
    """The hint for section ``section`` (0-based) of ``level_id``, or None.

    One-screen levels only have section 0. None: no hint (random levels),
    or no such section.
    """
    hint = _hints().get(level_id)
    if hint is None:
        return None
    sections = hint_sections(hint)
    return sections[section] if 0 <= section < len(sections) else None
