"""Static game data: ships and levels.

New ships or levels (e.g. for a future reward/shop system) are added here.
"""

from dataclasses import dataclass


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
class LevelSpec:
    id: int
    name: str
    start: tuple                # (x, y) in m
    target_center: tuple        # (x, y) in m
    target_radius: float        # m
    ship_id: str
    time_limit: float = 10.0    # s of simulated flight per launch
    lives: int = 5


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
]


def get_level(level_id):
    for level in LEVELS:
        if level.id == level_id:
            return level
    raise KeyError(f"Unknown level {level_id}")
