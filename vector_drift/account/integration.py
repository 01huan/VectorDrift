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
ABILITY_CHARGES_KEY = "ability_charges"


def _consumable_ability_ids() -> set:
    try:
        from ..abilities import ABILITIES
        return {aid for aid, ability in ABILITIES.items()
                if getattr(ability, "consumable", True)}
    except Exception:
        return set()
CUSTOM_LEVELS_KEY = "custom_levels"
# The Function Lab's library (named Fx/Fy pairs) rides along in the profile's
# stats, so the cloud schema needs no new column.
FUNCTION_LIBRARY_KEY = "function_library"
# The id of the function the player imported for use in the normal levels.
IMPORTED_FUNCTION_KEY = "imported_function_id"
# Whether the intro story has started (Session.seen_intro), saved the same way.
# Missing means not seen. Applying a save keeps it if either side saw it.
SEEN_INTRO_KEY = "seen_intro"
# Local id of the player (Session.player_key): the community statistics use
# it to count the different players who cleared a level.  It rides along in
# the profile's stats, so no extra column is needed.
PLAYER_KEY_KEY = "player_key"
# Monotonic high-water mark for player-created level ids (saved in the
# profile's stats).  Prevents re-issuing the id of a deleted custom level,
# which would inherit its records, paid-answer and reward state.
NEXT_CUSTOM_LEVEL_ID_KEY = "next_custom_level_id"
# Achievements (Session.achievements, Session.achievement_progress), saved the
# same way.  They are progress like the rest: applying a save replaces the
# session's with the applied copy's, so the achievements follow the player's
# choice (local or cloud) when the two copies differ.
ACHIEVEMENTS_KEY = "achievements"
ACHIEVEMENT_PROGRESS_KEY = "achievement_progress"


def _custom_levels_to_rows(levels: Any) -> list[dict]:
    return [level.to_row() for level in (levels or ())]


def _restore_custom_levels(session: Any, rows: Any) -> None:
    from vector_drift import data
    from vector_drift.data import LevelSpec, ObstacleSpec, PickupSpec

    levels = []
    for row in rows if isinstance(rows, list) else ():
        if not isinstance(row, dict):
            continue
        level = LevelSpec.from_row(row)
        if level is None:
            continue
        if level.id < 0:
            # An older version added the community levels it played to the
            # player's own custom levels.  Community levels have a negative
            # local id and belong to another player, so they are dropped here
            # instead of being restored as the player's own levels.
            data.CUSTOM_LEVELS.pop(level.id, None)
            continue
        try:
            data.register_custom_level(level)
        except ValueError:
            # A legacy profile can carry a custom id that collides with a
            # built-in level.  Built-ins are immutable and win, so skip the
            # custom copy instead of corrupting the level registry.
            continue
        levels.append(level)
    session.custom_levels = levels
    session.custom_level_ids = {level.id for level in levels}


