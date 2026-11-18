"""Tutorial mode data, read from tutorial.toml.

The Basics walkthrough (scenes/tutorial_basics.py) and the element demos
(scenes/field_guide.py, in the tutorial screen's popup) take every text and
every map from here, so the
scenes hold no tutorial content of their own. Each map becomes an ordinary
LevelSpec and each force an ordinary ForceField: the tutorial flies the same
physics as the game.
"""

import tomllib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .data_models import HoleSpec, LevelSpec, ObstacleSpec, PickupSpec

TUTORIAL_PATH = Path(__file__).resolve().parent / "tutorial.toml"
TUTORIAL_LEVEL_ID = 0           # never a campaign, random or custom level id
TUTORIAL_SHIP_ID = "ship01"
# A map without a planet still needs a target for the physics: one far off
# that nothing can reach (the scenes do not draw it).
NO_TARGET = (1.0e6, 1.0e6)
STEP_KINDS = ("play", "demo", "card")
POINTS = ("", "ship", "start", "hint")
PICKUP_KINDS = ("shockwave", "extratime", "shield", "unbound")
ICONS = ("rock", "holes") + PICKUP_KINDS
MAP_KEYS = ("start", "target", "target_radius", "time_limit", "obstacles", "pickups", "holes")


class TutorialFormatError(ValueError):
    """tutorial.toml is malformed; the message says where."""


@dataclass(frozen=True)
class TutorialMap:
    start: tuple
    target: tuple | None
    target_radius: float = 1.0
    time_limit: float = 10.0
    obstacles: tuple = ()           # ObstacleSpec
    pickups: tuple = ()             # PickupSpec
    holes: tuple = ()               # HoleSpec

    @property
    def has_target(self):
        return self.target is not None

    def level(self, name="Tutorial"):
        """This map as an ordinary one-screen level."""
        return LevelSpec(id=TUTORIAL_LEVEL_ID, name=name, start=self.start,
                         target_center=self.target if self.has_target else NO_TARGET,
                         target_radius=self.target_radius if self.has_target else 0.01,
                         ship_id=TUTORIAL_SHIP_ID, time_limit=self.time_limit,
                         obstacles=self.obstacles, pickups=self.pickups, holes=self.holes)


@dataclass(frozen=True)
class Beat:
    launch: bool
    point: str
    text: str


@dataclass(frozen=True)
class BasicsStep:
    kind: str                       # "play" | "demo" | "card"
    title: str
    text: str
    map: TutorialMap
    placeholders: tuple = ()        # play: grey hints on the empty lines
    success: str = ""               # play: shown on arrival
    force: tuple = ()               # demo: ("Fx", "Fy"), read only
    beats: tuple = ()               # demo: Beat per caption
    point: str = ""                 # card: what the arrow marks
    button: str = ""                # card: its one button


@dataclass(frozen=True)
class GuidePart:
    text: str
    force: tuple                    # ("Fx", "Fy")
    cap: float                      # s: the clip stops here (or when the flight ends)
    map: TutorialMap
    show_timer: bool = False


@dataclass(frozen=True)
class GuideItem:
    name: str
    icon: str
    parts: tuple


@dataclass(frozen=True)
class GuideCategory:
    name: str
    items: tuple


@dataclass(frozen=True)
class Tutorial:
    basics: tuple                   # BasicsStep
    guide: tuple                    # GuideCategory


# --- checks -------------------------------------------------------------------
def _table(where, entry):
    if not isinstance(entry, dict):
        raise TutorialFormatError(f"{where}: must be a table")
    return entry


def _only(where, entry, allowed):
    unknown = set(entry) - set(allowed)
    if unknown:
        raise TutorialFormatError(f"{where}: unknown keys {sorted(unknown)}")


def _text(where, entry, key, required=True):
    value = entry.get(key, "")
    if not isinstance(value, str):
        raise TutorialFormatError(f"{where}: '{key}' must be a string")
    if required and not value.strip():
        raise TutorialFormatError(f"{where}: '{key}' is missing or empty")
    return value


