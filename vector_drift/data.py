"""Static game data: ships and hand-designed levels.

Dynamic levels (e.g. 8) are NOT hard-coded here: their tunables and
optional per-level templates live in level_presets.py; their layouts are
generated fresh by random_level.py.
get_level() routes any id in level_presets.dynamic_ids() to the generator,
so gameplay always uses get_level() instead of reading LEVELS directly.
To add another random level: register_preset(RandomPreset(level_id=N, ...))
with an id no fixed level uses (level 9 is fixed, see LEVELS) -- no edits to
this file, config.py, or scenes are needed.

Multi-section levels (level 9 on) are fixed levels made of SectionSpecs:
reaching a section's target (a checkpoint) pans the camera to the next
section; only the last target is the planet. See multi_section_level.
"""

import hashlib
import math
from dataclasses import dataclass, replace

from .level_presets import dynamic_ids, get_preset, is_dynamic_level
from .accessors import owned_ship_ids as _owned_ship_ids


@dataclass(frozen=True)
class ShipSpec:
    id: str
    name: str
    mass: float                 # kg
    hull_radius: float          # collision radius (m)
    hull_color: tuple = (238, 242, 252)
    wing_color: tuple = (240, 100, 96)
    trim_color: tuple = (255, 196, 70)
    length: float = 0.8         # drawn length (m); collision uses hull_radius
    unlock_level: int = 1       # first fixed level that may fly it (see ship_unlocked)
    price: int = 0                # shop price (0 = not sold / free)


@dataclass(frozen=True)
class ObstacleSpec:
    """Circular bumper. Ship bounces elastically on contact.

    center: (x, y) in m. radius: m (ship hull_radius is added at runtime).
    restitution: 1.0 = perfectly elastic; kept per-obstacle for future tuning.
    kind: selects the renderer in sprites.OBSTACLE_RENDERERS; "bumper" is
    the classic rock. New kinds only add a renderer (+ optional rule), they
    never touch physics or the placement loop.
    """

    center: tuple
    radius: float
    restitution: float = 1.0
    kind: str = "bumper"


@dataclass(frozen=True)
class PickupSpec:
    """Collectible prop. Ship triggers it on contact (segment test).

    Declared exactly like ObstacleSpec: fixed levels just set center +
    radius (+ optional kind), e.g.
    ``pickups=(PickupSpec(center=(0.0, 0.0), radius=0.45),)``.
    center: (x, y) in m. radius: m (ship hull_radius added at runtime).
    kind: selects the effect in pickups.EFFECTS + painter in
    sprites.PICKUP_RENDERERS. New pickups add a kind + effect + painter.
    Placement rule (fixed + random): must not overlap any obstacle,
    peer pickup, start pad, or target -- see pickups.discs_overlap.
    """

    center: tuple
    radius: float = 0.45
    kind: str = "shockwave"


@dataclass(frozen=True)
class LevelSpec:
    id: int
    name: str
    start: tuple                # (x, y) in m
    target_center: tuple        # (x, y) in m
    target_radius: float        # m
    ship_id: str
    time_limit: float = 10.0    # s of simulated flight per launch
    lives: int = 5
    obstacles: tuple = ()       # tuple[ObstacleSpec, ...]; empty = no bumpers
    pickups: tuple = ()         # tuple[PickupSpec, ...]; FIXED levels own this
                              # fully: no entry = no pickups (mutual no-stack)
    holes: tuple = ()           # tuple[HoleSpec, ...]; black/white hole pairs
    portals: tuple = ()
    wormholes: tuple = ()
    sections: tuple = ()        # tuple[SectionSpec, ...]; empty = one-screen level.
                              # Multi-section: the per-screen fields above are
                              # section 1's (see multi_section_level).


    def to_row(self) -> dict:
        return _level_spec_to_row(self)

    @classmethod
    def from_row(cls, row):
        return _level_spec_from_row(row)


@dataclass(frozen=True)
class SectionSpec:
    """One screen of a multi-section level, in that screen's own coordinates.

    Every section spans the usual [-10, 10] x [-7.5, 7.5] with the origin at
    its own center, so physics sees each one as an ordinary level (see
    section_level). The target of every section but the last is a checkpoint;
    the camera then pans so the next section's start sits where that
    checkpoint was (see section_shift).
    """

    start: tuple                # (x, y) in m, section coordinates
    target_center: tuple        # (x, y) in m; a checkpoint unless last section
    target_radius: float = 1.0  # m
    time_limit: float = 10.0    # s of simulated flight per launch
    obstacles: tuple = ()       # tuple[ObstacleSpec, ...]
    pickups: tuple = ()         # tuple[PickupSpec, ...]
    holes: tuple = ()           # tuple[HoleSpec, ...]