def _restore_function_library(session: Any, rows: Any) -> None:
    """Put the saved functions back into the session."""
    from vector_drift.function_library import library_from_rows

    session.function_library = library_from_rows(rows)


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
    saved_intro = stats.pop(SEEN_INTRO_KEY, False) is True
    session.seen_intro = bool(getattr(session, "seen_intro", False)) or saved_intro
    saved_player_key = stats.pop(PLAYER_KEY_KEY, None)
    if saved_player_key:
        try:
            session.player_key = str(saved_player_key)
        except Exception:
            pass
    try:
        session.next_custom_level_id = max(
            1000, int(stats.pop(NEXT_CUSTOM_LEVEL_ID_KEY, 1000) or 1000))
    except (TypeError, ValueError, OverflowError):
        session.next_custom_level_id = 1000
    _apply_achievements(session, stats.pop(ACHIEVEMENTS_KEY, None),
                         stats.pop(ACHIEVEMENT_PROGRESS_KEY, None))
    _restore_custom_levels(session, stats.pop(CUSTOM_LEVELS_KEY, None))
    _restore_function_library(session, stats.pop(FUNCTION_LIBRARY_KEY, None))
    imported_id = stats.pop(IMPORTED_FUNCTION_KEY, None)
    session.imported_function_id = str(imported_id) if imported_id else None
    charges = stats.pop(ABILITY_CHARGES_KEY, None) or {}
    existing = getattr(session, "ability_charges", None)
    merged = dict(existing) if isinstance(existing, dict) else {}
    if isinstance(charges, dict):
        for key, value in charges.items():
            if isinstance(value, (int, float, str)):
                try:
                    merged[str(key)] = int(value)
                except (TypeError, ValueError):
                    continue
    # Keep any counts already present when the incoming profile omits them,
    # so an upload/download round trip never wipes the remaining uses.
    session.ability_charges = merged

    # Legacy migration: abilities used to be permanent unlocks tracked only via
    # purchased_items.  Convert any such id into a single charge so the skill
    # survives the move to the charge-based model, then drop it from
    # purchased_items so it is not mistaken for a permanent unlock.
    try:
        from ..abilities import ABILITIES
        purchased = getattr(session, "purchased_items", None)
        if isinstance(purchased, set):
            for aid, ability in ABILITIES.items():
                if getattr(ability, "consumable", True) and aid in purchased \
                        and aid not in session.ability_charges:
                    session.ability_charges[aid] = 1
            purchased.difference_update(
                aid for aid, ability in ABILITIES.items()
                if getattr(ability, "consumable", True))
            session.purchased_items = purchased
    except Exception:
        pass
    if stats:
        session.stats = stats


