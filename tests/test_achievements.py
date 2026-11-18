"""Achievements: the list, unlock rules, saving, the popup, the page and game hooks."""

from types import SimpleNamespace

import pygame
import pytest

from vector_drift import achievements as ach
from vector_drift import config
from vector_drift.account.integration import (load_guest_profile_into_session, profiles_equal,
                                              save_guest_profile, session_to_profile)
from vector_drift.data import SHIPS
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
def test_there_are_26_with_unique_ids_and_only_failures_hidden():
    # Fleet Commander ("Own all six ships") is gone: ships are no longer bought.
    assert len(ach.ACHIEVEMENTS) == 26
    assert len(ach.BY_ID) == 26
    assert "fleet_commander" not in ach.BY_ID
    assert {a.id for a in ach.ACHIEVEMENTS if a.hidden} == {"houston", "divide_by_zero", "lost_in_space"}
    assert {a.category for a in ach.ACHIEVEMENTS} == set(ach.CATEGORIES)


# --- unlocking -------------------------------------------------------------------
def test_unlock_once_plays_the_sound_and_queues_one_popup():
    manager = _manager()
    assert ach.unlock(manager, "kaboom")
    assert not ach.unlock(manager, "kaboom")
    assert manager.audio.played.count("achievement") == 1
    assert [a.id for a in manager.toasts.waiting + [t[0] for t in manager.toasts.shown]] == ["kaboom"]


def test_an_ordinary_clear_unlocks_nothing_special():
    manager = _manager()
    _clear(manager)
    assert _unlocked(manager) == set()


@pytest.mark.parametrize("overrides, expected", [
    (dict(level_id=1), "we_have_liftoff"),
    (dict(attempts=1), "beginners_luck"),
    (dict(lives_left=1), "not_today_gravity"),
    (dict(fx="3", fy="-2"), "keep_it_constant"),
    (dict(fx="sin(x)", fy="0"), "sine_of_the_times"),
    (dict(total_time=2.5), "faster_than_light"),
    (dict(resumed=True), "fashionably_late"),
    (dict(kind="random", level_id=8), "who_needs_robots"),
    (dict(kind="community", level_id=-3), "space_tourist"),
])
def test_clear_rules(overrides, expected):
    manager = _manager()
    _clear(manager, **overrides)
    assert expected in _unlocked(manager)


def test_the_ai_solver_or_an_editor_level_does_not_count():
    manager = _manager()
    _clear(manager, kind="random", level_id=8, solver_used=True)
    _clear(manager, kind="custom", level_id=1001)
    assert not {"who_needs_robots", "space_tourist"} & _unlocked(manager)


def test_xy_detection_ignores_function_names():
    assert not ach.formula_uses_xy("exp(2) + max(1, 3)")
    assert ach.formula_uses_xy("2x + 1")
    assert ach.formula_uses_trig("2*cos (y)")
    assert not ach.formula_uses_trig("cosh(1)")


def test_every_campaign_level_and_every_clean_one():
    manager = _manager()
    ids = ach.campaign_level_ids()
    for lid in ids:
        manager.session.records[lid] = 5.0
        _clear(manager, level_id=lid, solution_used=(lid == ids[-1]))
    assert "home_sweet_home" in _unlocked(manager)
    assert "look_ma_no_hints" not in _unlocked(manager)
    _clear(manager, level_id=ids[-1])
    assert "look_ma_no_hints" in _unlocked(manager)


def test_losses():
    manager = _manager()
    for _ in range(ach.OUT_OF_BOUNDS_TOTAL - 1):
        ach.flight_ended(manager, "OUT_OF_BOUNDS", lives_left=3)
    assert "lost_in_space" not in _unlocked(manager)
    ach.flight_ended(manager, "OUT_OF_BOUNDS", lives_left=3)
    assert "lost_in_space" in _unlocked(manager)
    ach.flight_ended(manager, "TIMEOUT", lives_left=0)
    assert "houston" in _unlocked(manager)


def test_in_flight_checks():
    manager = _manager()
    ach.in_flight(manager, SimpleNamespace(bounces=4, teleports=0, flings=0, unbound=False))
    assert _unlocked(manager) == set()
    ach.in_flight(manager, SimpleNamespace(bounces=5, teleports=1, flings=1, unbound=True), off_map=True)
    assert {"bounce_house", "hole_in_one", "divide_by_zero", "thinking_outside_the_box"} <= _unlocked(manager)


