"""Achievements: the list, what unlocks each one, and the player's progress.

Two kinds:
- tiered: one achievement with four tiers (I-IV) on one number, e.g. rocks
  bounced off in total. Each tier unlocks on its own, with its own popup.
- single: one unlock, usually for something hard done once.

Unlocks live in Session.achievements ({key: ISO time}). A single
achievement's key is its id; a tier's key is "<id>.<tier>" (1-4).
Counters live in Session.achievement_progress. Both are saved with the
profile's stats (see account/integration.py), like seen_intro. Applying a
profile replaces them with that copy's, so the achievements follow the
player's choice (local or cloud) when the two copies differ.

The game reports what happened through a few small calls (launched, clear,
flight_ended, ...). check_state() turns the counters and what the session
already records (records, coins) into tiers, so it also unlocks for players
whose progress came before achievements existed; SceneManager runs it now
and then. Every new unlock plays the "achievement" sound, is saved, and
shows a popup (SceneManager.toasts).
"""

import re
from dataclasses import dataclass
from datetime import datetime, timezone

# Categories: order of the achievements page, and the icon drawn for each.
PROGRESS, SKILL, MECHANICS, CREATION, FAILURE = "progress", "skill", "mechanics", "creation", "failure"
CATEGORIES = (PROGRESS, SKILL, MECHANICS, CREATION, FAILURE)

TIERS = 4
ROMAN = ("I", "II", "III", "IV")
ALL = "all"                      # a threshold meaning "every one there is"

# Session.achievement_progress keys
LAUNCHES = "launches"
BOUNCES = "bounces"
TELEPORTS = "teleports"
ROCKS_DESTROYED = "rocks_destroyed"
COINS = "coins"
OUT_OF_BOUNDS = "out_of_bounds"
ONE_LIFE_CLEARS = "one_life_clears"
RANDOM_CLEARS = "random_clears"
RANDOM_CLEARS_NO_AI = "random_clears_no_ai"
BEST_CLEAR_TIME = "best_clear_time"     # float seconds, the lowest so far
FIRST_TRY_LEVELS = "first_try_levels"   # list of campaign level ids
COMMUNITY_CLEARED = "community_cleared"  # list of community level keys
ABILITIES_USED = "abilities_used"       # list of ability ids
CLEAN_CLEARS = "clean_clears"           # list of campaign level ids cleared without an answer

CHAIN_REACTION_ROCKS = 3        # Chain Reaction: rocks in one shockwave
PINBALL_BOUNCES = 5             # Pinball Wizard: bounces in one cleared flight
ONE_LINER_CHARS = 6             # One-Liner: Fx + Fy characters, spaces not counted
ONE_LINER_FROM_LEVEL = 3        # ... on campaign level 3 or later


@dataclass(frozen=True)
class Achievement:
    id: str
    name: str
    description: str            # single: the rule; tiered: the rule with {n} for the threshold
    category: str
    hidden: bool = False        # shown as "???" until (its first tier is) unlocked
    tiers: tuple = ()           # tiered only: four thresholds, ALL for "every one"
    all_text: str = ""          # tiered: the description when the threshold is ALL
    one_text: str = ""          # tiered: the description when the threshold is 1 (singular English)
    lower_is_better: bool = False   # tiered on a best time instead of a count

    @property
    def tiered(self):
        return bool(self.tiers)


