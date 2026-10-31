"""Story text, read from story.toml.

The opening crawl plays the first time Start is pressed. Each fixed level
names the planet its target is drawn as, plus the lines Poland says the
first time the level opens and the first time it is cleared. A random fail
line is said whenever a life is lost (but not the last one). Random levels
have no story.
"""

import random
import tomllib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

STORY_PATH = Path(__file__).resolve().parent / "story.toml"
PLANET_KINDS = ("moon", "mars", "saturn", "exoplanet")     # painters in sprites.PLANETS

# Keys in Session.story_seen
INTRO_SEEN = "intro"


def level_intro_key(level_id):
    return f"level.{level_id}.intro"


def level_win_key(level_id):
    return f"level.{level_id}.win"


class StoryFormatError(ValueError):
    """story.toml is malformed; the message names the section and the field."""


@dataclass(frozen=True)
class Intro:
    title: str
    subtitle: str
    paragraphs: tuple               # tuple[str, ...]


@dataclass(frozen=True)
class LevelStory:
    level_id: int
    planet: str
    intro: tuple                    # tuple[str, ...], one line per click
    win: tuple


@dataclass(frozen=True)
class Story:
    intro: Intro
    levels: dict                    # {level_id: LevelStory}
    fail_lines: tuple


def _text(value):
    return isinstance(value, str) and value.strip() != ""


def _lines(where, entry, key):
    value = entry.get(key)
    if not isinstance(value, list) or not value or not all(_text(s) for s in value):
        raise StoryFormatError(f"{where}: '{key}' must be a non-empty list of non-empty strings")
    return tuple(value)


def _check_keys(where, entry, allowed):
    if not isinstance(entry, dict):
        raise StoryFormatError(f"{where}: must be a table")
    unknown = set(entry) - set(allowed)
    if unknown:
        raise StoryFormatError(f"{where}: unknown keys {sorted(unknown)}")


def _parse_intro(entry):
    where = "story.toml [intro]"
    _check_keys(where, entry, ("title", "subtitle", "paragraphs"))
    for key in ("title", "subtitle"):
        if not _text(entry.get(key)):
            raise StoryFormatError(f"{where}: '{key}' must be a non-empty string")
    return Intro(entry["title"], entry["subtitle"], _lines(where, entry, "paragraphs"))


def _parse_level(key, entry):
    try:
        level_id = int(key)
    except ValueError:
        raise StoryFormatError(f"story.toml: level key '{key}' is not a level number") from None
    where = f"story.toml level {level_id}"
    _check_keys(where, entry, ("planet", "intro", "win"))
    planet = entry.get("planet")
    if planet not in PLANET_KINDS:
        raise StoryFormatError(f"{where}: 'planet' must be one of {list(PLANET_KINDS)}")
    return LevelStory(level_id, planet, _lines(where, entry, "intro"), _lines(where, entry, "win"))


def parse_story(data):
    """Check parsed TOML data and return a Story."""
    _check_keys("story.toml", data, ("intro", "level", "fail"))
    if "intro" not in data:
        raise StoryFormatError("story.toml: missing [intro]")
    levels = data.get("level", {})
    if not isinstance(levels, dict):
        raise StoryFormatError("story.toml: 'level' must be a table of [level.N] entries")
    fail = data.get("fail", {})
    _check_keys("story.toml [fail]", fail, ("lines",))
    return Story(
        intro=_parse_intro(data["intro"]),
        levels={s.level_id: s for s in (_parse_level(k, v) for k, v in levels.items())},
        fail_lines=_lines("story.toml [fail]", fail, "lines"),
    )


def load_story(path=STORY_PATH):
    """Read and check a story file; returns a Story."""
    with open(path, "rb") as f:
        try:
            data = tomllib.load(f)
        except tomllib.TOMLDecodeError as exc:
            raise StoryFormatError(f"{Path(path).name}: {exc}") from None
    return parse_story(data)


@lru_cache(maxsize=1)
def get_story():
    return load_story()


def get_level_story(level_id):
    """The story for ``level_id``, or None (random levels)."""
    return get_story().levels.get(level_id)


def planet_for(level_id):
    """The planet kind a level's target is drawn as, or None (default art)."""
    story = get_level_story(level_id)
    return story.planet if story else None


def all_seen_keys():
    """Every story_seen key: as if the crawl and all level lines were shown."""
    keys = {INTRO_SEEN}
    for level_id in get_story().levels:
        keys |= {level_intro_key(level_id), level_win_key(level_id)}
    return keys


def random_fail_line(rng=random):
    return rng.choice(get_story().fail_lines)
