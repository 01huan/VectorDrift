"""Achievements: tiered and single ones, unlock rules, saving, the popup, the page, game hooks."""

from types import SimpleNamespace

import pygame
import pytest

from vector_drift import achievements as ach
from vector_drift import config
from vector_drift.account.integration import (load_guest_profile_into_session, profiles_equal,
                                              save_guest_profile, session_to_profile)
from vector_drift.physics import Outcome
from vector_drift.scenes.base import SceneManager

pytestmark = pytest.mark.usefixtures("pygame_display")


class RecordingAudio:
    def __init__(self):
        self.played = []

    def play(self, name):
        self.played.append(name)

    def start_loop(self, name):
        pass

    def stop_loop(self, name):
        pass


def _manager():
    return SceneManager(RecordingAudio())


def _clear(manager, **overrides):
    args = dict(level_id=2, kind="campaign", attempts=3, lives_left=3, total_time=8.0,
                fx="x", fy="y", solution_used=False, solver_used=False, resumed=False)
    args.update(overrides)
    ach.clear(manager, **args)


def _unlocked(manager):
    return set(manager.session.achievements)


# --- the list --------------------------------------------------------------------
def test_14_tiered_and_12_single_with_four_tiers_each():
    tiered = [a for a in ach.ACHIEVEMENTS if a.tiered]
    single = [a for a in ach.ACHIEVEMENTS if not a.tiered]
    assert (len(tiered), len(single)) == (14, 12)
    assert len(ach.BY_ID) == 26
    assert all(len(a.tiers) == ach.TIERS == 4 for a in tiered)
    assert set(ach.VALUES) == {a.id for a in tiered}
    assert len(ach.unlock_keys()) == 14 * 4 + 12
    assert "fleet_commander" not in ach.BY_ID       # ships are no longer bought


def test_thresholds_rise_tier_by_tier():
    for a in ach.ACHIEVEMENTS:
        if not a.tiered:
            continue
        steps = ach.thresholds(a)
        assert list(steps) == (sorted(steps, reverse=True) if a.lower_is_better else sorted(steps))
        assert len(set(steps)) == 4, a.id


def test_only_failures_are_hidden():
    assert {a.id for a in ach.ACHIEVEMENTS if a.hidden} == {"houston", "divide_by_zero", "lost_in_space"}
    assert {a.category for a in ach.ACHIEVEMENTS} == set(ach.CATEGORIES)


def test_keys_and_names():
    assert ach.split_key("bounce_house.3") == (ach.BY_ID["bounce_house"], 3)
    assert ach.split_key("chain_reaction") == (ach.BY_ID["chain_reaction"], 0)
    assert ach.split_key("bounce_house") == (None, 0)          # a tiered one needs its tier
    assert ach.split_key("bounce_house.5") == (None, 0)
    assert ach.split_key("we_have_liftoff") == (None, 0)       # removed
    assert ach.display_name(ach.BY_ID["kaboom"], 4) == "Kaboom! IV"
    assert ach.describe(ach.BY_ID["home_sweet_home"], 4) == "Clear every campaign level"
    assert ach.describe(ach.BY_ID["bounce_house"], 2) == "Bounce off rocks 100 times"
    assert ach.describe(ach.BY_ID["space_tourist"], 1) == "Clear a community level"
    for a in ach.ACHIEVEMENTS:                      # no "1 times" / "1 levels" anywhere
        for tier in range(1, ach.TIERS + 1 if a.tiered else 1):
            text = ach.describe(a, tier)
            assert " 1 " not in f" {text} ", text


# --- unlocking -------------------------------------------------------------------
def test_unlock_once_plays_the_sound_and_queues_one_popup():
    manager = _manager()
    assert ach.unlock(manager, "chain_reaction")
    assert not ach.unlock(manager, "chain_reaction")
    assert not ach.unlock(manager, "no_such_thing")
    assert manager.audio.played.count("achievement") == 1
    queued = manager.toasts.waiting + [tuple(t[:2]) for t in manager.toasts.shown]
    assert queued == [(ach.BY_ID["chain_reaction"], 0)]


