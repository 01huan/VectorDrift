"""Random-level presets and their optional complete generation templates."""

from __future__ import annotations

from dataclasses import dataclass, field, replace


@dataclass(frozen=True)
class ValidationProfile:
    """Difficulty heuristics and validator settings for one level template.

    The validator runs fast geometric checks unconditionally, and optionally a
    short AI Solver probe that confirms a non-trivial solution exists under the
    formal physics.  ``require_solver_confirmed=False`` (the default) treats the
    probe as informational: the corridor/maze/ring construction guarantees a
    path, so a failed probe never rejects a level -- set it to ``True`` (or
    pass ``require_solver=True`` to ``generate_random_level``) to make the
    generator retry until the probe succeeds.
    """

    # AI Solver probe.
    run_solver: bool = True
    solver_template: str = "general_poly"
    solver_particles: int = 10
    solver_simulations: int = 16
    solver_max_steps: int | None = 480       # 4 s of flight is plenty to confirm
    require_solver_confirmed: bool = False
    max_attempts: int = 6                    # generation attempts before accepting
    # Difficulty heuristics (warnings/infos, never hard failures).
    reference_speed: float = 6.0             # m/s used for the route-time estimate
    max_route_time_fraction: float = 0.95    # estimated route time vs limit
    min_route_time_fraction: float = 0.05
    max_obstacle_density: float | None = None  # obstacles per m^2 (None = no check)


@dataclass(frozen=True)
class RandomPreset:
    """All tunables for one dynamic random level.

    ``templates`` can hold complete RandomPreset configurations. When present,
    generation chooses one configuration and uses it for the whole level.
    Without templates, this preset itself remains the generation config.
    """

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
    templates: tuple[RandomPreset, ...] = ()
    card_blurb: str = "New maze every visit"
    extra_rules: tuple = field(default=(), compare=False, repr=False)
    # Which generation module builds this template (see level_modules.py).
    generator: str = "corridor"
    # Pickups the level REQUIRES (must be present and reachable); the bomb
    # module marks its shockwave this way.
    required_pickup_kinds: tuple = ()
    # Difficulty heuristics + validator settings.
    validation: ValidationProfile = ValidationProfile()

    def __post_init__(self):
        if any(not isinstance(template, RandomPreset) for template in self.templates):
            raise TypeError("preset.templates must contain RandomPreset instances")
        if any(template.templates for template in self.templates):
            raise ValueError("random-level templates cannot contain nested templates")


_PRESET_8_TEMPLATE_1 = RandomPreset(
    level_id=8,
    name="Random Drift I",
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
    pickup_groups=(("life", (1, 2), 0.5), ("money", (1, 2), 0.5)),
    num_holes=2,
    card_blurb="New maze every visit",
)


_PRESET_8_TEMPLATE_2 = RandomPreset(
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
    pickup_groups=(("shockwave", (1, 3), 0.5), ("extratime", (1, 3), 0.5), ("shield", (1, 3), 0.5), ("life", (1, 3), 0.5), ("money", (1, 3), 0.5)),
    card_blurb="Denser maze, smaller target; shockwaves, extratime and shields",
)

_PRESET_8_WORMHOLE = RandomPreset(
    level_id=8,
    name="Random Drift III",
    generator="wormhole_network",
    time_limit=12.0,
    lives=4,
    target_radius=0.9,
    min_start_target_dist=14.0,
    num_hidden_points=0,
    num_obstacles=4,
    num_obstacles_min=3,
    num_obstacles_max=6,
    obstacle_radius_min=0.5,
    obstacle_radius_max=1.0,
    corridor_clearance=1.1,
    min_obstacle_gap=0.4,
    num_direct_blockers=0,
    num_holes=3,
    pickup_groups=(("money", (1, 2), 0.5), ("life", (1, 2), 0.5)),
    card_blurb="Wormhole gates: chain the black holes through sealed sectors",
)

_PRESET_8_MAZE = RandomPreset(
    level_id=8,
    name="Random Drift IV",
    generator="maze",
    time_limit=15.0,
    lives=5,
    target_radius=0.9,
    min_start_target_dist=10.0,
    num_hidden_points=0,
    num_obstacles=0,
    num_direct_blockers=0,
    pickup_groups=(("money", (2, 4), 0.5), ("extratime", (1, 1), 0.5)),
    # The maze's 15 s limit makes a full PSO probe expensive and rarely
    # informative; use a cheaper one (the BFS route still guarantees a path).
    validation=ValidationProfile(solver_particles=8, solver_simulations=8,
                                 solver_max_steps=360),
    card_blurb="A sealed maze; find the hidden route to the planet",
)

_PRESET_8_BOMB = RandomPreset(
    level_id=8,
    name="Random Drift V",
    generator="bomb",
    time_limit=10.0,
    lives=4,
    target_radius=0.8,
    min_start_target_dist=10.0,
    num_hidden_points=0,
    num_obstacles_min=3,
    num_obstacles_max=6,
    num_direct_blockers=0,
    required_pickup_kinds=("shockwave",),
    pickup_groups=(("money", (1, 2), 0.5), ("life", (1, 2), 0.5)),
    card_blurb="Bomb run: blast the ring to reach the planet",
)

_PRESET_8_EXTREME_TIME = RandomPreset(
    level_id=8,
    name="Random Drift VI",
    generator="extreme_time",
    time_limit=0.50,
    lives=2,
    target_radius=0.9,
    min_start_target_dist=10.0,
    num_hidden_points=5,
    num_obstacles=9,
    num_obstacles_min=6,
    num_obstacles_max=20,
    obstacle_radius_min=0.45,
    obstacle_radius_max=0.9,
    corridor_clearance=0.7,
    min_obstacle_gap=0.3,
    num_direct_blockers=0,
    pickup_groups=(("extratime", (1, 2), 0.5), ("money", (1, 2), 0.5)),
    card_blurb="Extreme time: a fast slalom against the clock",
)

PRESET_8 = replace(
    _PRESET_8_TEMPLATE_2,
    name="Random Drift",  # the card name; templates carry their own flavour names
    templates=(_PRESET_8_TEMPLATE_1, _PRESET_8_TEMPLATE_2, _PRESET_8_WORMHOLE,
               _PRESET_8_MAZE, _PRESET_8_BOMB, _PRESET_8_EXTREME_TIME),
    card_blurb="New module every visit: wormhole gates, maze, bomb run, extreme time",
)

PRESETS = {8: PRESET_8}


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
