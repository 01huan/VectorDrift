"""Achievements: the list, what unlocks each one, and the player's progress.

Unlocked ids live in Session.achievements ({id: ISO time}); counters and
partial progress live in Session.achievement_progress. Both are saved with
the profile's stats (see account/integration.py), like seen_intro.

The game reports what happened through a few small calls (unlock, clear,
flight_ended, ...). check_state() looks at things the session already
records (records, ships, coins) so it also unlocks for players whose
progress came before achievements existed; SceneManager runs it now and
then. Every new unlock plays the "achievement" sound, is saved, and shows a
popup (SceneManager.toasts).
"""

import re
from dataclasses import dataclass
from datetime import datetime, timezone

# Categories: order of the achievements page, and the icon drawn for each.
PROGRESS, SKILL, MECHANICS, CREATION, FAILURE = "progress", "skill", "mechanics", "creation", "failure"
CATEGORIES = (PROGRESS, SKILL, MECHANICS, CREATION, FAILURE)

FAST_CLEAR_S = 3.0              # Faster Than Light
BOUNCES_IN_ONE_FLIGHT = 5       # Bounce House
OUT_OF_BOUNDS_TOTAL = 10        # Lost in Space
ABILITIES = ("ability_boost", "ability_shield_pulse", "ability_magnet")   # Power Trip

# Session.achievement_progress keys
OUT_OF_BOUNDS = "out_of_bounds"         # int: flights that left the map
ABILITIES_USED = "abilities_used"       # list of ability ids used at least once
CLEAN_CLEARS = "clean_clears"           # list of fixed level ids cleared without an answer


@dataclass(frozen=True)
class Achievement:
    id: str
    name: str
    description: str
    category: str
    hidden: bool = False        # shown as "???" until unlocked


ACHIEVEMENTS = (
    Achievement("is_anyone_out_there", "Is Anyone Out There?", "Answer the distress call", PROGRESS),
    Achievement("we_have_liftoff", "We Have Liftoff", "Clear Level 1", PROGRESS),
    Achievement("home_sweet_home", "Home Sweet Home", "Guide the ship through every campaign level", PROGRESS),

    Achievement("beginners_luck", "Beginner's Luck", "Clear a level on your very first launch", SKILL),
    Achievement("not_today_gravity", "Not Today, Gravity", "Clear a level with one life left", SKILL),
    Achievement("look_ma_no_hints", "Look Ma, No Hints",
                "Clear every campaign level without peeking at an answer", SKILL),
    Achievement("who_needs_robots", "Who Needs Robots?", "Clear a random level without the AI Solver", SKILL),
    Achievement("keep_it_constant", "Keep It Constant", "Clear a level without a single x or y", SKILL),
    Achievement("sine_of_the_times", "Sine of the Times", "Clear a level with sin, cos or tan", SKILL),
    Achievement("faster_than_light", "Faster Than Light", "Clear a level in under 3 seconds of flight", SKILL),
    Achievement("fashionably_late", "Fashionably Late", "Run out of time, keep going, and still make it", SKILL),

    Achievement("bounce_house", "Bounce House", "Bounce off rocks 5 times in one flight", MECHANICS),
    Achievement("hole_in_one", "Hole in One", "Fly through a black hole", MECHANICS),
    Achievement("kaboom", "Kaboom!", "Blow up a rock with a shockwave", MECHANICS),
    Achievement("not_a_scratch", "Not a Scratch", "Let a shield take the hit", MECHANICS),
    Achievement("thinking_outside_the_box", "Thinking Outside the Box", "Fly beyond the edge of the map",
                MECHANICS),
    Achievement("halfway_there", "Halfway There", "Reach a checkpoint", MECHANICS),
    Achievement("pocket_change", "Pocket Change", "Collect every coin in the campaign", MECHANICS),
    Achievement("fleet_commander", "Fleet Commander", "Own all six ships", MECHANICS),
    Achievement("power_trip", "Power Trip", "Use Boost, Shield Pulse and Magnet", MECHANICS),

    Achievement("built_different", "Built Different", "Save a level in the Level Editor", CREATION),
    Achievement("signal_sent", "Signal Sent", "Upload a community level", CREATION),
    Achievement("space_tourist", "Space Tourist", "Clear a community level", CREATION),
    Achievement("instant_replay", "Instant Replay", "Watch a replay to the end", CREATION),

    Achievement("houston", "Houston, We Have a Problem", "Lose every life in a level", FAILURE, hidden=True),
    Achievement("divide_by_zero", "Divide by Zero", "Get flung by an infinite force", FAILURE, hidden=True),
    Achievement("lost_in_space", "Lost in Space", "Fly out of bounds 10 times", FAILURE, hidden=True),
)
BY_ID = {a.id: a for a in ACHIEVEMENTS}