def section_count(level):
    """Number of screens in ``level``: 1 for an ordinary one-screen level."""
    return len(level.sections) or 1


def section_level(level, index):
    """Section ``index`` (0-based) of ``level`` as an ordinary one-screen LevelSpec.

    Same id, name, lives and ship; start, target, time limit and props come
    from the section, in its own coordinates, and ``sections`` is empty, so
    physics, hints, collisions and pickups treat it like any level. A
    one-screen level is its own section 0.
    """
    if not level.sections:
        if index != 0:
            raise IndexError(f"level {level.id} has one section, not {index + 1}")
        return level
    if not 0 <= index < len(level.sections):
        raise IndexError(f"level {level.id} has {len(level.sections)} sections, not {index + 1}")
    s = level.sections[index]
    return replace(level, start=tuple(s.start), target_center=tuple(s.target_center),
                   target_radius=s.target_radius, time_limit=s.time_limit,
                   obstacles=tuple(s.obstacles), pickups=tuple(s.pickups), holes=tuple(s.holes),
                   portals=(), wormholes=(), sections=())


def section_shift(level, index):
    """Camera pan (m) from section ``index`` to ``index + 1``.

    The checkpoint (section ``index``'s target) stays put on screen while the
    camera moves, so the pan is that target minus the next section's start,
    each in its own section's coordinates. It is also where section
    ``index + 1``'s origin sits in section ``index``'s coordinates.
    """
    if not 0 <= index < len(level.sections) - 1:
        raise IndexError(f"level {level.id} has no pan after section {index + 1}")
    here, there = level.sections[index], level.sections[index + 1]
    return (float(here.target_center[0] - there.start[0]),
            float(here.target_center[1] - there.start[1]))


def multi_section_level(id, name, ship_id, sections, lives=5):
    """A LevelSpec made of ``sections``; its own screen fields mirror section 1."""
    if len(sections) < 2:
        raise ValueError(f"level {id}: a multi-section level needs at least 2 sections")
    first = sections[0]
    return LevelSpec(id=id, name=name, start=tuple(first.start),
                     target_center=tuple(first.target_center),
                     target_radius=first.target_radius, ship_id=ship_id,
                     time_limit=first.time_limit, lives=lives,
                     obstacles=tuple(first.obstacles), pickups=tuple(first.pickups),
                     holes=tuple(first.holes), sections=tuple(sections))



# Ship skins: same physics, different look (assets/images/ships/<id>.png).
# The shown name is the id until the team picks real names. shipN unlocks
# on level N.
SHIPS = {
    f"ship{n:02d}": ShipSpec(id=f"ship{n:02d}", name=f"ship{n:02d}", mass=1.0, hull_radius=0.2,
                             unlock_level=n)
    for n in range(1, 7)
}






def ship_unlocked(ship, level_id=None, session=None, owned=None):
    """True if ``ship`` is owned by the player (purchased).

    Ownership replaces the old level-based unlock: only ``ship01`` is owned
    from the start; every other skin must be bought in the shop.  ``level_id``
    is kept for backwards compatibility but no longer gates anything.
    """
    ship_id = _ship_id(ship)
    if isinstance(ship_id, (list, tuple, set)):
        ship_id = list(ship_id)[0] if ship_id else None
    if owned is not None:
        try:
            return ship_id in set(owned)
        except TypeError:
            return ship_id == owned
    if session is not None:
        return ship_id in _owned_ship_ids(session)
    return ship_id in _owned_ship_ids(None)


def default_ship_id(level_id=None, session=None):
    """The ship a level starts on: the first owned ship (ship01 by default)."""
    owned = _owned_ship_ids(session)
    usable = [sid for sid in SHIPS if sid in owned]
    return usable[-1] if usable else next(iter(SHIPS))

