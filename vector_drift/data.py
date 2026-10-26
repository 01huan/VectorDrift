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
    kind: str = "bomb"


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


# Ship skins: same physics, different look (assets/images/ships/<id>.png).
# The shown name is the id until the team picks real names.
# levelN's style is the ship with unlock_level == N; it is unlocked only when
# that level is successfully cleared.
SHIPS = {
    f"ship{n:02d}": ShipSpec(id=f"ship{n:02d}", name=f"ship{n:02d}", mass=1.0, hull_radius=0.2,
                             unlock_level=n)
    for n in range(1, 7)
}

# Default style shown before any fixed level has been cleared.
DEFAULT_SHIP = ShipSpec(
    id="default",
    name="Default",
    mass=1.0,
    hull_radius=0.2,
    hull_color=(238, 242, 252),
    wing_color=(240, 100, 96),
    trim_color=(255, 196, 70),
    length=0.8,
    unlock_level=0,  # not used by the new unlock rule; kept for introspection
)


def ship_unlocked(ship, level_id, cleared_levels=None):
    """True if ``ship`` may fly on ``level_id``.

    cleared_levels: set of successfully completed fixed level ids.

    - Dynamic levels fly every ship.
    - The default style is always usable.
    - A fixed level's own style (shipN) is usable only if N is in
      ``cleared_levels``, i.e. it is unlocked by successfully completing
      that level, not by merely playing it.
    """
    if is_dynamic_level(level_id):
        return True

    if ship is DEFAULT_SHIP:
        return True

    if cleared_levels and ship.unlock_level in cleared_levels:
        return True

    return False


def default_ship_id(level_id, cleared_levels=None):
    """The ship a level starts on.

    No cleared fixed levels: the default style.
    Otherwise: the style of the highest cleared fixed level.
    """
    if not cleared_levels:
        return DEFAULT_SHIP.id

    newest = max(cleared_levels)
    return f"ship{newest:02d}"

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
        start=(-7.0, -2.0),
        target_center=(7.0, 2.0),
        target_radius=1.0,
        ship_id="ship01",
        obstacles=(
            ObstacleSpec(center=(0.0, 0.0), radius=1.2),
        ),
    ),
    LevelSpec(
        id=3,
        name="First Bounce",
        start=(-4.0, 0.0),
        target_center=(7.0, 2.0),
        target_radius=1.0,
        ship_id="ship02",
        obstacles=(
            ObstacleSpec(center=(0.0, 0.0), radius=3),ObstacleSpec(center=(0.0, 6.0), radius=3),ObstacleSpec(center=(0.0, -6.0), radius=3)
        ),
        pickups=(
            PickupSpec(center=(-7.0, 0.0), radius=0.45, kind="penetrate"),
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
