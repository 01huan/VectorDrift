"""Level registry and routing.

The value objects live in :mod:`vector_drift.data_models`, fixed content in
:mod:`vector_drift.data_levels`, serialization in
:mod:`vector_drift.data_serialization`, and untrusted public-level validation
in :mod:`vector_drift.data_public`. This module keeps the mutable registries
and the public lookup API, and re-exports the old names for compatibility.

Dynamic levels (e.g. 8) are NOT hard-coded here: their tunables and optional
per-level templates live in level_presets.py; their layouts are generated
fresh by random_level.py and merged into one to three screens by
level_merge.py. get_level() routes any id in
level_presets.dynamic_ids() to the generator, so gameplay always uses
get_level() instead of reading LEVELS directly.
"""

import hashlib

from .accessors import owned_ship_ids as _owned_ship_ids
from .data_models import (
    HoleSpec,
    LevelSpec,
    ObstacleSpec,
    PickupSpec,
    SectionSpec,
    ShipSpec,
    SHIPS,
    _ship_id,
    default_ship_id,
    level_holes,
    multi_section_level,
    section_count,
    section_level,
    section_shift,
    ship_unlocked,
)
from .data_levels import LEVELS
from .data_public import (
    PUBLIC_LEVEL_MAX_COORD,
    PUBLIC_LEVEL_MAX_HOLES,
    PUBLIC_LEVEL_MAX_LIVES,
    PUBLIC_LEVEL_MAX_NAME_LEN,
    PUBLIC_LEVEL_MAX_OBSTACLES,
    PUBLIC_LEVEL_MAX_PICKUPS,
    PUBLIC_LEVEL_MAX_RADIUS,
    PUBLIC_LEVEL_MAX_RESTITUTION,
    PUBLIC_LEVEL_MAX_TIME_LIMIT,
    PUBLIC_LEVEL_MIN_LIVES,
    PUBLIC_LEVEL_MIN_RADIUS,
    PUBLIC_LEVEL_MIN_TIME_LIMIT,
    _public_hole,
    _public_int,
    _public_name,
    _public_number,
    _public_obstacle,
    _public_pickup,
    _public_point,
    _public_radius,
    _supported_obstacle_kinds,
    _supported_pickup_kinds,
    level_spec_from_public,
)
from .data_serialization import (
    _hole_from_row,
    _holes_from_rows,
    _holes_to_rows,
    _level_spec_from_row,
    _level_spec_from_snapshot,
    _level_spec_to_row,
    _level_spec_to_snapshot,
    _list_or_empty,
    _obstacle_from_row,
    _obstacles_from_rows,
    _obstacles_to_rows,
    _pickup_from_row,
    _pickups_from_rows,
    _pickups_to_rows,
    custom_level_from_snapshot,
    custom_level_to_snapshot,
)
from .level_presets import dynamic_ids, get_preset, is_dynamic_level


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


# Custom (player-created) levels registry.
CUSTOM_LEVELS: dict[int, "LevelSpec"] = {}

# Community levels come from a public, untrusted table. Their local ids are
# generated here from the remote row UUID and live in a dedicated negative
# namespace, so they can never collide with a built-in level (positive id) or
# an editor-created level (>= 1000). The uploader-supplied ``level_data.id``
# is never used as a global id.
COMMUNITY_ID_SPACE = 1 << 30
_COMMUNITY_IDS_BY_REMOTE: dict[str, int] = {}
COMMUNITY_REMOTE_IDS: dict[int, str] = {}


def community_level_id(remote_id) -> int:
    """Local id for a community row, stable for the same remote UUID.

    The id is generated locally (negative namespace); the remote UUID is kept
    as the identity so the uploader cannot pick a colliding global id.
    """
    key = "" if remote_id is None else str(remote_id)
    if not key:
        # No remote id to key on (should not happen with Supabase rows):
        # hand out a fresh unique id instead of reusing one.
        candidate = -1
        while candidate in CUSTOM_LEVELS or candidate in COMMUNITY_REMOTE_IDS:
            candidate -= 1
            if candidate <= -COMMUNITY_ID_SPACE:
                raise RuntimeError("community level id space exhausted")
        COMMUNITY_REMOTE_IDS[candidate] = ""
        return candidate
    cached = _COMMUNITY_IDS_BY_REMOTE.get(key)
    if cached is not None:
        return cached
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    candidate = -1 - (int.from_bytes(digest[:7], "big") % COMMUNITY_ID_SPACE)
    while candidate in CUSTOM_LEVELS or candidate in COMMUNITY_REMOTE_IDS:
        candidate -= 1
        if candidate <= -COMMUNITY_ID_SPACE:
            raise RuntimeError("community level id space exhausted")
    _COMMUNITY_IDS_BY_REMOTE[key] = candidate
    COMMUNITY_REMOTE_IDS[candidate] = key
    return candidate


def community_remote_id(level_id):
    """Remote row UUID behind a locally generated community level id."""
    return COMMUNITY_REMOTE_IDS.get(level_id)


def register_custom_level(spec):
    """Register a custom level in ``CUSTOM_LEVELS``.

    Built-in levels are immutable: a custom id may never replace one, so a
    colliding id is rejected instead of overwriting ``LEVELS``. Community
    levels use negative ids and the editor uses ids >= 1000, so normal callers
    never hit this.
    """
    if any(level.id == spec.id for level in LEVELS):
        raise ValueError(f"custom level id {spec.id} collides with a built-in level")
    CUSTOM_LEVELS[spec.id] = spec
    return spec


def is_custom_level(level_id):
    return level_id in CUSTOM_LEVELS


def get_level(level_id, seed=None):
    """Return the spec for ``level_id``.

    Built-in and dynamic levels always win over custom ones: a custom id can
    never shadow them (community ids are negative, editor ids >= 1000).

    Dynamic ids (see level_presets.dynamic_ids()) generate a fresh solvable
    layout on every call unless ``seed`` is given (same seed -> same layout,
    used to keep retry/replay on one layout while level-select entries get a
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
    if level_id in CUSTOM_LEVELS:
        return CUSTOM_LEVELS[level_id]
    raise KeyError(f"Unknown level {level_id}")


__all__ = [
    "ShipSpec", "ObstacleSpec", "PickupSpec", "LevelSpec", "SectionSpec",
    "HoleSpec", "SHIPS", "LEVELS", "CUSTOM_LEVELS", "all_levels", "get_level",
    "register_custom_level", "is_custom_level", "community_level_id",
    "community_remote_id", "COMMUNITY_ID_SPACE", "COMMUNITY_REMOTE_IDS",
    "section_count", "section_level", "section_shift", "multi_section_level",
    "ship_unlocked", "default_ship_id", "level_holes",
    "custom_level_to_snapshot", "custom_level_from_snapshot",
    "level_spec_from_public",
]