LEVELS = [
    LevelSpec(
        id=1,
        name="First Drift",
        start=(-7.0, 0.0),
        target_center=(7.0, 0.0),
        target_radius=1.0,
        ship_id="ship01",
    ),
    LevelSpec(
        id=2,
        name="First Bounce",
        start=(-7.0, 0.0),
        target_center=(7.0, 0.0),
        target_radius=1.0,
        ship_id="ship01",
        obstacles=(
            ObstacleSpec(center=(0.0, 0.0), radius=1.2),
        ),
        pickups=(PickupSpec(center=(0.0, 3.0), radius=0.45, kind="money"),),
    ),
    # Shockwave intro: a ring of 9 bumpers (r 2.6 m around the target, every
    # 40 deg from 180 deg) seals the target until one shockwave blasts a gap.
    # Reference solutions: Fx = 3, Fy = -x - 2y (top shockwave) or
    # Fy = x - 2y (bottom, mirrored).
    LevelSpec(
        id=3,
        name="First Blast",
        start=(-7.0, 0.0),
        target_center=(6.5, 0.0),
        target_radius=1.0,
        ship_id="ship01",
        # Intentional: neighbouring bumpers are ~0.18 m apart, less than the
        # ship's 0.4 m width, so their collision discs overlap and seal the ring.
        obstacles=(
            ObstacleSpec(center=(3.9, 0.0), radius=0.8),
            ObstacleSpec(center=(4.51, -1.67), radius=0.8),
            ObstacleSpec(center=(6.05, -2.56), radius=0.8),
            ObstacleSpec(center=(7.8, -2.25), radius=0.8),
            ObstacleSpec(center=(8.94, -0.89), radius=0.8),
            ObstacleSpec(center=(8.94, 0.89), radius=0.8),
            ObstacleSpec(center=(7.8, 2.25), radius=0.8),
            ObstacleSpec(center=(6.05, 2.56), radius=0.8),
            ObstacleSpec(center=(4.51, 1.67), radius=0.8),
        ),
        pickups=(
            PickupSpec(center=(3.2, 3.6), radius=0.45, kind="shockwave"),
            PickupSpec(center=(3.2, -3.6), radius=0.45, kind="shockwave"),
        ),
    ),
    LevelSpec(
        id=4,
        name="First Wormhole",
        start=(-7.0, 0.0),
        target_center=(7.0, 0.0),
        target_radius=1.0,
        ship_id="ship01",
        # Full-height wall of rocks at x = 0: both ends stick out past the world
        # bounds (±7.5 m), so there is no way around it, only through the
        # wormhole. Centers are 1.6 m apart with radius 0.8 m each, so neighbours
        # touch exactly (the top two overlap) and leave no gap at all. Tighter
        # than level 3's ring (about 1.78 m apart). The rock art is drawn a bit
        # inside the radius, so thin slits show on screen, but none is passable.
        obstacles=(
            ObstacleSpec(center=(0.0, -7.0), radius=0.8),
            ObstacleSpec(center=(0.0, -5.4), radius=0.8),
            ObstacleSpec(center=(0.0, -3.8), radius=0.8),
            ObstacleSpec(center=(0.0, -2.2), radius=0.8),
            ObstacleSpec(center=(0.0, -0.6), radius=0.8),
            ObstacleSpec(center=(0.0, 1.0), radius=0.8),
            ObstacleSpec(center=(0.0, 2.6), radius=0.8),
            ObstacleSpec(center=(0.0, 4.2), radius=0.8),
            ObstacleSpec(center=(0.0, 5.8), radius=0.8),
            ObstacleSpec(center=(0.0, 7.0), radius=0.8),
        ),
        # Black hole top-left of the wall, white hole top-right, NOT placed on
        # the target and NOT point-symmetric with (start, target): the ship has
        # to steer into the black hole, then curve down into the target after
        # exiting, not just fly a single straight/constant-force line through
        # both legs.
        pickups=(PickupSpec(center=(-4.0, 4.0), radius=0.45, kind="money"),),
        holes=(
            ((-3.0, 4.0), (2.0, 4.0), 0.5),
        ),
    ),
    LevelSpec(
        id=5,
        name="First Extratime",
        start=(-8.0, 0.0),
        target_center=(8.0, 0.0),
        target_radius=1.0,
        ship_id="ship01",
        time_limit=9.0,   # tighter than the 10 s default
        # Two sealed rows of rocks (y = +-4.8, r = 0.8, gaps ~0.1 m, narrower
        # than the ship) block level 2's tall round swirl. The reference answer
        # F = (-2y, x + 6.7) is that swirl flattened by a/b = 2 (height x
        # 1/sqrt(2)) and passes between the rows (mirror: F = (2y, -x - 6.7)).
        # The Extratime pickup is optional; the reference answers don't use it.
        obstacles=(
            ObstacleSpec(center=(-2.5, 0.8), radius=1.0),
            ObstacleSpec(center=(2.5, -0.8), radius=1.0),
            ObstacleSpec(center=(-6.0, 4.8), radius=0.8),
            ObstacleSpec(center=(-4.3, 4.8), radius=0.8),
            ObstacleSpec(center=(-2.6, 4.8), radius=0.8),
            ObstacleSpec(center=(-0.9, 4.8), radius=0.8),
            ObstacleSpec(center=(0.8, 4.8), radius=0.8),
            ObstacleSpec(center=(2.5, 4.8), radius=0.8),
            ObstacleSpec(center=(4.2, 4.8), radius=0.8),
            ObstacleSpec(center=(-6.0, -4.8), radius=0.8),
            ObstacleSpec(center=(-4.3, -4.8), radius=0.8),
            ObstacleSpec(center=(-2.6, -4.8), radius=0.8),
            ObstacleSpec(center=(-0.9, -4.8), radius=0.8),
            ObstacleSpec(center=(0.8, -4.8), radius=0.8),
            ObstacleSpec(center=(2.5, -4.8), radius=0.8),
            ObstacleSpec(center=(4.2, -4.8), radius=0.8),
        ),
        pickups=(
            PickupSpec(center=(-4.2, 0.4), radius=0.45, kind="extratime"),
        ),
    ),
    # Unbound intro: 11 rocks in an arc across the middle of the map, bulging
    # left (x = -1 at y = 0) and curving right toward the top and bottom
    # edges, where the outermost rocks sit on y = +-7.5. Neighbours are about
    # 1.50-1.65 m apart, under the 2 m (2 x (0.8 + hull 0.2)) the ship needs,
    # so the only way to the target is one arch over (or under) the wall,
    # outside the map: either Unbound (top or bottom) makes that legal.
    LevelSpec(
        id=6,
        name="First Unbound",
        start=(-7.0, 0.0),
        target_center=(7.0, 0.0),
        target_radius=1.0,
        ship_id="ship01",
        obstacles=(
            ObstacleSpec(center=(0.875, -7.5), radius=0.8),
            ObstacleSpec(center=(0.2, -6.0), radius=0.8),
            ObstacleSpec(center=(-0.325, -4.5), radius=0.8),
            ObstacleSpec(center=(-0.7, -3.0), radius=0.8),
            ObstacleSpec(center=(-0.925, -1.5), radius=0.8),
            ObstacleSpec(center=(-1.0, 0.0), radius=0.8),
            ObstacleSpec(center=(-0.925, 1.5), radius=0.8),
            ObstacleSpec(center=(-0.7, 3.0), radius=0.8),
            ObstacleSpec(center=(-0.325, 4.5), radius=0.8),
            ObstacleSpec(center=(0.2, 6.0), radius=0.8),
            ObstacleSpec(center=(0.875, 7.5), radius=0.8),
        ),
        pickups=(
            PickupSpec(center=(-5.1, 5.6), radius=0.45, kind="unbound"),
            PickupSpec(center=(-5.1, -5.6), radius=0.45, kind="unbound"),
        ),
    ),
    # Checkpoint intro: two level-1 screens side by side. In world terms the
    # ship goes x = -7 -> 7 (checkpoint) -> 21 (planet); the pan is (14, 0) and
    # the screens share x in [4, 10] of section 1 (= [-10, -4] of section 2),
    # which must stay empty apart from the checkpoint (tests/test_level9.py).
    multi_section_level(
        id=9,
        name="New Horizon",
        ship_id="ship01",
        sections=(
            SectionSpec(start=(-7.0, 0.0), target_center=(7.0, 0.0), target_radius=1.0),
            SectionSpec(start=(-7.0, 0.0), target_center=(7.0, 0.0), target_radius=1.0),
        ),
    ),
]


