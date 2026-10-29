"""Random-level presets: one dataclass per dynamic level."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RandomPreset:
    """All tunables for one dynamic random level."""

    level_id: int
    name: str
    ship_id: str = "ship01"
    time_limit: float = 10.0
    lives: int = 5
    target_radius: float = 1.0
    min_start_target_dist: float = 10.0
    num_hidden_points: int = 7
    # Obstacle count: fixed (num_obstacles) by default, or random in
    # [num_obstacles_min, num_obstacles_max] when either bound is given.
    num_obstacles: int = 10
    num_obstacles_min: int | None = None
    num_obstacles_max: int | None = None
    obstacle_radius_min: float = 0.5
    obstacle_radius_max: float = 1.4
    corridor_clearance: float = 0.9
    start_clearance: float = 1.0
    target_clearance: float = 1.0
    min_obstacle_gap: float = 0.3
    edge_margin: float = 0.5
    endpoint_margin: float = 1.0
    hidden_margin: float = 0.5
    max_endpoint_attempts: int = 100
    max_place_attempts: int = 500
    max_level_attempts: int = 10
    num_direct_blockers: int = 1
    obstacle_kind: str = "bumper"
    restitution: float = 1.0
    # Random pickups live HERE (not in code): one (kind, count, radius)
    # group per pickup type. () = no pickups at all. Adding a new pickup
    # to random levels = appending one tuple here.
    pickup_groups: tuple = ()
    pickup_corridor_max: float = 0.6  # must sit ON the route (m from corridor)
    num_holes: int = 0
    num_wormholes: int = 0
    num_portals: int = 0
    card_blurb: str = "New maze every visit"
    extra_rules: tuple = field(default=(), compare=False, repr=False)


PRESET_7 = RandomPreset(
    level_id=7,
    name="Random Drift",
    ship_id="ship01",
    time_limit=10.0,
    lives=5,
    target_radius=1.0,
    min_start_target_dist=10.0,
    num_hidden_points=7,
    num_obstacles=10,
    num_obstacles_min=5,
    num_obstacles_max=20,
    obstacle_radius_min=0.5,
    obstacle_radius_max=1.4,
    corridor_clearance=0.9,
    start_clearance=1.0,
    target_clearance=1.0,
    min_obstacle_gap=0.3,
    edge_margin=0.5,
    endpoint_margin=1.0,
    hidden_margin=0.5,
    max_endpoint_attempts=100,
    max_place_attempts=500,
    max_level_attempts=10,
    num_direct_blockers=1,
    pickup_groups=(("life", (1, 2), 0.5),),
    num_holes=2,
    card_blurb="New maze every visit",
)


PRESET_8 = RandomPreset(
    level_id=8,
    name="Random Drift II",
    time_limit=12.0,
    lives=3,
    target_radius=0.8,
    min_start_target_dist=12.0,
    num_hidden_points=4,
    num_obstacles=14,
    num_obstacles_min=10,
    num_obstacles_max=18,
    obstacle_radius_min=0.4,
    obstacle_radius_max=1.0,
    corridor_clearance=0.7,
    start_clearance=1.2,
    target_clearance=1.2,
    min_obstacle_gap=0.4,
    num_direct_blockers=2,
    pickup_groups=(("shockwave", (1, 3), 0.5), ("extratime", (1, 3), 0.5), ("shield", (1, 3), 0.5), ("life", (1, 3), 0.5)),
    card_blurb="Denser maze, smaller target; shockwaves, extratime and shields",
)


PRESETS = {7: PRESET_7, 8: PRESET_8}


def get_preset(level_id):
    preset = PRESETS.get(level_id)
    if not isinstance(preset, RandomPreset):
        raise KeyError(f"Unknown random preset {level_id}")
    return preset


def register_preset(preset):
    if not isinstance(preset.level_id, int):
        raise TypeError("preset.level_id must be int")
    PRESETS[preset.level_id] = preset
    return preset


def is_dynamic_level(level_id):
    return level_id in PRESETS and isinstance(PRESETS[level_id], RandomPreset)


def dynamic_ids():
    return tuple(sorted(k for k in PRESETS if isinstance(k, int)))
