"""JSON/row serialization for level specs.

Kept separate from the models so the value objects stay dependency-free and
the replay/community code can reuse the same conversion rules.
"""

from .data_models import HoleSpec, LevelSpec, ObstacleSpec, PickupSpec


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


def custom_level_to_snapshot(level):
    """Return a JSON-compatible copy of the editable custom-level state."""
    return _level_spec_to_snapshot(level)


def custom_level_from_snapshot(snapshot):
    """Rebuild a custom level from a replay's saved level state."""
    return _level_spec_from_snapshot(snapshot)


__all__ = [
    "custom_level_to_snapshot", "custom_level_from_snapshot",
    "_list_or_empty", "_obstacles_to_rows", "_obstacle_from_row",
    "_obstacles_from_rows", "_pickups_to_rows", "_pickup_from_row",
    "_pickups_from_rows", "_holes_to_rows", "_hole_from_row",
    "_holes_from_rows", "_level_spec_to_row", "_level_spec_from_row",
    "_level_spec_to_snapshot", "_level_spec_from_snapshot",
]