def _placeholder(preset):
    """Level-select card for a dynamic level (real layout via get_level)."""
    return LevelSpec(
        id=preset.level_id, name=preset.name, start=(0.0, 0.0),
        target_center=(0.0, 0.0), target_radius=preset.target_radius,
        ship_id=preset.ship_id,
    )


def all_levels():
    """Static levels + one placeholder per registered dynamic preset."""
    seen = {lv.id for lv in LEVELS}
    cards = list(LEVELS)
    for lid in dynamic_ids():
        if lid not in seen:
            cards.append(_placeholder(get_preset(lid)))
    return cards


# Custom (player-created) levels registry.
CUSTOM_LEVELS: dict[int, "LevelSpec"] = {}

# Community levels come from a public, untrusted table.  Their local ids are
# generated here from the remote row UUID and live in a dedicated negative
# namespace, so they can never collide with a built-in level (positive id) or
# an editor-created level (>= 1000).  The uploader-supplied ``level_data.id``
# is never used as a global id.
COMMUNITY_ID_SPACE = 1 << 30
_COMMUNITY_IDS_BY_REMOTE: dict[str, int] = {}
COMMUNITY_REMOTE_IDS: dict[int, str] = {}


def community_level_id(remote_id) -> int:
    """Local id for a community row, stable for the same remote UUID.

    The id is generated locally (negative namespace); the remote UUID is kept
    as the identity so the uploader cannot pick a colliding global id.
    """
    key = "" if remote_id is None else str(remote_id)
    if not key:
        # No remote id to key on (should not happen with Supabase rows):
        # hand out a fresh unique id instead of reusing one.
        candidate = -1
        while candidate in CUSTOM_LEVELS or candidate in COMMUNITY_REMOTE_IDS:
            candidate -= 1
            if candidate <= -COMMUNITY_ID_SPACE:
                raise RuntimeError("community level id space exhausted")
        COMMUNITY_REMOTE_IDS[candidate] = ""
        return candidate
    cached = _COMMUNITY_IDS_BY_REMOTE.get(key)
    if cached is not None:
        return cached
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    candidate = -1 - (int.from_bytes(digest[:7], "big") % COMMUNITY_ID_SPACE)
    while candidate in CUSTOM_LEVELS or candidate in COMMUNITY_REMOTE_IDS:
        candidate -= 1
        if candidate <= -COMMUNITY_ID_SPACE:
            raise RuntimeError("community level id space exhausted")
    _COMMUNITY_IDS_BY_REMOTE[key] = candidate
    COMMUNITY_REMOTE_IDS[candidate] = key
    return candidate