def test_pickups_and_abilities():
    manager = _manager()
    ach.pickup_event(manager, {"kind": "shockwave", "destroyed": ()})
    assert "kaboom" not in _unlocked(manager)
    ach.pickup_event(manager, {"kind": "shockwave", "destroyed": ("rock",)})
    ach.pickup_event(manager, {"kind": "shield_used"})
    assert {"kaboom", "not_a_scratch"} <= _unlocked(manager)
    for ability in ach.ABILITIES[:-1]:
        ach.ability_used(manager, ability)
    assert "power_trip" not in _unlocked(manager)
    ach.ability_used(manager, ach.ABILITIES[-1])
    assert "power_trip" in _unlocked(manager)


def test_saved_progress_unlocks_on_the_next_check():
    manager = _manager()
    manager.session.owned_ships = set(SHIPS)
    manager.session.collected_money_pickups = set(ach.campaign_coin_keys())
    manager.session.records = {1: 4.0}
    from vector_drift.scenes.achievements_page import AchievementsScene
    manager.switch(AchievementsScene(manager))
    manager.update(0.01)                            # SceneManager checks right away
    assert {"pocket_change", "we_have_liftoff"} <= _unlocked(manager)
    assert "fleet_commander" not in _unlocked(manager)


def test_an_old_save_with_fleet_commander_still_loads_and_counts():
    manager = _manager()
    manager.session.achievements = {"fleet_commander": "2026-11-01T00:00:00+00:00"}
    manager.session.owned_ships = {"ship01", "ship02", "ship03"}
    assert ach.counts(manager.session) == (0, len(ach.ACHIEVEMENTS))
    assert not ach.unlock(manager, "fleet_commander")
    from vector_drift.scenes.achievements_page import AchievementsScene
    manager.switch(AchievementsScene(manager))
    manager.update(0.01)
    manager.draw(pygame.Surface((config.WINDOW_W, config.WINDOW_H)))


# --- saving ----------------------------------------------------------------------
def test_achievements_survive_save_and_load():
    manager = _manager()
    ach.unlock(manager, "kaboom")
    ach.flight_ended(manager, "OUT_OF_BOUNDS", lives_left=2)
    save_guest_profile(manager.session)

    fresh = _manager().session
    assert load_guest_profile_into_session(fresh)
    assert set(fresh.achievements) == {"kaboom"}
    assert fresh.achievement_progress[ach.OUT_OF_BOUNDS] == 1
    assert "achievements" not in fresh.stats


def test_a_loaded_profile_replaces_the_session_achievements():
    # The applied copy wins, like every other progress field: the player
    # chooses local or cloud when the two differ, and the achievements go
    # with that choice (they are not merged with the other side).
    manager = _manager()
    ach.unlock(manager, "kaboom")
    save_guest_profile(manager.session)

    fresh = _manager().session
    fresh.achievements = {"hole_in_one": "2026-01-01T00:00:00+00:00"}
    assert load_guest_profile_into_session(fresh)
    assert set(fresh.achievements) == {"kaboom"}


def test_achievements_alone_do_make_the_profiles_differ():
    # The achievements are progress like the rest: they are not merged
    # between the two copies, so a difference in them is a difference the
    # player is asked about ("Use Local" / "Use Cloud").
    a, b = _manager().session, _manager().session
    a.achievements = {"kaboom": "t"}
    assert not profiles_equal(session_to_profile(a, "u"), session_to_profile(b, "u"))


# --- popup and page --------------------------------------------------------------
def test_popups_slide_in_stack_and_leave():
    from vector_drift.scenes.achievement_ui import HOLD_S, MAX_SHOWN, SLIDE_S, ToastStack
    stack = ToastStack()
    for a in ach.ACHIEVEMENTS[:MAX_SHOWN + 1]:
        stack.push(a)
    assert len(stack.shown) == MAX_SHOWN and len(stack.waiting) == 1
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    stack.update(SLIDE_S)
    stack.draw(surface)
    stack.update(HOLD_S + SLIDE_S + 0.01)
    assert len(stack.shown) == 1 and not stack.waiting


def test_page_draws_and_back_goes_to_the_menu():
    from vector_drift.scenes.achievements_page import AchievementsScene
    from vector_drift.scenes.menu import MenuScene
    manager = _manager()
    ach.unlock(manager, "houston")
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
    assert {"we_have_liftoff", "beginners_luck"} <= _unlocked(manager)


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
