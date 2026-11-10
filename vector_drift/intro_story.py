"""The intro story's panels, read from intro_story.toml (played by scenes/story.py).

Each panel names its picture (an image_assets key), describes the scene
(shown as placeholder text while the picture does not exist), and gives
one subtitle line said by a speaker ("SHIP") or by the narrator ("").
"""

import tomllib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

STORY_PATH = Path(__file__).resolve().parent / "intro_story.toml"
PANEL_KEYS = ("image", "scene", "speaker", "line")


class StoryFormatError(ValueError):
    """intro_story.toml is malformed; the message names the panel and the field."""


@dataclass(frozen=True)
class StoryPanel:
    image: str          # image_assets key, e.g. "story.panel1"
    scene: str          # what the picture shows (placeholder text)
    speaker: str        # "SHIP", or "" for the narrator
    line: str           # the subtitle


def _parse_panel(n, entry):
    where = f"intro_story.toml panel {n}"
    if not isinstance(entry, dict):
        raise StoryFormatError(f"{where}: must be a [[panel]] table")
    unknown = set(entry) - set(PANEL_KEYS)
    if unknown:
        raise StoryFormatError(f"{where}: unknown keys {sorted(unknown)}")
    for key in PANEL_KEYS:
        if key not in entry:
            raise StoryFormatError(f"{where}: missing '{key}'")
        if not isinstance(entry[key], str):
            raise StoryFormatError(f"{where}: '{key}' must be a string")
    for key in ("image", "scene", "line"):
        if not entry[key].strip():
            raise StoryFormatError(f"{where}: '{key}' is empty")
    return StoryPanel(**{key: entry[key] for key in PANEL_KEYS})


def parse_story(data):
    """Check parsed TOML data and return the panels in order."""
    unknown = set(data) - {"panel"}
    if unknown:
        raise StoryFormatError(f"intro_story.toml: unknown top-level keys {sorted(unknown)}")
    panels = data.get("panel")
    if not isinstance(panels, list) or not panels:
        raise StoryFormatError("intro_story.toml: needs at least one [[panel]]")
    return tuple(_parse_panel(n, entry) for n, entry in enumerate(panels, start=1))


def load_story(path=STORY_PATH):
    """Read and check a story file; returns a tuple of StoryPanel."""
    with open(path, "rb") as f:
        try:
            data = tomllib.load(f)
        except tomllib.TOMLDecodeError as exc:
            raise StoryFormatError(f"{Path(path).name}: {exc}") from None
    return parse_story(data)


@lru_cache(maxsize=1)
def story_panels():
    """The intro story (read once)."""
    return load_story()