def community_remote_id(level_id):
    """Remote row UUID behind a locally generated community level id."""
    return COMMUNITY_REMOTE_IDS.get(level_id)


def register_custom_level(spec):
    """Register a custom level in ``CUSTOM_LEVELS``.

    Built-in levels are immutable: a custom id may never replace one, so a
    colliding id is rejected instead of overwriting ``LEVELS``.  Community
    levels use negative ids and the editor uses ids >= 1000, so normal callers
    never hit this.
    """
    if any(level.id == spec.id for level in LEVELS):
        raise ValueError(f"custom level id {spec.id} collides with a built-in level")
    CUSTOM_LEVELS[spec.id] = spec
    return spec


def is_custom_level(level_id):
    return level_id in CUSTOM_LEVELS


def custom_level_to_snapshot(level):
    """Return a JSON-compatible copy of the editable custom-level state."""
    return _level_spec_to_snapshot(level)


def custom_level_from_snapshot(snapshot):
    """Rebuild a custom level from a replay's saved level state."""
    return _level_spec_from_snapshot(snapshot)


def get_level(level_id, seed=None):
    """Return the spec for ``level_id``.

    Built-in and dynamic levels always win over custom ones: a custom id can
    never shadow them (community ids are negative, editor ids >= 1000).

    Dynamic ids (see level_presets.dynamic_ids()) generate a fresh solvable
    layout on every call unless ``seed`` is given (same seed -> same layout,
    used to keep retry/replay on one layout while level-select entries get
    new ones).
    """
    if is_dynamic_level(level_id):
        # Dynamic level: fresh solvable layout on every call (lazy import
        # avoids a data <-> random_level import cycle).
        from .random_level import generate_random_level
        return generate_random_level(level_id, seed=seed)
    for level in LEVELS:
        if level.id == level_id:
            return level
    if level_id in CUSTOM_LEVELS:
        return CUSTOM_LEVELS[level_id]
    raise KeyError(f"Unknown level {level_id}")

# Black/white hole (wormhole) spec.
@dataclass(frozen=True)
class HoleSpec:
    black_center: tuple = (0.0, 0.0)
    white_center: tuple = (0.0, 0.0)
    radius: float = 0.5

    def __init__(self, *args, **kwargs):
        bc = kwargs.pop("black_center", None)
        wc = kwargs.pop("white_center", None)
        if bc is None:
            for key in ("black", "entry", "in_center", "start", "center"):
                if key in kwargs:
                    bc = kwargs.pop(key)
                    break
        if wc is None:
            for key in ("white", "exit", "out_center", "target", "end"):
                if key in kwargs:
                    wc = kwargs.pop(key)
                    break
        if bc is None and args:
            bc = args[0]; args = args[1:]
        if wc is None and args:
            wc = args[0]; args = args[1:]
        radius = kwargs.pop("radius", 0.5)
        if args:
            radius = args[0]
        object.__setattr__(self, "black_center", (float(bc[0]), float(bc[1])))
        object.__setattr__(self, "white_center", (float(wc[0]), float(wc[1])))
        object.__setattr__(self, "radius", float(radius))

    @classmethod
    def from_centers(cls, black_center, white_center, radius=0.5):
        return cls(black_center=black_center, white_center=white_center, radius=radius)


def _list_or_empty(value):
    return value or ()


def _obstacles_to_rows(obstacles):
    return [
        {"center": list(item.center), "radius": float(item.radius),
         "restitution": float(item.restitution), "kind": str(item.kind)}
        for item in _list_or_empty(obstacles)
    ]


