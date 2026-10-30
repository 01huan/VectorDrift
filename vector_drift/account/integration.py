"""Bridge helpers between account profiles and game Session.

Kept in the account package but importing the game Session lazily so that the
account subsystem stays usable (and testable) without importing pygame scenes.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .models import PlayerProfile


def _session_class():
    from vector_drift.scenes.base import Session

    return Session


def apply_profile_to_session(session: Any, profile: PlayerProfile, user_id: str, email: str | None = None) -> None:
    from vector_drift.money import Money

    session.money = Money(profile.money)
    session.owned_ships = set(profile.owned_ships) or {"ship01"}
    session.purchased_items = set(profile.purchased_items)
    session.records = dict(profile.records)
    session.collected_money_pickups = set(profile.collected_money_pickups)
    session.stats = dict(profile.stats) if profile.stats else session.stats
    session.display_name = profile.display_name
    session.user_id = user_id
    session.email = email
    session.auth_status = "authenticated"
    session.profile_loaded = True
    session.sync_status = "idle"
    session.last_sync_error = None


def session_to_profile(session: Any, user_id: str) -> PlayerProfile:
    return PlayerProfile(
        user_id=user_id,
        display_name=session.display_name,
        money=int(session.money),
        owned_ships=set(session.owned_ships or {"ship01"}),
        purchased_items=set(session.purchased_items or set()),
        records=dict(session.records or {}),
        collected_money_pickups=set(session.collected_money_pickups or set()),
        stats=dict(session.stats or {}),
        updated_at=datetime.now(timezone.utc).isoformat(),
    )


def reset_session_to_guest(session: Any) -> None:
    from vector_drift.money import Money

    session.money = Money(0)
    session.owned_ships = {"ship01"}
    session.purchased_items = set()
    session.records = {}
    session.collected_money_pickups = set()
    session.stats = {}
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
    session.collected_money_pickups = set(profile.collected_money_pickups)
    session.stats = dict(profile.stats) if profile.stats else session.stats
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

    try:
        profile = session_to_profile(session, "guest")
    except Exception:
        return
    LocalProfileManager().save(profile)


def clear_guest_profile(session=None):
    from .local_profile_manager import LocalProfileManager

    LocalProfileManager().clear()
    if session is not None:
        reset_session_to_guest(session)