def test_a_counter_unlocks_each_tier_once_with_its_own_popup():
    manager = _manager()
    ach.count(manager, ach.BOUNCES, 24)
    assert _unlocked(manager) == set()
    ach.count(manager, ach.BOUNCES, 1)
    assert _unlocked(manager) == {"bounce_house.1"}
    ach.count(manager, ach.BOUNCES, 500)                # jumps straight past II and III
    assert {f"bounce_house.{t}" for t in (1, 2, 3, 4)} <= _unlocked(manager)
    assert manager.audio.played.count("achievement") == 4


def test_launches_count_for_frequent_flyer():
    manager = _manager()
    for _ in range(25):
        ach.launched(manager)
    assert "frequent_flyer.1" in _unlocked(manager)


def test_an_ordinary_clear_unlocks_nothing_special():
    manager = _manager()
    _clear(manager)
    assert _unlocked(manager) == set()


@pytest.mark.parametrize("overrides, expected", [
    (dict(attempts=1), "beginners_luck.1"),
    (dict(lives_left=1), "not_today_gravity.1"),
    (dict(total_time=4.5), "faster_than_light.1"),
    (dict(total_time=1.5), "faster_than_light.4"),
    (dict(fx="3", fy="-2", has_rocks=True), "keep_it_constant"),
    (dict(resumed=True), "fashionably_late"),
    (dict(bounces=5), "pinball_wizard"),
    (dict(went_off_map=True), "thinking_outside_the_box"),
    (dict(shield_saved=True), "not_a_scratch"),
    (dict(level_id=3, fx="3", fy="-y"), "one_liner"),
    (dict(kind="community", level_id=-3, community_key="abc"), "space_tourist.1"),
])
def test_clear_rules(overrides, expected):
    manager = _manager()
    _clear(manager, **overrides)
    assert expected in _unlocked(manager)


def test_clear_rules_that_should_not_fire():
    manager = _manager()
    _clear(manager, fx="3", fy="-2", has_rocks=False)            # no rocks: too easy
    _clear(manager, level_id=2, fx="3", fy="-y")                 # One-Liner starts at level 3
    _clear(manager, level_id=3, fx="3*x", fy="-2*y")             # 8 characters
    _clear(manager, bounces=4)
    _clear(manager, kind="custom", level_id=1001, community_key=1001)
    assert not {"keep_it_constant", "one_liner", "pinball_wizard", "space_tourist.1"} & _unlocked(manager)


def test_random_clears_with_and_without_the_ai_solver():
    manager = _manager()
    for _ in range(4):
        _clear(manager, kind="random", level_id=8, solver_used=True)
    assert "who_needs_robots.1" not in _unlocked(manager)
    _clear(manager, kind="random", level_id=8)
    assert {"roll_the_dice.1", "who_needs_robots.1"} <= _unlocked(manager)


def test_the_same_community_level_counts_once():
    manager = _manager()
    for _ in range(5):
        _clear(manager, kind="community", level_id=-3, community_key="same")
    assert ach.value(manager.session, ach.BY_ID["space_tourist"]) == 1


def test_formula_helpers():
    assert not ach.formula_uses_xy("exp(2) + max(1, 3)")
    assert ach.formula_uses_xy("2x + 1")
    assert ach.formula_chars("3 * x", " -y ") == 5


def test_every_campaign_level_and_every_clean_one():
    manager = _manager()
    ids = ach.campaign_level_ids()
    for lid in ids:
        manager.session.records[lid] = 5.0
        _clear(manager, level_id=lid, solution_used=(lid == ids[-1]))
    assert "home_sweet_home.4" in _unlocked(manager)
    assert "look_ma_no_hints" not in _unlocked(manager)
    _clear(manager, level_id=ids[-1])
    assert "look_ma_no_hints" in _unlocked(manager)


def test_first_try_counts_distinct_campaign_levels():
    manager = _manager()
    for _ in range(3):
        _clear(manager, level_id=1, attempts=1)
    assert ach.value(manager.session, ach.BY_ID["beginners_luck"]) == 1


def test_losses():
    manager = _manager()
    for _ in range(9):
        ach.flight_ended(manager, "OUT_OF_BOUNDS", lives_left=3)
    assert "lost_in_space.1" not in _unlocked(manager)
    ach.flight_ended(manager, "OUT_OF_BOUNDS", lives_left=3)
    assert "lost_in_space.1" in _unlocked(manager)
    ach.flight_ended(manager, "TIMEOUT", lives_left=0)
    assert "houston" in _unlocked(manager)