def _obstacle_from_row(item):
    return ObstacleSpec(
        center=tuple(item["center"]),
        radius=float(item["radius"]),
        restitution=float(item.get("restitution", 1.0)),
        kind=str(item.get("kind", "bumper")),
    )


def _obstacles_from_rows(rows):
    return tuple(_obstacle_from_row(item) for item in _list_or_empty(rows))


def _pickups_to_rows(pickups):
    return [
        {"center": list(item.center), "radius": float(item.radius), "kind": str(item.kind)}
        for item in _list_or_empty(pickups)
    ]


def _pickup_from_row(item):
    return PickupSpec(
        center=tuple(item["center"]),
        radius=float(item.get("radius", 0.45)),
        kind=str(item.get("kind", "shockwave")),
    )


def _pickups_from_rows(rows):
    return tuple(_pickup_from_row(item) for item in _list_or_empty(rows))


def _holes_to_rows(holes):
    return [
        {"black_center": list(item.black_center), "white_center": list(item.white_center),
         "radius": float(item.radius)}
        for item in _list_or_empty(holes)
    ]


def _hole_from_row(item):
    return HoleSpec(
        black_center=tuple(item.get("black_center", item.get("black", (0.0, 0.0)))),
        white_center=tuple(item.get("white_center", item.get("white", (0.0, 0.0)))),
        radius=float(item.get("radius", 0.5)),
    )


def _holes_from_rows(rows):
    return tuple(_hole_from_row(item) for item in _list_or_empty(rows))


def _level_spec_to_row(level):
    return {
        "id": int(level.id),
        "name": level.name,
        "start": list(level.start),
        "target_center": list(level.target_center),
        "target_radius": float(level.target_radius),
        "ship_id": level.ship_id,
        "time_limit": float(level.time_limit),
        "lives": int(level.lives),
        "obstacles": _obstacles_to_rows(level.obstacles),
        "pickups": _pickups_to_rows(level.pickups),
        "holes": _holes_to_rows(getattr(level, "holes", ()) or ()),
    }


def _level_spec_from_row(row):
    if not isinstance(row, dict):
        return None
    try:
        return LevelSpec(
            id=int(row["id"]),
            name=str(row["name"]),
            start=tuple(row["start"]),
            target_center=tuple(row["target_center"]),
            target_radius=float(row["target_radius"]),
            ship_id=str(row.get("ship_id", "ship01")),
            time_limit=float(row.get("time_limit", 10.0)),
            lives=int(row.get("lives", 5)),
            obstacles=_obstacles_from_rows(row.get("obstacles", ()) or ()),
            pickups=_pickups_from_rows(row.get("pickups", ()) or ()),
            holes=_holes_from_rows(row.get("holes", ()) or ()),
        )
    except (KeyError, TypeError, ValueError, OverflowError, AttributeError):

        return None

def _level_spec_to_snapshot(level):
    return {
        "id": int(level.id),
        "name": str(level.name),
        "start": list(level.start),
        "target_center": list(level.target_center),
        "target_radius": float(level.target_radius),
        "ship_id": str(level.ship_id),
        "time_limit": float(level.time_limit),
        "lives": int(level.lives),
        "obstacles": _obstacles_to_rows(level.obstacles),
        "pickups": _pickups_to_rows(level.pickups),
        "holes": _holes_to_rows(getattr(level, "holes", ()) or ()),
    }


def _level_spec_from_snapshot(snapshot):
    if not isinstance(snapshot, dict):
        raise ValueError("Custom level snapshot must be an object")
    obstacles = _obstacles_from_rows(snapshot.get("obstacles", ()))
    pickups = _pickups_from_rows(snapshot.get("pickups", ()))
    holes = _holes_from_rows(snapshot.get("holes", ()))
    return LevelSpec(
        id=int(snapshot["id"]),
        name=str(snapshot["name"]),
        start=tuple(snapshot["start"]),
        target_center=tuple(snapshot["target_center"]),
        target_radius=float(snapshot["target_radius"]),
        ship_id=str(snapshot.get("ship_id", "ship01")),
        time_limit=float(snapshot.get("time_limit", 10.0)),
        lives=int(snapshot.get("lives", 5)),
        obstacles=obstacles,
        pickups=pickups,
        holes=holes,
    )


# --- Validation for untrusted (community) level data ----------------------
#
# Community ``level_data`` is public and can be written by anybody, so it is
# validated before it becomes a LevelSpec.  The bounds are deliberately
# generous: they reject garbage (negative/huge values, NaN/inf, absurd object
# counts) without limiting ordinary designs.