A = Achievement
ACHIEVEMENTS = (
    # --- tiered ------------------------------------------------------------------
    A("frequent_flyer", "Frequent Flyer", "Launch {n} times", PROGRESS, tiers=(25, 100, 250, 500)),
    A("home_sweet_home", "Home Sweet Home", "Clear {n} campaign levels", PROGRESS,
      tiers=(2, 4, 6, ALL), all_text="Clear every campaign level"),
    A("beginners_luck", "Beginner's Luck", "Clear {n} campaign levels on the first launch", SKILL,
      tiers=(1, 3, 5, ALL), all_text="Clear every campaign level on the first launch",
      one_text="Clear a campaign level on the first launch"),
    A("not_today_gravity", "Not Today, Gravity", "Clear a level with one life left {n} times", SKILL,
      tiers=(1, 5, 10, 20), one_text="Clear a level with one life left"),
    A("faster_than_light", "Faster Than Light", "Clear a level in under {n} seconds of flight", SKILL,
      tiers=(5, 4, 3, 2), lower_is_better=True),
    A("roll_the_dice", "Roll the Dice", "Clear the random level {n} times", SKILL, tiers=(5, 15, 40, 100)),
    A("who_needs_robots", "Who Needs Robots?", "Clear the random level {n} times without the AI Solver",
      SKILL, tiers=(1, 5, 20, 50), one_text="Clear the random level without the AI Solver"),
    A("bounce_house", "Bounce House", "Bounce off rocks {n} times", MECHANICS, tiers=(25, 100, 250, 500)),
    A("hole_in_one", "Hole in One", "Fly through black holes {n} times", MECHANICS, tiers=(5, 15, 40, 100)),
    A("kaboom", "Kaboom!", "Blow up {n} rocks with shockwaves", MECHANICS, tiers=(10, 40, 100, 250)),
    A("pocket_change", "Pocket Change", "Collect {n} coins", MECHANICS, tiers=(10, 40, 100, 200)),
    A("power_trip", "Power Trip", "Use {n} different abilities", MECHANICS,
      tiers=(2, 4, 6, ALL), all_text="Use every ability"),
    A("space_tourist", "Space Tourist", "Clear {n} different community levels", CREATION,
      tiers=(1, 5, 15, 50), one_text="Clear a community level"),
    A("lost_in_space", "Lost in Space", "Fly out of bounds {n} times", FAILURE, hidden=True,
      tiers=(10, 50, 100, 200)),

    # --- single ------------------------------------------------------------------
    A("is_anyone_out_there", "Is Anyone Out There?", "Watch the intro story to the end", PROGRESS),
    A("look_ma_no_hints", "Look Ma, No Hints", "Clear every campaign level without peeking at an answer",
      SKILL),
    A("keep_it_constant", "Keep It Constant", "Clear a level with rocks without a single x or y", SKILL),
    A("fashionably_late", "Fashionably Late", "Run out of time, keep going, and still make it", SKILL),
    A("one_liner", "One-Liner", "Clear Level 3 or later with Fx and Fy in 6 characters or fewer", SKILL),
    A("pinball_wizard", "Pinball Wizard", "Bounce off rocks 5 times in one flight and still make it",
      MECHANICS),
    A("chain_reaction", "Chain Reaction", "Blow up 3 rocks with one shockwave", MECHANICS),
    A("thinking_outside_the_box", "Thinking Outside the Box",
      "Fly beyond the edge of the map and still make it", MECHANICS),
    A("not_a_scratch", "Not a Scratch", "Let a shield take a hit and still make it", MECHANICS),
    A("signal_sent", "Signal Sent", "Upload a community level", CREATION),
    A("houston", "Houston, We Have a Problem", "Lose every life in a level", FAILURE, hidden=True),
    A("divide_by_zero", "Divide by Zero", "Get flung by an infinite force", FAILURE, hidden=True),
)
del A
BY_ID = {a.id: a for a in ACHIEVEMENTS}

_TRIG = re.compile(r"\b(sin|cos|tan)\s*\(")
_XY = re.compile(r"(?<![a-z])[xy](?![a-z])")


# --- keys and state ------------------------------------------------------------------
def tier_key(achievement_id, tier):
    return f"{achievement_id}.{tier}"


def split_key(key):
    """(Achievement, tier) for an unlock key; tier is 0 for a single one. (None, 0) if unknown."""
    aid, _, tier = str(key).partition(".")
    achievement = BY_ID.get(aid)
    if achievement is None:
        return None, 0
    if not achievement.tiered:
        return (achievement, 0) if not tier else (None, 0)
    return (achievement, int(tier)) if tier in {str(t) for t in range(1, TIERS + 1)} else (None, 0)


def display_name(achievement, tier=0):
    return f"{achievement.name} {ROMAN[tier - 1]}" if tier else achievement.name


def unlocked(session):
    return getattr(session, "achievements", None) or {}


def is_unlocked(session, key):
    return key in unlocked(session)


def tier_reached(session, achievement):
    """Highest tier unlocked (0 = none) of a tiered achievement."""
    return max((t for t in range(1, TIERS + 1) if is_unlocked(session, tier_key(achievement.id, t))),
               default=0)


def progress(session):
    data = getattr(session, "achievement_progress", None)
    if not isinstance(data, dict):
        data = {}
        session.achievement_progress = data
    return data


def _number(session, key):
    try:
        return int(progress(session).get(key, 0) or 0)
    except (TypeError, ValueError):
        return 0


def _list(session, key):
    current = progress(session).get(key)
    return set(current) if isinstance(current, (list, tuple, set, frozenset)) else set()


def _add_to_list(session, key, value):
    """Add ``value`` to the progress list ``key``; returns the list as a set."""
    items = _list(session, key)
    items.add(value)
    # Sorted by its text: a list may hold numbers and names, which cannot be sorted together.
    progress(session)[key] = sorted(items, key=str)
    return items


def _bump(session, key, amount=1):
    progress(session)[key] = _number(session, key) + int(amount)