def test_flings_shockwaves_and_abilities():
    manager = _manager()
    ach.in_flight(manager, SimpleNamespace(flings=1))
    assert "divide_by_zero" in _unlocked(manager)
    ach.pickup_event(manager, {"kind": "shockwave", "destroyed": ("a", "b")})
    assert "chain_reaction" not in _unlocked(manager)
    ach.pickup_event(manager, {"kind": "shockwave", "destroyed": ("a", "b", "c")})
    assert "chain_reaction" in _unlocked(manager)
    assert manager.session.achievement_progress[ach.ROCKS_DESTROYED] == 5
    ach.ability_used(manager, "ability_boost")
    ach.ability_used(manager, "ability_boost")
    assert "power_trip.1" not in _unlocked(manager)
    ach.ability_used(manager, "ability_magnet")
    assert "power_trip.1" in _unlocked(manager)


def test_saved_coins_and_records_unlock_on_the_next_check():
    manager = _manager()
    manager.session.collected_money_pickups = {(1, (float(i), 0.0)) for i in range(12)}
    manager.session.records = {1: 4.0, 2: 6.0}
    from vector_drift.scenes.achievements_page import AchievementsScene
    manager.switch(AchievementsScene(manager))
    manager.update(0.01)                            # SceneManager checks right away
    assert {"pocket_change.1", "home_sweet_home.1"} <= _unlocked(manager)


def test_first_version_unlocks_become_tier_one_and_removed_ones_are_ignored():
    manager = _manager()
    manager.session.achievements = {"bounce_house": "2026-11-01T00:00:00+00:00",
                                    "we_have_liftoff": "2026-11-01T00:00:00+00:00",
                                    "fleet_commander": "2026-11-01T00:00:00+00:00",
                                    "kaboom": "2026-11-02T00:00:00+00:00"}
    ach.check_state(manager)
    unlocked = _unlocked(manager)
    assert {"bounce_house.1", "kaboom.1"} <= unlocked
    assert "bounce_house" not in unlocked
    assert manager.session.achievements["bounce_house.1"] == "2026-11-01T00:00:00+00:00"
    assert ach.counts(manager.session) == (2, len(ach.unlock_keys()))
    assert manager.audio.played.count("achievement") == 0     # no popups for old unlocks


# --- saving ----------------------------------------------------------------------
def test_achievements_survive_save_and_load():
    manager = _manager()
    ach.unlock(manager, "chain_reaction")
    ach.flight_ended(manager, "OUT_OF_BOUNDS", lives_left=2)
    ach.clear(manager, level_id=2, kind="campaign", attempts=2, lives_left=2, total_time=3.5,
              fx="x", fy="y")
    save_guest_profile(manager.session)

    fresh = _manager().session
    assert load_guest_profile_into_session(fresh)
    assert {"chain_reaction", "faster_than_light.2"} <= set(fresh.achievements)
    assert fresh.achievement_progress[ach.OUT_OF_BOUNDS] == 1
    assert fresh.achievement_progress[ach.BEST_CLEAR_TIME] == 3.5
    assert "achievements" not in fresh.stats


def test_a_loaded_profile_replaces_the_session_achievements():
    # The applied copy wins, like every other progress field: the player
    # chooses local or cloud when the two differ, and the achievements go
    # with that choice (they are not merged with the other side).
    manager = _manager()
    ach.unlock(manager, "chain_reaction")
    save_guest_profile(manager.session)

    fresh = _manager().session
    fresh.achievements = {"hole_in_one.1": "2026-01-01T00:00:00+00:00"}
    assert load_guest_profile_into_session(fresh)
    assert set(fresh.achievements) == {"chain_reaction"}


def test_achievements_alone_do_make_the_profiles_differ():
    a, b = _manager().session, _manager().session
    a.achievements = {"chain_reaction": "t"}
    assert not profiles_equal(session_to_profile(a, "u"), session_to_profile(b, "u"))