PUBLIC_LEVEL_MAX_NAME_LEN = 80
PUBLIC_LEVEL_MAX_COORD = 100.0       # |x| / |y| in m
PUBLIC_LEVEL_MIN_RADIUS = 0.01       # m
PUBLIC_LEVEL_MAX_RADIUS = 5.0        # m
PUBLIC_LEVEL_MIN_TIME_LIMIT = 0.1    # s
PUBLIC_LEVEL_MAX_TIME_LIMIT = 120.0  # s
PUBLIC_LEVEL_MIN_LIVES = 1
PUBLIC_LEVEL_MAX_LIVES = 99
PUBLIC_LEVEL_MAX_OBSTACLES = 200
PUBLIC_LEVEL_MAX_PICKUPS = 100
PUBLIC_LEVEL_MAX_HOLES = 50
PUBLIC_LEVEL_MAX_RESTITUTION = 1.0


def _public_number(value, field):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a number")
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{field} must be a finite number")
    return value


def _public_int(value, field):
    if isinstance(value, bool):
        raise ValueError(f"{field} must be an integer")
    if isinstance(value, float):
        if not math.isfinite(value) or not value.is_integer():
            raise ValueError(f"{field} must be an integer")
        value = int(value)
    if not isinstance(value, int):
        raise ValueError(f"{field} must be an integer")
    return value


def _public_point(value, field):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(f"{field} must be a list of two numbers")
    x = _public_number(value[0], f"{field}[0]")
    y = _public_number(value[1], f"{field}[1]")
    if abs(x) > PUBLIC_LEVEL_MAX_COORD or abs(y) > PUBLIC_LEVEL_MAX_COORD:
        raise ValueError(f"{field} must stay within +/-{PUBLIC_LEVEL_MAX_COORD:g} m")
    return (x, y)


def _public_radius(value, field):
    radius = _public_number(value, field)
    if not PUBLIC_LEVEL_MIN_RADIUS <= radius <= PUBLIC_LEVEL_MAX_RADIUS:
        raise ValueError(
            f"{field} must be between {PUBLIC_LEVEL_MIN_RADIUS:g} and "
            f"{PUBLIC_LEVEL_MAX_RADIUS:g} m"
        )
    return radius


def _public_name(value):
    if value is None:
        return "Community"
    if not isinstance(value, str):
        raise ValueError("name must be a string")
    name = value.strip()
    if not name:
        return "Community"
    if len(name) > PUBLIC_LEVEL_MAX_NAME_LEN:
        raise ValueError(f"name must be at most {PUBLIC_LEVEL_MAX_NAME_LEN} characters")
    return name


def _supported_obstacle_kinds():
    # Lazy import: data.py loads before pygame/scenes, and sprites does not
    # depend on data, so importing it at call time is safe.
    from .sprites import OBSTACLE_RENDERERS
    return frozenset(OBSTACLE_RENDERERS)


def _supported_pickup_kinds():
    from .sprites import PICKUP_RENDERERS
    return frozenset(PICKUP_RENDERERS)


def _public_obstacle(item, index):
    field = f"obstacles[{index}]"
    if not isinstance(item, dict):
        raise ValueError(f"{field} must be an object")
    if "center" not in item:
        raise ValueError(f"{field}.center is required")
    if "radius" not in item:
        raise ValueError(f"{field}.radius is required")
    center = _public_point(item["center"], f"{field}.center")
    radius = _public_radius(item["radius"], f"{field}.radius")
    restitution = _public_number(item.get("restitution", 1.0), f"{field}.restitution")
    if not 0.0 <= restitution <= PUBLIC_LEVEL_MAX_RESTITUTION:
        raise ValueError(f"{field}.restitution must be between 0 and 1")
    kind = item.get("kind", "bumper")
    if not isinstance(kind, str) or kind not in _supported_obstacle_kinds():
        raise ValueError(f"{field}.kind is not supported")
    return ObstacleSpec(center=center, radius=radius, restitution=restitution, kind=kind)


def _public_pickup(item, index):
    field = f"pickups[{index}]"
    if not isinstance(item, dict):
        raise ValueError(f"{field} must be an object")
    if "center" not in item:
        raise ValueError(f"{field}.center is required")
    center = _public_point(item["center"], f"{field}.center")
    radius = _public_radius(item.get("radius", 0.45), f"{field}.radius")
    kind = item.get("kind", "shockwave")
    if not isinstance(kind, str) or kind not in _supported_pickup_kinds():
        raise ValueError(f"{field}.kind is not supported")
    return PickupSpec(center=center, radius=radius, kind=kind)