def unlock(manager, key, notify=True):
    """Unlock one key (a single id or "<id>.<tier>"). Returns True only the first time.

    A new unlock is saved; with ``notify`` it also plays the sound and
    queues the popup.
    """
    session = getattr(manager, "session", None)
    achievement, tier = split_key(key)
    if session is None or achievement is None or is_unlocked(session, key):
        return False
    if not isinstance(getattr(session, "achievements", None), dict):
        session.achievements = {}
    session.achievements[key] = datetime.now(timezone.utc).isoformat()
    if notify:
        toasts = getattr(manager, "toasts", None)
        if toasts is not None:
            toasts.push(achievement, tier)
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


# --- campaign facts --------------------------------------------------------------------
def campaign_level_ids():
    """Ids of the built-in fixed levels (random and custom levels excluded)."""
    from .data import LEVELS
    from .level_presets import is_dynamic_level
    return [level.id for level in LEVELS if not is_dynamic_level(level.id)]


def ability_count():
    try:
        from .abilities import ABILITIES
        return len(ABILITIES)
    except Exception:               # noqa: BLE001 - no abilities module: nothing to count
        return 0


def formula_uses_xy(*formulas):
    return any(_XY.search(f.lower()) for f in formulas)


def formula_uses_trig(*formulas):
    return any(_TRIG.search(f.lower()) for f in formulas)


def formula_chars(*formulas):
    return sum(len(re.sub(r"\s", "", f)) for f in formulas)


# --- tier values -----------------------------------------------------------------------
def _campaign_cleared(session):
    campaign = set(campaign_level_ids())
    records = getattr(session, "records", None) or {}
    return {int(k) for k in records if str(k).lstrip("-").isdigit() and int(k) in campaign}


VALUES = {
    "frequent_flyer": lambda s: _number(s, LAUNCHES),
    "home_sweet_home": lambda s: len(_campaign_cleared(s)),
    "beginners_luck": lambda s: len(_list(s, FIRST_TRY_LEVELS) & set(campaign_level_ids())),
    "not_today_gravity": lambda s: _number(s, ONE_LIFE_CLEARS),
    "faster_than_light": lambda s: progress(s).get(BEST_CLEAR_TIME),
    "roll_the_dice": lambda s: _number(s, RANDOM_CLEARS),
    "who_needs_robots": lambda s: _number(s, RANDOM_CLEARS_NO_AI),
    "bounce_house": lambda s: _number(s, BOUNCES),
    "hole_in_one": lambda s: _number(s, TELEPORTS),
    "kaboom": lambda s: _number(s, ROCKS_DESTROYED),
    # Coins paid before the counter existed are in the saved collected coins.
    "pocket_change": lambda s: max(_number(s, COINS), len(getattr(s, "collected_money_pickups", None) or ())),
    "power_trip": lambda s: len(_list(s, ABILITIES_USED)),
    "space_tourist": lambda s: len(_list(s, COMMUNITY_CLEARED)),
    "lost_in_space": lambda s: _number(s, OUT_OF_BOUNDS),
}
_ALL_OF = {
    "home_sweet_home": lambda: len(campaign_level_ids()),
    "beginners_luck": lambda: len(campaign_level_ids()),
    "power_trip": ability_count,
}


def thresholds(achievement):
    """The four thresholds as numbers (ALL resolved)."""
    return tuple(_ALL_OF[achievement.id]() if t == ALL else t for t in achievement.tiers)


def value(session, achievement):
    """The current number a tiered achievement is measured on (None = nothing yet)."""
    return VALUES[achievement.id](session)


def tier_met(achievement, current, threshold):
    if current is None or threshold is None:
        return False
    if achievement.lower_is_better:
        return current < threshold
    return threshold > 0 and current >= threshold


def describe(achievement, tier):
    """Text of tier ``tier`` (1-4) of a tiered achievement."""
    threshold = achievement.tiers[tier - 1]
    if threshold == ALL:
        return achievement.all_text
    if threshold == 1 and achievement.one_text:
        return achievement.one_text
    return achievement.description.format(n=threshold)


# --- what the game reports ---------------------------------------------------------------
def _in_tutorial(manager):
    """Tutorial screens (counts_for_progress = False) report nothing."""
    return getattr(getattr(manager, "scene", None), "counts_for_progress", True) is False


def _playing(manager):
    return getattr(manager, "session", None) is not None and not _in_tutorial(manager)


def launched(manager):
    if _playing(manager):
        _bump(manager.session, LAUNCHES)
        check_tiers(manager)


def count(manager, key, amount=1):
    """Add to a counter (bounces, black holes, rocks, coins) and check the tiers."""
    if _playing(manager) and amount > 0:
        _bump(manager.session, key, amount)
        check_tiers(manager)