# --- popup and page --------------------------------------------------------------
def test_popups_slide_in_stack_and_leave():
    from vector_drift.scenes.achievement_ui import HOLD_S, MAX_SHOWN, SLIDE_S, ToastStack
    stack = ToastStack()
    for a in ach.ACHIEVEMENTS[:MAX_SHOWN + 1]:
        stack.push(a, 2 if a.tiered else 0)
    assert len(stack.shown) == MAX_SHOWN and len(stack.waiting) == 1
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    stack.update(SLIDE_S)
    stack.draw(surface)
    stack.update(HOLD_S + SLIDE_S + 0.01)
    assert len(stack.shown) == 1 and not stack.waiting


def test_tier_status_on_the_page():
    from vector_drift.scenes.achievements_page import tier_status
    manager = _manager()
    bounce = ach.BY_ID["bounce_house"]
    assert tier_status(manager.session, bounce) == (0, "Bounce off rocks 25 times", 0.0, "0 / 25")
    ach.count(manager, ach.BOUNCES, 50)
    reached, goal, fraction, number = tier_status(manager.session, bounce)
    assert (reached, goal, number) == (1, "Bounce off rocks 100 times", "50 / 100")
    assert fraction == pytest.approx(0.5)
    ach.count(manager, ach.BOUNCES, 1000)
    assert tier_status(manager.session, bounce)[:3] == (4, "Bounce off rocks 500 times", 1.0)
    fast = ach.BY_ID["faster_than_light"]
    assert tier_status(manager.session, fast)[3] == "best —"


def test_page_draws_and_back_goes_to_the_menu():
    from vector_drift.scenes.achievements_page import AchievementsScene
    from vector_drift.scenes.menu import MenuScene
    manager = _manager()
    ach.unlock(manager, "houston")
    ach.count(manager, ach.BOUNCES, 120)
    ach.flight_ended(manager, "OUT_OF_BOUNDS", lives_left=2)
    scene = AchievementsScene(manager)
    manager.switch(scene)
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    scene.draw(surface)
    last = scene.card_rect(len(ach.ACHIEVEMENTS) - 1)
    assert last.bottom <= config.WINDOW_H and last.right <= config.WINDOW_W
    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, mod=0, unicode="", scancode=0))
    assert isinstance(manager.scene, MenuScene)


def test_menu_opens_the_page():
    from vector_drift.scenes.achievements_page import AchievementsScene
    from vector_drift.scenes.menu import MenuScene
    manager = _manager()
    menu = MenuScene(manager)
    manager.switch(menu)
    pos = menu.achievements_button.rect.center
    menu.handle_event(pygame.event.Event(pygame.MOUSEMOTION, pos=pos, rel=(0, 0), buttons=(0, 0, 0)))
    menu.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=pos, button=1))
    menu.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=pos, button=1))
    assert isinstance(manager.scene, AchievementsScene)


# --- in the real game ------------------------------------------------------------
def _game(level_id):
    from vector_drift.scenes.game import GameScene
    manager = _manager()
    manager.session.seen_intro = True
    manager.session.level_id = level_id
    scene = GameScene(manager)
    manager.switch(scene)
    return manager, scene


def _fly(scene, fx, fy):
    from vector_drift.scenes.game_layout import FLIGHT
    scene.editor.set_lines([fx, fy])
    scene._on_text_change(scene.editor)
    scene._try_launch()
    for _ in range(3000):
        if scene.state != FLIGHT:
            return
        scene.update(1 / 60)


def test_clearing_level_1_first_try_in_the_game():
    from vector_drift.hints import get_hint
    manager, scene = _game(1)
    answer = get_hint(1).answers[0]
    _fly(scene, answer.fx, answer.fy)
    assert "beginners_luck.1" in _unlocked(manager)
    assert manager.session.achievement_progress[ach.LAUNCHES] == 1
    assert 1 in manager.session.achievement_progress[ach.FIRST_TRY_LEVELS]


def test_bounces_in_the_game_are_counted():
    manager, scene = _game(2)                       # one rock in the middle of the path
    _fly(scene, "3", "0")
    assert manager.session.achievement_progress.get(ach.BOUNCES, 0) >= 1


def test_losing_every_life_in_the_game():
    manager, scene = _game(2)
    for _ in range(scene.lives):
        if manager.scene is not scene:
            break
        scene.editor.set_lines(["0", "0"])
        scene._on_text_change(scene.editor)
        scene._try_launch()
        scene.flight.abort()
        scene._end_flight(Outcome.ABORTED)
    assert "houston" in _unlocked(manager)
