"""Static game data: ships and hand-designed levels.

Dynamic levels (e.g. 7, 8) are NOT hard-coded here: their tunables live in
level_presets.py and their layouts are generated fresh by random_level.py.
get_level() routes any id in level_presets.dynamic_ids() to the generator,
so gameplay always uses get_level() instead of reading LEVELS directly.
To add Level 9: register_preset(RandomPreset(level_id=9, ...)) -- no edits
to this file, config.py, or scenes are needed.
"""

from dataclasses import dataclass

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



# Ship skins: same physics, different look (assets/images/ships/<id>.png).
# The shown name is the id until the team picks real names. shipN unlocks
# on level N.
SHIPS = {
    f"ship{n:02d}": ShipSpec(id=f"ship{n:02d}", name=f"ship{n:02d}", mass=1.0, hull_radius=0.2,
                             unlock_level=n)
    for n in range(1, 7)
}


def ship_unlocked(ship, level_id):
    """True if ``ship`` may fly on ``level_id``.

    Fixed level N flies the ships with unlock_level <= N (ship01..shipN),
    by the level being played, not by saved progress. Random levels fly
    every ship.
    """
    return is_dynamic_level(level_id) or ship.unlock_level <= level_id


def default_ship_id(level_id):
    """The ship a level starts on: the newest one it may fly (shipN on level N)."""
    usable = [ship_id for ship_id, ship in SHIPS.items() if ship_unlocked(ship, level_id)]
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
        holes=(
            ((-3.0, 4.0), (2.0, 4.0), 0.5),
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


PortalSpec = HoleSpec
WormholeSpec = HoleSpec
BlackHoleSpec = HoleSpec
WhiteHoleSpec = HoleSpec


# test insert