def _number(where, entry, key, default=None, positive=True):
    value = entry.get(key, default)
    if value is None:
        raise TutorialFormatError(f"{where}: missing '{key}'")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TutorialFormatError(f"{where}: '{key}' must be a number")
    if positive and value <= 0:
        raise TutorialFormatError(f"{where}: '{key}' must be positive")
    return float(value)


def _point(where, value):
    if (not isinstance(value, list) or len(value) != 2
            or any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in value)):
        raise TutorialFormatError(f"{where}: must be [x, y]")
    return (float(value[0]), float(value[1]))


def _force(where, entry):
    value = entry.get("force")
    if not isinstance(value, list) or len(value) != 2 or not all(isinstance(v, str) for v in value):
        raise TutorialFormatError(f"{where}: 'force' must be [\"Fx\", \"Fy\"]")
    from .expr_parser import diagnose_expression
    for text in value:
        expr, err, _pos = diagnose_expression(text)
        if expr is None:
            raise TutorialFormatError(f"{where}: force {text!r}: {err}")
    return tuple(value)


def _list(where, entry, key):
    value = entry.get(key, [])
    if not isinstance(value, list):
        raise TutorialFormatError(f"{where}: '{key}' must be a list")
    return value


def _parse_map(where, entry):
    entry = _table(where, entry)
    obstacles = []
    for n, ob in enumerate(_list(where, entry, "obstacles"), start=1):
        at = f"{where} obstacle {n}"
        ob = _table(at, ob)
        _only(at, ob, ("center", "radius"))
        obstacles.append(ObstacleSpec(center=_point(f"{at} center", ob.get("center")),
                                      radius=_number(at, ob, "radius")))
    pickups = []
    for n, pk in enumerate(_list(where, entry, "pickups"), start=1):
        at = f"{where} pickup {n}"
        pk = _table(at, pk)
        _only(at, pk, ("center", "kind"))
        kind = pk.get("kind")
        if kind not in PICKUP_KINDS:
            raise TutorialFormatError(f"{at}: 'kind' must be one of {list(PICKUP_KINDS)}")
        pickups.append(PickupSpec(center=_point(f"{at} center", pk.get("center")), kind=kind))
    holes = []
    for n, hole in enumerate(_list(where, entry, "holes"), start=1):
        at = f"{where} hole {n}"
        hole = _table(at, hole)
        _only(at, hole, ("black", "white", "radius"))
        holes.append(HoleSpec.from_centers(_point(f"{at} black", hole.get("black")),
                                           _point(f"{at} white", hole.get("white")),
                                           _number(at, hole, "radius", 0.5)))
    target = entry.get("target")
    return TutorialMap(
        start=_point(f"{where} start", entry.get("start")),
        target=None if target is None else _point(f"{where} target", target),
        target_radius=_number(where, entry, "target_radius", 1.0),
        time_limit=_number(where, entry, "time_limit", 10.0),
        obstacles=tuple(obstacles), pickups=tuple(pickups), holes=tuple(holes))


def _parse_step(n, entry):
    where = f"tutorial.toml basics step {n}"
    entry = _table(where, entry)
    kind = entry.get("kind")
    if kind not in STEP_KINDS:
        raise TutorialFormatError(f"{where}: 'kind' must be one of {list(STEP_KINDS)}")
    common = ("kind", "title", "text", "map")
    extra = {"play": ("placeholders", "success"), "demo": ("force", "beat"),
             "card": ("point", "button")}[kind]
    _only(where, entry, common + extra)
    step = dict(kind=kind, title=_text(where, entry, "title"),
                text=_text(where, entry, "text", required=kind != "demo"),
                map=_parse_map(f"{where} map", entry.get("map")))
    if kind == "play":
        holders = entry.get("placeholders", [])
        if not isinstance(holders, list) or not all(isinstance(h, str) for h in holders):
            raise TutorialFormatError(f"{where}: 'placeholders' must be a list of strings")
        step.update(placeholders=tuple(holders), success=_text(where, entry, "success"))
    elif kind == "demo":
        beats = []
        for k, beat in enumerate(_list(where, entry, "beat"), start=1):
            at = f"{where} beat {k}"
            beat = _table(at, beat)
            _only(at, beat, ("launch", "point", "text"))
            if not isinstance(beat.get("launch"), bool):
                raise TutorialFormatError(f"{at}: 'launch' must be true or false")
            point = beat.get("point", "")
            if point not in POINTS:
                raise TutorialFormatError(f"{at}: 'point' must be one of {list(POINTS)}")
            beats.append(Beat(beat["launch"], point, _text(at, beat, "text")))
        if not beats:
            raise TutorialFormatError(f"{where}: needs at least one beat")
        step.update(force=_force(where, entry), beats=tuple(beats))
    else:
        point = entry.get("point", "")
        if point not in POINTS:
            raise TutorialFormatError(f"{where}: 'point' must be one of {list(POINTS)}")
        step.update(point=point, button=_text(where, entry, "button"))
    return BasicsStep(**step)


