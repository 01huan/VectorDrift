"""Bridge helpers between account profiles and game Session.

Kept in the account package but importing the game Session lazily so that the
account subsystem stays usable (and testable) without importing pygame scenes.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .models import PlayerProfile
from .profile_manager import _profile_updated_at, _ts_gte

# Saves made before the story was removed carry the story lines already
# shown in their stats; the key is dropped on load and no longer written.
LEGACY_STORY_SEEN_KEY = "story_seen"
# Fixed levels whose clear reward was paid ride along in the profile's stats
# so the cloud schema needs no new column; Session keeps them apart
# (session.stats is overwritten by every win / fail).
CLEAR_REWARDED_KEY = "clear_rewarded_levels"
CUSTOM_LEVELS_KEY = "custom_levels"


def _custom_levels_to_rows(levels: Any) -> list[dict]:
    rows = []
    for level in levels or ():
        rows.append({
            "id": int(level.id),
            "name": level.name,
            "start": list(level.start),
            "target_center": list(level.target_center),
            "target_radius": float(level.target_radius),
            "ship_id": level.ship_id,
            "time_limit": float(level.time_limit),
            "lives": int(level.lives),
            "obstacles": [
                {"center": list(item.center), "radius": float(item.radius),
                 "restitution": float(item.restitution), "kind": item.kind}
                for item in level.obstacles
            ],
            "pickups": [
                {"center": list(item.center), "radius": float(item.radius), "kind": item.kind}
                for item in level.pickups
            ],
        })
    return rows


def _restore_custom_levels(session: Any, rows: Any) -> None:
    from vector_drift import data
    from vector_drift.data import LevelSpec, ObstacleSpec, PickupSpec

    levels = []
    for row in rows if isinstance(rows, list) else ():
        if not isinstance(row, dict):
            continue
        try:
            obstacles = tuple(
                ObstacleSpec(
                    center=tuple(item["center"]),
                    radius=float(item["radius"]),
                    restitution=float(item.get("restitution", 1.0)),
                    kind=item.get("kind", "bumper"),
                )
                for item in row.get("obstacles", ())
            )
            pickups = tuple(
                PickupSpec(
                    center=tuple(item["center"]),
                    radius=float(item.get("radius", 0.45)),
                    kind=item.get("kind", "shockwave"),
                )
                for item in row.get("pickups", ())
            )
            level = LevelSpec(
                id=int(row["id"]),
                name=str(row["name"]),
                start=tuple(row["start"]),
                target_center=tuple(row["target_center"]),
                target_radius=float(row["target_radius"]),
                ship_id=str(row.get("ship_id", "ship01")),
                time_limit=float(row.get("time_limit", 10.0)),
                lives=int(row.get("lives", 5)),
                obstacles=obstacles,
                pickups=pickups,
            )
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        data.register_custom_level(level)
        levels.append(level)
    session.custom_levels = levels
    session.custom_level_ids = {level.id for level in levels}


def _session_class():
    from vector_drift.scenes.base import Session

    return Session


def _apply_profile_stats(session: Any, stats: dict | None) -> None:
    stats = dict(stats or {})
    stats.pop(LEGACY_STORY_SEEN_KEY, None)
    rewarded = set()
    for lid in stats.pop(CLEAR_REWARDED_KEY, None) or ():
        try:
            rewarded.add(int(lid))
        except (TypeError, ValueError):
            continue
    session.clear_rewarded_levels = rewarded
    _restore_custom_levels(session, stats.pop(CUSTOM_LEVELS_KEY, None))
    if stats:
        session.stats = stats


def apply_profile_to_session(session: Any, profile: PlayerProfile, user_id: str, email: str | None = None) -> None:
    from vector_drift.money import Money

    session.money = Money(profile.money)
    session.owned_ships = set(profile.owned_ships) or {"ship01"}
    session.purchased_items = set(profile.purchased_items)
    session.records = dict(profile.records)
    session.replays = list(getattr(profile, "replays", None) or [])
    session.collected_money_pickups = set(profile.collected_money_pickups)
    _apply_profile_stats(session, profile.stats)
    session.display_name = profile.display_name
    session.user_id = user_id
    session.email = email
    session.auth_status = "authenticated"
    session.profile_loaded = True
    session.sync_status = "idle"
    session.last_sync_error = None

def profiles_equal(a: Any, b: Any) -> bool:
    """Return True when two profiles carry the same game data.

    Timestamps (``updated_at``) are ignored: only the actual progress matters
    for deciding whether the local and cloud copies disagree.
    """
    if a is None or b is None:
        return False

    def _norm(v):
        if isinstance(v, set):
            return frozenset(v)
        if isinstance(v, dict):
            return tuple(sorted((k, _norm(val)) for k, val in v.items()))
        if isinstance(v, (list, tuple)):
            return tuple(sorted(_norm(x) for x in v))
        return v

    return (
        getattr(a, "money", None) == getattr(b, "money", None)
        and _norm(getattr(a, "owned_ships", set())) == _norm(getattr(b, "owned_ships", set()))
        and _norm(getattr(a, "purchased_items", set())) == _norm(getattr(b, "purchased_items", set()))
        and _norm(getattr(a, "records", {})) == _norm(getattr(b, "records", {}))
    and _norm(getattr(a, "replays", [])) == _norm(getattr(b, "replays", []))
        and _norm(getattr(a, "collected_money_pickups", set())) == _norm(getattr(b, "collected_money_pickups", set()))
        and _norm(getattr(a, "stats", {})) == _norm(getattr(b, "stats", {}))
        and getattr(a, "display_name", None) == getattr(b, "display_name", None)
    )




def apply_best_profile(session: Any, cloud_profile: Any, user_id: str, email: str | None = None) -> Any:
    """Apply the newest of the local guest profile vs. the cloud profile to ``session``.

    Local data is trusted: when timestamps are equal, or the local profile is newer,
    the local profile wins and is written to the session.  Returns the profile that
    was applied (or ``None`` when there is nothing to apply).
    """
    from .local_profile_manager import LocalProfileManager

    local = LocalProfileManager().load()
    chosen = cloud_profile
    if local is not None:
        if cloud_profile is None or _ts_gte(
            _profile_updated_at(local), _profile_updated_at(cloud_profile)
        ):
            chosen = local

    if chosen is None:
        return None
    apply_profile_to_session(session, chosen, user_id, email)
    return chosen


def session_to_profile(session: Any, user_id: str) -> PlayerProfile:
    return PlayerProfile(
        user_id=user_id,
        display_name=session.display_name,
        money=int(session.money),
        owned_ships=set(session.owned_ships or {"ship01"}),
        purchased_items=set(session.purchased_items or set()),
        records=dict(session.records or {}),
        replays=list(getattr(session, "replays", None) or getattr(session, "launch_records", None) or [])[-10:],
        collected_money_pickups=set(session.collected_money_pickups or set()),
        stats={**(session.stats or {}),
               CLEAR_REWARDED_KEY: sorted(getattr(session, "clear_rewarded_levels", ()) or ()),
               CUSTOM_LEVELS_KEY: _custom_levels_to_rows(getattr(session, "custom_levels", ()))},
        updated_at=datetime.now(timezone.utc).isoformat(),
    )


def reset_session_to_guest(session: Any) -> None:
    from vector_drift.money import Money

    session.money = Money(0)
    session.owned_ships = {"ship01"}
    session.purchased_items = set()
    session.records = {}
    session.replays = []
    session.collected_money_pickups = set()
    session.stats = {}
    session.clear_rewarded_levels = set()
    # Delete player-created (local custom) levels together with the rest of
    # local data, so "Delete local data" removes them from memory and the
    # data registry (the guest profile file is already cleared by the caller).
    from vector_drift import data

    session.custom_levels = []
    session.custom_level_ids = set()
    custom_ids = set(data.CUSTOM_LEVELS)
    data.CUSTOM_LEVELS.clear()
    data.LEVELS[:] = [lv for lv in data.LEVELS if lv.id not in custom_ids]
    session.user_id = None
    session.email = None
    session.display_name = None
    session.auth_status = "guest"
    session.profile_loaded = False
    session.sync_status = "idle"
    session.last_sync_error = None
    session.fx_text = ""
    session.fy_text = ""
    session.random_seed = None
    session.level_id = 1
    session.ship_id = None
    session.hint_answer_confirmed = False


def apply_guest_profile_to_session(session, profile):
    from vector_drift.money import Money

    session.money = Money(profile.money)
    session.owned_ships = set(profile.owned_ships) or {"ship01"}
    session.purchased_items = set(profile.purchased_items)
    session.records = dict(profile.records)
    session.replays = list(getattr(profile, "replays", None) or [])
    session.collected_money_pickups = set(profile.collected_money_pickups)
    _apply_profile_stats(session, profile.stats)
    session.display_name = profile.display_name
    session.user_id = None
    session.email = None
    session.auth_status = "guest"
    session.profile_loaded = False
    session.sync_status = "idle"
    session.last_sync_error = None


def session_to_guest_profile(session):
    return session_to_profile(session, "guest")


def load_guest_profile_into_session(session):
    from .local_profile_manager import LocalProfileManager

    profile = LocalProfileManager().load()
    if profile is None:
        return False
    apply_guest_profile_to_session(session, profile)
    return True


def save_guest_profile(session):
    from .local_profile_manager import LocalProfileManager

    profile = session_to_profile(session, "guest")
    LocalProfileManager().save(profile)


def _mark_sync_error(session: Any, exc: Exception) -> None:
    session.sync_status = "error"
    session.last_sync_error = str(exc)


def _save_cloud_profile(account: Any, session: Any, local_error: Exception | None) -> None:
    is_authenticated = getattr(account, "is_authenticated", None)
    current_user = getattr(account, "current_user", None)
    if account is None or is_authenticated is None or not is_authenticated() or current_user is None:
        if local_error is not None:
            _mark_sync_error(session, local_error)
        else:
            session.sync_status = "idle"
            session.last_sync_error = None
        return

    profile = session_to_profile(session, current_user.id)
    session.sync_status = "syncing"

    def _on_saved():
        if local_error is not None:
            _mark_sync_error(session, local_error)
        else:
            session.sync_status = "idle"
            session.last_sync_error = None

    def _on_error(exc):
        session.sync_status = "error"
        session.last_sync_error = str(exc)

    account.save_profile_async(profile, on_success=_on_saved, on_error=_on_error)


def save_progress(account: Any, session: Any) -> None:
    """Write progress to local storage immediately and sync it to cloud if signed in."""
    local_error = None
    try:
        save_guest_profile(session)
    except Exception as exc:
        local_error = exc
    try:
        _save_cloud_profile(account, session, local_error)
    except Exception as exc:
        _mark_sync_error(session, exc)


def save_profile_if_authenticated(account: Any, session: Any) -> None:
    """Persist locally for everyone and sync to cloud when signed in."""
    save_progress(account, session)


def clear_guest_profile(session=None):
    from .local_profile_manager import LocalProfileManager

    LocalProfileManager().clear()
    if session is not None:
        reset_session_to_guest(session)
