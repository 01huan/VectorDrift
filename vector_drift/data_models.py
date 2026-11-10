"""Core level and ship data models.

This module holds the immutable value objects only. Fixed level content lives
in :mod:`vector_drift.data_levels`; registry/routing lives in
:mod:`vector_drift.data`.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

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
    price: int = 0              # shop price (0 = not sold / free)


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
        from .data_serialization import _level_spec_to_row
        return _level_spec_to_row(self)

    @classmethod
    def from_row(cls, row):
        from .data_serialization import _level_spec_from_row
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


__all__ = [
    "ShipSpec", "ObstacleSpec", "PickupSpec", "LevelSpec", "SectionSpec",
    "HoleSpec", "SHIPS", "section_count", "section_level", "section_shift",
    "multi_section_level", "ship_unlocked", "default_ship_id", "level_holes",
]
