"""Static game data: ships and hand-designed levels.

Dynamic levels (e.g. 7, 8) are NOT hard-coded here: their tunables live in
level_presets.py and their layouts are generated fresh by random_level.py.
get_level() routes any id in level_presets.dynamic_ids() to the generator,
so gameplay always uses get_level() instead of reading LEVELS directly.
To add another random level: register_preset(RandomPreset(level_id=N, ...))
with an id no fixed level uses (level 9 is fixed, see LEVELS) -- no edits to
this file, config.py, or scenes are needed.

Multi-section levels (level 9 on) are fixed levels made of SectionSpecs:
reaching a section's target (a checkpoint) pans the camera to the next
section; only the last target is the planet. See multi_section_level.
"""

from dataclasses import dataclass, replace

from .level_presets import dynamic_ids, get_preset, is_dynamic_level


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


def _owned_ship_ids(session=None):
    """Resolve the set of owned ship ids from a session (or the default)."""
    if session is not None:
        for attr in ("owned_ships", "unlocked_ships", "purchased_ships", "owned_ship_ids"):
            value = getattr(session, attr, None)
            if value is not None:
                try:
                    return set(value)
                except TypeError:
                    pass
        owned = {"ship01"}
        try:
            setattr(session, "owned_ships", owned)
        except Exception:
            pass
        return owned
    return {"ship01"}


def ship_unlocked(ship, level_id=None, session=None, owned=None):
    """True if ``ship`` is owned by the player (purchased).

    Ownership replaces the old level-based unlock: only ``ship01`` is owned
    from the start; every other skin must be bought in the shop.  ``level_id``
    is kept for backwards compatibility but no longer gates anything.
    """
    ship_id = getattr(ship, "id", ship)
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
    # Unbound intro: 15 rocks along x = 4.5 + y^2 / 12 wall the target in on
    # the right. Neighbours are at most ~1.64 m apart, under the 2 m
    # (2 x (0.8 + hull 0.2)) the ship needs, and both ends stick out past the
    # top-right and bottom-right corners, so the only way round is outside the
    # map: either Unbound (top or bottom, like level 3's two shockwaves).
    LevelSpec(
        id=6,
        name="First Unbound",
        start=(-7.0, 0.0),
        target_center=(7.5, 0.0),
        target_radius=1.0,
        ship_id="ship01",
        obstacles=(
            ObstacleSpec(center=(10.38, -8.4), radius=0.8),
            ObstacleSpec(center=(9.31, -7.6), radius=0.8),
            ObstacleSpec(center=(8.24, -6.7), radius=0.8),
            ObstacleSpec(center=(7.11, -5.6), radius=0.8),
            ObstacleSpec(center=(6.11, -4.4), radius=0.8),
            ObstacleSpec(center=(5.25, -3.0), radius=0.8),
            ObstacleSpec(center=(4.69, -1.5), radius=0.8),
            ObstacleSpec(center=(4.5, 0.0), radius=0.8),
            ObstacleSpec(center=(4.69, 1.5), radius=0.8),
            ObstacleSpec(center=(5.25, 3.0), radius=0.8),
            ObstacleSpec(center=(6.11, 4.4), radius=0.8),
            ObstacleSpec(center=(7.11, 5.6), radius=0.8),
            ObstacleSpec(center=(8.24, 6.7), radius=0.8),
            ObstacleSpec(center=(9.31, 7.6), radius=0.8),
            ObstacleSpec(center=(10.38, 8.4), radius=0.8),
        ),
        pickups=(
            PickupSpec(center=(-2.7, 6.3), radius=0.45, kind="unbound"),
            PickupSpec(center=(-2.7, -6.3), radius=0.45, kind="unbound"),
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


def get_level(level_id, seed=None):
    """Return the spec for ``level_id``.

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