_TRIG = re.compile(r"\b(sin|cos|tan)\s*\(")
_XY = re.compile(r"(?<![a-z])[xy](?![a-z])")


# --- state -----------------------------------------------------------------------
def unlocked(session):
    return getattr(session, "achievements", None) or {}


def is_unlocked(session, achievement_id):
    return achievement_id in unlocked(session)


def progress(session):
    data = getattr(session, "achievement_progress", None)
    if not isinstance(data, dict):
        data = {}
        session.achievement_progress = data
    return data


def _add_to_list(session, key, value):
    """Add ``value`` to the progress list ``key``; returns the list as a set."""
    data = progress(session)
    items = set(data.get(key) or ())
    items.add(value)
    data[key] = sorted(items)
    return items


def unlock(manager, achievement_id, notify=True):
    """Unlock one achievement. Returns True only the first time.

    A new unlock is saved; with ``notify`` it also plays the sound and
    queues the popup.
    """
    session = manager.session
    if achievement_id not in BY_ID or is_unlocked(session, achievement_id):
        return False
    if not isinstance(getattr(session, "achievements", None), dict):
        session.achievements = {}
    session.achievements[achievement_id] = datetime.now(timezone.utc).isoformat()
    if notify:
        toasts = getattr(manager, "toasts", None)
        if toasts is not None:
            toasts.push(BY_ID[achievement_id])
        try:
            manager.audio.play("achievement")
        except Exception:           # noqa: BLE001 - sound is optional
            pass
    try:
        from .account.integration import save_progress
        save_progress(getattr(manager, "account", None), session)
    except Exception:               # noqa: BLE001 - saving never stops play
        pass
    return True


# --- campaign facts --------------------------------------------------------------
def campaign_level_ids():
    """Ids of the built-in fixed levels (random and custom levels excluded)."""
    from .data import LEVELS
    from .level_presets import is_dynamic_level
    return [level.id for level in LEVELS if not is_dynamic_level(level.id)]


def campaign_coin_keys():
    """The collected_money_pickups key of every coin in the campaign."""
    from .data import LEVELS
    from .data_models import section_count, section_level
    keys = set()
    for level in LEVELS:
        for index in range(section_count(level)):
            part = section_level(level, index) if level.sections else level
            for pickup in part.pickups or ():
                if pickup.kind == "money":
                    keys.add((level.id, tuple(pickup.center)))
    return keys


def formula_uses_xy(*formulas):
    return any(_XY.search(f.lower()) for f in formulas)


def formula_uses_trig(*formulas):
    return any(_TRIG.search(f.lower()) for f in formulas)


# --- what the game reports ---------------------------------------------------------
def _in_tutorial(manager):
    """Tutorial screens (counts_for_progress = False) report nothing."""
    return getattr(getattr(manager, "scene", None), "counts_for_progress", True) is False