def _apply_achievements(session: Any, saved: Any, saved_progress: Any) -> None:
    """The applied profile's unlocks replace the session's.

    When the local and the cloud data differ, the player picks which copy to
    keep ("Use Local" / "Use Cloud"), and the achievements follow that choice
    like every other progress field -- they are not merged with the other side.
    A profile without the keys (saved before achievements existed) leaves the
    session's alone.
    """
    if saved is not None:
        session.achievements = ({aid: str(when) for aid, when in saved.items()
                                  if isinstance(aid, str)}
                                 if isinstance(saved, dict) else {})
    if saved_progress is not None:
        progress = {}
        if isinstance(saved_progress, dict):
            for key, value in saved_progress.items():
                if isinstance(value, bool):
                    continue
                if isinstance(value, (int, float)):
                    try:
                        progress[key] = int(value)
                    except (TypeError, ValueError, OverflowError):
                        continue
                elif isinstance(value, (list, tuple, set, frozenset)):
                    items = set()
                    for item in value:
                        try:
                            items.add(item)
                        except TypeError:      # a broken entry (a list in a list)
                            continue
                    # Sorted by its text: the lists hold level ids (numbers) and
                    # ability ids (names), and a mixed set cannot be sorted by value.
                    progress[key] = sorted(items, key=str)
        session.achievement_progress = progress


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
    try:
        session.cloud_save_pending = False
    except Exception:
        pass

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

    def _stats(profile):
        # seen_intro is merged (either side True), so it never needs a choice.
        stats = dict(getattr(profile, "stats", {}) or {})
        stats.pop(SEEN_INTRO_KEY, None)
        # The player id is an installation detail, not game progress: two
        # devices signed into the same account each generate their own id and
        # must not be treated as a local/cloud conflict.
        stats.pop(PLAYER_KEY_KEY, None)
        # The achievements are progress like the rest: they are not merged
        # between the two copies, so a difference in them is a difference the
        # player is asked about ("Use Local" / "Use Cloud"). A profile saved
        # before the achievements existed counts as "none unlocked".
        stats.setdefault(ACHIEVEMENTS_KEY, {})
        stats.setdefault(ACHIEVEMENT_PROGRESS_KEY, {})
        return stats

    return (
        getattr(a, "money", None) == getattr(b, "money", None)
        and _norm(getattr(a, "owned_ships", set())) == _norm(getattr(b, "owned_ships", set()))
        and _norm(getattr(a, "purchased_items", set())) == _norm(getattr(b, "purchased_items", set()))
        and _norm(getattr(a, "records", {})) == _norm(getattr(b, "records", {}))
    and _norm(getattr(a, "replays", [])) == _norm(getattr(b, "replays", []))
        and _norm(getattr(a, "collected_money_pickups", set())) == _norm(getattr(b, "collected_money_pickups", set()))
        and _norm(_stats(a)) == _norm(_stats(b))
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
    from vector_drift.function_library import library_to_rows

    stats = {**(session.stats or {}),
             CLEAR_REWARDED_KEY: sorted(getattr(session, "clear_rewarded_levels", ()) or ()),
             SEEN_INTRO_KEY: bool(getattr(session, "seen_intro", False)),
             ACHIEVEMENTS_KEY: dict(getattr(session, "achievements", None) or {}),
             ACHIEVEMENT_PROGRESS_KEY: dict(getattr(session, "achievement_progress", None) or {}),
             CUSTOM_LEVELS_KEY: _custom_levels_to_rows(getattr(session, "custom_levels", ())),
             FUNCTION_LIBRARY_KEY: library_to_rows(getattr(session, "function_library", ())),
             IMPORTED_FUNCTION_KEY: getattr(session, "imported_function_id", None),
             ABILITY_CHARGES_KEY: {
                 **(session.stats.get(ABILITY_CHARGES_KEY, {}) if isinstance(getattr(session, "stats", None), dict) else {}),
                 **(getattr(session, "ability_charges", {}) or {}),
             }}
    player_key = getattr(session, "player_key", None)
    if player_key:
        stats[PLAYER_KEY_KEY] = str(player_key)
    try:
        stats[NEXT_CUSTOM_LEVEL_ID_KEY] = max(
            1000, int(getattr(session, "next_custom_level_id", 1000) or 1000))
    except (TypeError, ValueError, OverflowError):
        stats[NEXT_CUSTOM_LEVEL_ID_KEY] = 1000
    return PlayerProfile(
        user_id=user_id,
        display_name=session.display_name,
        money=int(session.money),
        owned_ships=set(session.owned_ships or {"ship01"}),
        purchased_items=set(session.purchased_items or set()) - _consumable_ability_ids(),
        records=dict(session.records or {}),
        replays=list(getattr(session, "replays", None) or getattr(session, "launch_records", None) or [])[-10:],
        collected_money_pickups=set(session.collected_money_pickups or set()),
        stats=stats,
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
    session.ability_charges = {}
    session.seen_intro = False          # the next Start plays the intro again
    session.achievements = {}
    session.achievement_progress = {}
    # Delete player-created (local custom) levels together with the rest of
    # local data, so "Delete local data" removes them from memory and the
    # data registry (the guest profile file is already cleared by the caller).
    from vector_drift import data

    session.custom_levels = []
    session.custom_level_ids = set()
    session.next_custom_level_id = 1000
    # The Function Lab's library is deleted with the rest of the local data.
    session.function_library = []
    session.imported_function_id = None
    # register_custom_level() never writes to LEVELS (built-ins are
    # immutable), so clearing the custom registry is enough.
    data.CUSTOM_LEVELS.clear()
    session.user_id = None
    session.email = None
    session.display_name = None
    session.auth_status = "guest"
    session.profile_loaded = False
    session.sync_status = "idle"
    session.last_sync_error = None
    try:
        session.cloud_save_pending = False
    except Exception:
        pass
    session.cloud_save_pending = False
    session.fx_text = ""
    session.fy_text = ""
    session.random_seed = None
    session.level_id = 1
    session.ship_id = None
    session.hint_answer_confirmed = False
    # The local player id belongs to the deleted data: a fresh one is made
    # when the player plays a community level again.
    try:
        session.player_key = None
    except Exception:
        pass


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
    try:
        session.cloud_save_pending = False
    except Exception:
        pass


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
        try:
            session.cloud_save_pending = False
        except Exception:
            pass
        if local_error is not None:
            _mark_sync_error(session, local_error)
        else:
            session.sync_status = "idle"
            session.last_sync_error = None
        return

    # Defer the upload when the account manager is busy instead of failing it.
    if getattr(account, "is_busy", False):
        try:
            session.cloud_save_pending = True
            session.sync_status = "syncing"
        except Exception:
            pass
        if local_error is not None:
            _mark_sync_error(session, local_error)
        return

    try:
        session.cloud_save_pending = False
    except Exception:
        pass
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
