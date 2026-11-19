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
from typing import Any, Iterable

from .accessors import owned_ship_ids as _owned_ship_ids
from .data_models import (
    HoleSpec,
    LevelSpec,
    ObstacleSpec,
    PickupSpec,
    SectionSpec,
    ShipSpec,
    SHIPS,
    DEFAULT_SHIP_ID,
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


def level_number(level_id):
    """The number the player sees for a level: its slot on the level select.

    A level's id is its identity in saves (best time, clear reward,
    achievements, replays) and never changes; its number is only its place
    and may move. A fixed level's number is its id. Dynamic levels (the
    random level, id RANDOM_LEVEL_ID = 999) come right after the last fixed
    level, in id order. Any other id (custom, community) is its own number.
    """
    if is_dynamic_level(level_id):
        last_fixed = max((level.id for level in LEVELS), default=0)
        return last_fixed + 1 + dynamic_ids().index(level_id)
    return level_id


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

# Community levels that were downloaded and are being played.  They live in
# their own registry: a community level belongs to another player, so playing
# one must never add it to the player's own custom levels (which are saved
# with the profile).  The registry is runtime-only -- it is never saved.
COMMUNITY_LEVELS: dict[int, "LevelSpec"] = {}

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
        while candidate in CUSTOM_LEVELS or candidate in COMMUNITY_REMOTE_IDS or candidate in COMMUNITY_LEVELS:
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
    while candidate in CUSTOM_LEVELS or candidate in COMMUNITY_REMOTE_IDS or candidate in COMMUNITY_LEVELS:
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


def clean_level_name(name: Any) -> str:
    """A usable level name: one line, never empty."""
    if not isinstance(name, str):
        name = ""
    return " ".join(name.split())[:60] or "Custom"


def unique_level_name(name: Any, levels: Iterable) -> str:
    """A level name that does not collide with another level in the library.

    ``"Maze"`` stays ``"Maze"`` when it is free; otherwise the first free
    ``"Maze (2)"``, ``"Maze (3)"`` ... is returned.  Existing levels are
    never renamed.  Comparison ignores case and repeated whitespace.
    """
    base = clean_level_name(name)
    taken = {" ".join(str(getattr(level, "name", "") or "").split()).casefold()
             for level in (levels or ())}
    if base.casefold() not in taken:
        return base
    for suffix in range(2, 1000):
        candidate = f"{base[:54].rstrip()} ({suffix})"
        if candidate.casefold() not in taken:
            return candidate
    return f"{base[:54].rstrip()} ({new_id_suffix()})"


def new_id_suffix() -> str:
    """A short random suffix for the (very unlikely) exhaustion case."""
    import uuid

    return uuid.uuid4().hex[:6]


def is_custom_level(level_id):
    return level_id in CUSTOM_LEVELS


def register_community_level(spec):
    """Register a downloaded community level for this session only.

    A community level is somebody else's level: it is kept in its own
    registry so that playing it never adds it to the player's own custom
    levels (the list that is saved with the profile and shown in the level
    editor).  The spec stays available for the game to load it.
    """
    COMMUNITY_LEVELS[spec.id] = spec
    return spec


def is_community_level(level_id):
    """True for a community level that was downloaded in this session."""
    return level_id in COMMUNITY_LEVELS


def level_ship_id(level_id, session=None):
    """The ship a level flies; the player does not pick it.

    Campaign level N (the random level too) flies shipNN, or ship01 while
    that ship is not in SHIPS yet. Community and custom levels fly ship01.
    """
    if is_community_level(level_id) or is_custom_map(level_id, session):
        return DEFAULT_SHIP_ID
    return default_ship_id(level_id)


def is_custom_map(level_id, session=None):
    """True for a map that is not part of the campaign.

    That is a player-created (custom) level and a community level.  Both
    follow the same rules in a run: the AI solver replaces the authored
    hints, the money pickups pay nothing and no clear reward is paid.
    """
    if level_id in CUSTOM_LEVELS or level_id in COMMUNITY_LEVELS:
        return True
    if session is not None:
        ids = getattr(session, "custom_level_ids", None)
        if ids:
            return level_id in ids
    return False


def get_level(level_id, seed=None):
    """Return the spec for ``level_id``.

    Built-in and dynamic levels always win over custom ones: a custom id can
    never shadow them (community ids are negative, editor ids >= 1000).

    Player-created levels come from ``CUSTOM_LEVELS``, community levels that
    were downloaded this session from ``COMMUNITY_LEVELS``.

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
    if level_id in COMMUNITY_LEVELS:
        return COMMUNITY_LEVELS[level_id]
    raise KeyError(f"Unknown level {level_id}")


__all__ = [
    "ShipSpec", "ObstacleSpec", "PickupSpec", "LevelSpec", "SectionSpec",
    "HoleSpec", "SHIPS", "LEVELS", "CUSTOM_LEVELS", "COMMUNITY_LEVELS",
    "all_levels", "get_level", "level_number",
    "register_custom_level", "is_custom_level", "community_level_id",
    "clean_level_name", "unique_level_name",
    "register_community_level", "is_community_level", "is_custom_map",
    "level_ship_id", "DEFAULT_SHIP_ID",
    "community_remote_id", "COMMUNITY_ID_SPACE", "COMMUNITY_REMOTE_IDS",
    "section_count", "section_level", "section_shift", "multi_section_level",
    "ship_unlocked", "default_ship_id", "level_holes",
    "custom_level_to_snapshot", "custom_level_from_snapshot",
    "level_spec_from_public",
]