def clear(manager, *, level_id, kind, attempts, lives_left, total_time, fx, fy,
          solution_used=False, solver_used=False, resumed=False):
    """A level was cleared. ``kind``: "campaign", "random" or "community" (or "custom")."""
    if _in_tutorial(manager):
        return
    if kind == "campaign":
        if level_id == 1:
            unlock(manager, "we_have_liftoff")
        if not solution_used:
            _add_to_list(manager.session, CLEAN_CLEARS, level_id)
    if kind == "random" and not solver_used:
        unlock(manager, "who_needs_robots")
    if kind == "community":
        unlock(manager, "space_tourist")
    if attempts == 1:
        unlock(manager, "beginners_luck")
    if lives_left == 1:
        unlock(manager, "not_today_gravity")
    if not formula_uses_xy(fx, fy):
        unlock(manager, "keep_it_constant")
    if formula_uses_trig(fx, fy):
        unlock(manager, "sine_of_the_times")
    if total_time < FAST_CLEAR_S:
        unlock(manager, "faster_than_light")
    if resumed:
        unlock(manager, "fashionably_late")
    check_state(manager)


def flight_ended(manager, outcome_name, lives_left):
    """A flight ended without a clear (``outcome_name``: an Outcome's name)."""
    if _in_tutorial(manager):
        return
    if outcome_name == "OUT_OF_BOUNDS":
        data = progress(manager.session)
        data[OUT_OF_BOUNDS] = int(data.get(OUT_OF_BOUNDS, 0)) + 1
        if data[OUT_OF_BOUNDS] >= OUT_OF_BOUNDS_TOTAL:
            unlock(manager, "lost_in_space")
    if lives_left <= 0:
        unlock(manager, "houston")


def checkpoint_reached(manager):
    """A checkpoint of a multi-section level was reached."""
    if _in_tutorial(manager):
        return
    unlock(manager, "halfway_there")


def in_flight(manager, flight, off_map=False):
    """Checked every frame of a flight: bounces, holes, flings, the map edge."""
    if _in_tutorial(manager):
        return
    if getattr(flight, "bounces", 0) >= BOUNCES_IN_ONE_FLIGHT:
        unlock(manager, "bounce_house")
    if getattr(flight, "teleports", 0) > 0:
        unlock(manager, "hole_in_one")
    if getattr(flight, "flings", 0) > 0:
        unlock(manager, "divide_by_zero")
    if off_map and getattr(flight, "unbound", False):
        unlock(manager, "thinking_outside_the_box")


def pickup_event(manager, event):
    if _in_tutorial(manager):
        return
    kind = event.get("kind")
    if kind == "shockwave" and event.get("destroyed"):
        unlock(manager, "kaboom")
    elif kind == "shield_used":
        unlock(manager, "not_a_scratch")
    elif kind == "money":
        check_state(manager)


def ability_used(manager, ability_id):
    if _in_tutorial(manager):
        return
    used = _add_to_list(manager.session, ABILITIES_USED, ability_id)
    if set(ABILITIES) <= used:
        unlock(manager, "power_trip")


def check_state(manager):
    """Unlock what the saved progress already proves (safe to call any time)."""
    session = manager.session
    campaign = set(campaign_level_ids())
    cleared = {int(k) for k in (getattr(session, "records", None) or {}) if str(k).lstrip("-").isdigit()}
    if 1 in cleared:
        unlock(manager, "we_have_liftoff")
    if campaign and campaign <= cleared:
        unlock(manager, "home_sweet_home")
    if campaign and campaign <= set(progress(session).get(CLEAN_CLEARS) or ()):
        unlock(manager, "look_ma_no_hints")
    coins = campaign_coin_keys()
    collected = {(k[0], tuple(k[1])) for k in (getattr(session, "collected_money_pickups", None) or ())
                 if isinstance(k, tuple) and len(k) == 2}
    if coins and coins <= collected:
        unlock(manager, "pocket_change")
    from .data import SHIPS
    if set(SHIPS) <= set(getattr(session, "owned_ships", None) or ()):
        unlock(manager, "fleet_commander")


def counts(session):
    """(unlocked, total) for the page header."""
    return len([a for a in ACHIEVEMENTS if is_unlocked(session, a.id)]), len(ACHIEVEMENTS)