def _public_hole(item, index):
    field = f"holes[{index}]"
    if not isinstance(item, dict):
        raise ValueError(f"{field} must be an object")
    black = item.get("black_center", item.get("black"))
    white = item.get("white_center", item.get("white"))
    if black is None:
        raise ValueError(f"{field}.black_center is required")
    if white is None:
        raise ValueError(f"{field}.white_center is required")
    black_center = _public_point(black, f"{field}.black_center")
    white_center = _public_point(white, f"{field}.white_center")
    radius = _public_radius(item.get("radius", 0.5), f"{field}.radius")
    return HoleSpec(black_center=black_center, white_center=white_center, radius=radius)


def level_spec_from_public(raw, level_id):
    """Validate untrusted community ``level_data`` and build a ``LevelSpec``.

    ``level_id`` is the locally generated id assigned by the caller; the
    uploader-supplied ``raw["id"]`` is ignored on purpose.  Raises
    ``ValueError`` when the data is missing required fields or contains
    unsupported / non-finite / out-of-range values.
    """
    if isinstance(level_id, bool) or not isinstance(level_id, int):
        raise ValueError("level_id must be an integer")
    if not isinstance(raw, dict):
        raise ValueError("level data must be an object")
    for required in ("start", "target_center", "target_radius"):
        if required not in raw:
            raise ValueError(f"{required} is required")
    start = _public_point(raw["start"], "start")
    target_center = _public_point(raw["target_center"], "target_center")
    target_radius = _public_radius(raw["target_radius"], "target_radius")
    name = _public_name(raw.get("name"))
    ship_id = raw.get("ship_id", "ship01")
    if not isinstance(ship_id, str) or ship_id not in SHIPS:
        raise ValueError("ship_id is not supported")
    time_limit = _public_number(raw.get("time_limit", 10.0), "time_limit")
    if not PUBLIC_LEVEL_MIN_TIME_LIMIT <= time_limit <= PUBLIC_LEVEL_MAX_TIME_LIMIT:
        raise ValueError(
            f"time_limit must be between {PUBLIC_LEVEL_MIN_TIME_LIMIT:g} and "
            f"{PUBLIC_LEVEL_MAX_TIME_LIMIT:g} s"
        )
    lives = _public_int(raw.get("lives", 5), "lives")
    if not PUBLIC_LEVEL_MIN_LIVES <= lives <= PUBLIC_LEVEL_MAX_LIVES:
        raise ValueError(
            f"lives must be between {PUBLIC_LEVEL_MIN_LIVES} and {PUBLIC_LEVEL_MAX_LIVES}"
        )

    obstacles_raw = raw.get("obstacles", ())
    if not isinstance(obstacles_raw, (list, tuple)):
        raise ValueError("obstacles must be a list")
    if len(obstacles_raw) > PUBLIC_LEVEL_MAX_OBSTACLES:
        raise ValueError(f"obstacles must contain at most {PUBLIC_LEVEL_MAX_OBSTACLES} entries")
    obstacles = tuple(_public_obstacle(item, i) for i, item in enumerate(obstacles_raw))

    pickups_raw = raw.get("pickups", ())
    if not isinstance(pickups_raw, (list, tuple)):
        raise ValueError("pickups must be a list")
    if len(pickups_raw) > PUBLIC_LEVEL_MAX_PICKUPS:
        raise ValueError(f"pickups must contain at most {PUBLIC_LEVEL_MAX_PICKUPS} entries")
    pickups = tuple(_public_pickup(item, i) for i, item in enumerate(pickups_raw))

    holes_raw = raw.get("holes", ())
    if not isinstance(holes_raw, (list, tuple)):
        raise ValueError("holes must be a list")
    if len(holes_raw) > PUBLIC_LEVEL_MAX_HOLES:
        raise ValueError(f"holes must contain at most {PUBLIC_LEVEL_MAX_HOLES} entries")
    holes = tuple(_public_hole(item, i) for i, item in enumerate(holes_raw))

    return LevelSpec(
        id=level_id,
        name=name,
        start=start,
        target_center=target_center,
        target_radius=target_radius,
        ship_id=ship_id,
        time_limit=time_limit,
        lives=lives,
        obstacles=obstacles,
        pickups=pickups,
        holes=holes,
    )


def _ship_id(ship):
    return getattr(ship, "id", ship)


def level_holes(level):
    """Return a canonical HoleSpec tuple from holes/portals/wormholes aliases."""
    if level is None:
        return ()
    holes = getattr(level, "holes", ()) or ()
    if holes:
        return tuple(holes)
    for alias in ("portals", "wormholes"):
        value = getattr(level, alias, ()) or ()
        if value:
            return tuple(value)
    return ()

