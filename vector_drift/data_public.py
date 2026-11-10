"""Validation for untrusted (community) level data.

Community ``level_data`` is public and can be written by anybody, so it is
validated before it becomes a LevelSpec. The bounds are deliberately
generous: they reject garbage (negative/huge values, NaN/inf, absurd object
counts) without limiting ordinary designs.
"""

import math

from .data_models import HoleSpec, LevelSpec, ObstacleSpec, PickupSpec, SHIPS

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
    # Lazy import: data loads before pygame/scenes, and sprites does not
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


__all__ = [
    "level_spec_from_public",
    "PUBLIC_LEVEL_MAX_NAME_LEN", "PUBLIC_LEVEL_MAX_COORD",
    "PUBLIC_LEVEL_MIN_RADIUS", "PUBLIC_LEVEL_MAX_RADIUS",
    "PUBLIC_LEVEL_MIN_TIME_LIMIT", "PUBLIC_LEVEL_MAX_TIME_LIMIT",
    "PUBLIC_LEVEL_MIN_LIVES", "PUBLIC_LEVEL_MAX_LIVES",
    "PUBLIC_LEVEL_MAX_OBSTACLES", "PUBLIC_LEVEL_MAX_PICKUPS",
    "PUBLIC_LEVEL_MAX_HOLES", "PUBLIC_LEVEL_MAX_RESTITUTION",
]
