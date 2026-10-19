"""Static game data: ships and hand-designed levels.

Level 7 ("Random Drift") is dynamic: see random_level.py. get_level(7)
generates a fresh solvable layout on every call, so gameplay always uses
get_level() instead of reading LEVELS directly.
"""

from dataclasses import dataclass

from . import config


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


@dataclass(frozen=True)
class ObstacleSpec:
    """Circular bumper. Ship bounces elastically on contact.

    center: (x, y) in m. radius: m (ship hull_radius is added at runtime).
    restitution: 1.0 = perfectly elastic; kept per-obstacle for future tuning.
    """

    center: tuple
    radius: float
    restitution: float = 1.0


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


SHIPS = {
    "drifter": ShipSpec(
        id="drifter",
        name="Drifter Mk I",
        mass=1.0,
        hull_radius=0.2,
    ),
}

LEVELS = [
    LevelSpec(
        id=1,
        name="First Drift",
        start=(-7.0, 0.0),
        target_center=(7.0, 0.0),
        target_radius=1.0,
        ship_id="drifter",
    ),
    LevelSpec(
        id=2,
        name="First Bounce",
        start=(-7.0, -2.0),
        target_center=(7.0, 2.0),
        target_radius=1.0,
        ship_id="drifter",
        obstacles=(
            ObstacleSpec(center=(0.0, 0.0), radius=1.2),
        ),
    ),
    LevelSpec(
        id=config.RANDOM_LEVEL_ID,
        name=config.RANDOM_LEVEL_NAME,
        # Placeholder so the level-select card shows up; the real layout
        # is generated fresh by get_level() (see random_level.py).
        start=(0.0, 0.0),
        target_center=(0.0, 0.0),
        target_radius=config.RANDOM_LEVEL_TARGET_RADIUS,
        ship_id=config.RANDOM_LEVEL_SHIP_ID,
    ),
]


def get_level(level_id, seed=None):
    """Return the spec for ``level_id``.

    Level 7 is dynamic: a fresh solvable layout is generated on every call
    unless ``seed`` is given (same seed -> same layout, used to keep
    retry/replay on one layout while level-select entries get new ones).
    """
    if level_id == config.RANDOM_LEVEL_ID:
        # Dynamic level: fresh solvable layout on every call (lazy import
        # avoids a data <-> random_level import cycle).
        from .random_level import generate_random_level
        return generate_random_level(seed=seed)
    for level in LEVELS:
        if level.id == level_id:
            return level
    raise KeyError(f"Unknown level {level_id}")