def clear(manager, *, level_id, kind, attempts, lives_left, total_time, fx, fy,
          solution_used=False, solver_used=False, resumed=False, bounces=0,
          went_off_map=False, shield_saved=False, has_rocks=False, community_key=None):
    """A level was cleared. ``kind``: "campaign", "random", "daily", "community" or "custom".

    A daily clear counts only for the achievements of any kind of level.
    """
    if not _playing(manager):
        return
    session = manager.session
    if kind == "campaign":
        if attempts == 1:
            _add_to_list(session, FIRST_TRY_LEVELS, level_id)
        if not solution_used:
            _add_to_list(session, CLEAN_CLEARS, level_id)
        if level_id >= ONE_LINER_FROM_LEVEL and formula_chars(fx, fy) <= ONE_LINER_CHARS:
            unlock(manager, "one_liner")
    if kind == "random":
        _bump(session, RANDOM_CLEARS)
        if not solver_used:
            _bump(session, RANDOM_CLEARS_NO_AI)
    if kind == "community":
        _add_to_list(session, COMMUNITY_CLEARED, community_key if community_key is not None else level_id)
    if lives_left == 1:
        _bump(session, ONE_LIFE_CLEARS)
    best = progress(session).get(BEST_CLEAR_TIME)
    if isinstance(total_time, (int, float)) and (not isinstance(best, (int, float)) or total_time < best):
        progress(session)[BEST_CLEAR_TIME] = float(total_time)
    if has_rocks and not formula_uses_xy(fx, fy):
        unlock(manager, "keep_it_constant")
    if resumed:
        unlock(manager, "fashionably_late")
    if bounces >= PINBALL_BOUNCES:
        unlock(manager, "pinball_wizard")
    if went_off_map:
        unlock(manager, "thinking_outside_the_box")
    if shield_saved:
        unlock(manager, "not_a_scratch")
    check_state(manager)


def flight_ended(manager, outcome_name, lives_left):
    """A flight ended without a clear (``outcome_name``: an Outcome's name)."""
    if not _playing(manager):
        return
    if outcome_name == "OUT_OF_BOUNDS":
        _bump(manager.session, OUT_OF_BOUNDS)
        check_tiers(manager)
    if lives_left <= 0:
        unlock(manager, "houston")


def in_flight(manager, flight):
    """Checked every frame of a flight: flung by a point of infinite force."""
    if _playing(manager) and getattr(flight, "flings", 0) > 0:
        unlock(manager, "divide_by_zero")


def pickup_event(manager, event):
    if not _playing(manager):
        return
    if event.get("kind") == "shockwave":
        destroyed = len(event.get("destroyed") or ())
        if destroyed >= CHAIN_REACTION_ROCKS:
            unlock(manager, "chain_reaction")
        count(manager, ROCKS_DESTROYED, destroyed)


def ability_used(manager, ability_id):
    if _playing(manager):
        _add_to_list(manager.session, ABILITIES_USED, ability_id)
        check_tiers(manager)


def check_tiers(manager):
    """Unlock every tier whose threshold the current numbers meet."""
    session = manager.session
    for achievement in ACHIEVEMENTS:
        if not achievement.tiered:
            continue
        current = value(session, achievement)
        for tier, threshold in enumerate(thresholds(achievement), start=1):
            if tier_met(achievement, current, threshold):
                unlock(manager, tier_key(achievement.id, tier))


def check_state(manager):
    """Unlock what the saved progress already proves (safe to call any time)."""
    session = getattr(manager, "session", None)
    if session is None:
        return
    _migrate(session)
    check_tiers(manager)
    campaign = set(campaign_level_ids())
    if campaign and campaign <= _list(session, CLEAN_CLEARS):
        unlock(manager, "look_ma_no_hints")


def _migrate(session):
    """Unlocks from the first version (one id, no tiers) become tier I of the same achievement."""
    old = unlocked(session)
    for key in list(old):
        achievement = BY_ID.get(key)
        if achievement is not None and achievement.tiered:
            when = old.pop(key)
            old.setdefault(tier_key(key, 1), when)


# --- the page ------------------------------------------------------------------------------
def unlock_keys():
    """Every unlock key there is, in page order."""
    keys = []
    for a in ACHIEVEMENTS:
        keys.extend([tier_key(a.id, t) for t in range(1, TIERS + 1)] if a.tiered else [a.id])
    return keys


def counts(session):
    """(unlocked, total) unlock keys, every tier counted on its own."""
    keys = unlock_keys()
    return len([k for k in keys if is_unlocked(session, k)]), len(keys)