def _parse_part(where, entry):
    entry = _table(where, entry)
    _only(where, entry, ("text", "force", "cap", "show_timer") + MAP_KEYS)
    show_timer = entry.get("show_timer", False)
    if not isinstance(show_timer, bool):
        raise TutorialFormatError(f"{where}: 'show_timer' must be true or false")
    return GuidePart(text=_text(where, entry, "text"), force=_force(where, entry),
                     cap=_number(where, entry, "cap"),
                     map=_parse_map(where, {k: entry[k] for k in MAP_KEYS if k in entry}),
                     show_timer=show_timer)


def _parse_guide(data):
    categories = []
    for n, cat in enumerate(_list("tutorial.toml guide", data, "category"), start=1):
        where = f"tutorial.toml guide category {n}"
        cat = _table(where, cat)
        _only(where, cat, ("name", "item"))
        items = []
        for k, item in enumerate(_list(where, cat, "item"), start=1):
            at = f"{where} item {k}"
            item = _table(at, item)
            _only(at, item, ("name", "icon", "part"))
            if item.get("icon") not in ICONS:
                raise TutorialFormatError(f"{at}: 'icon' must be one of {list(ICONS)}")
            parts = tuple(_parse_part(f"{at} part {j}", part)
                          for j, part in enumerate(_list(at, item, "part"), start=1))
            if not parts:
                raise TutorialFormatError(f"{at}: needs at least one part")
            items.append(GuideItem(_text(at, item, "name"), item["icon"], parts))
        if not items:
            raise TutorialFormatError(f"{where}: needs at least one item")
        categories.append(GuideCategory(_text(where, cat, "name"), tuple(items)))
    if not categories:
        raise TutorialFormatError("tutorial.toml: needs at least one guide category")
    return tuple(categories)


def parse_tutorial(data):
    """Check parsed TOML data and return the Tutorial."""
    _only("tutorial.toml", data, ("basics", "guide"))
    basics = _table("tutorial.toml basics", data.get("basics", {}))
    _only("tutorial.toml basics", basics, ("step",))
    steps = tuple(_parse_step(n, s) for n, s in enumerate(_list("tutorial.toml basics", basics, "step"),
                                                           start=1))
    if not steps:
        raise TutorialFormatError("tutorial.toml: needs at least one basics step")
    guide = _table("tutorial.toml guide", data.get("guide", {}))
    _only("tutorial.toml guide", guide, ("category",))
    return Tutorial(basics=steps, guide=_parse_guide(guide))


def load_tutorial(path=TUTORIAL_PATH):
    with open(path, "rb") as f:
        try:
            data = tomllib.load(f)
        except tomllib.TOMLDecodeError as exc:
            raise TutorialFormatError(f"{Path(path).name}: {exc}") from None
    return parse_tutorial(data)


@lru_cache(maxsize=1)
def tutorial():
    """The tutorial (read once)."""
    return load_tutorial()


def force_field(force):
    """("Fx", "Fy") formulas as the game's ForceField."""
    from .expr_parser import diagnose_expression
    from .physics import ForceField
    fx, _, _ = diagnose_expression(force[0])
    fy, _, _ = diagnose_expression(force[1])
    return ForceField.from_exprs(fx, fy)
