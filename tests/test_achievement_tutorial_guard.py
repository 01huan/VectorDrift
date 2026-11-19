"""Achievements and tutorial screens: play there counts for nothing, but an
achievement unlocked directly (an experience, like watching the story) still works."""

from types import SimpleNamespace

import pytest

from vector_drift import achievements as ach
from vector_drift.scenes.base import SceneManager

pytestmark = pytest.mark.usefixtures("pygame_display")


def _manager(tutorial):
    audio = SimpleNamespace(play=lambda *a, **k: None, start_loop=lambda *a, **k: None,
                            stop_loop=lambda *a, **k: None)
    manager = SceneManager(audio)
    manager.scene = SimpleNamespace(counts_for_progress=not tutorial)
    return manager


def _report_everything(manager):
    flight = SimpleNamespace(bounces=9, teleports=1, flings=1, unbound=True)
    ach.launched(manager)
    ach.count(manager, ach.BOUNCES, 30)
    ach.clear(manager, level_id=1, kind="campaign", attempts=1, lives_left=1, total_time=1.0,
              fx="1", fy="0", resumed=True, bounces=9, went_off_map=True, shield_saved=True,
              has_rocks=True)
    ach.flight_ended(manager, "OUT_OF_BOUNDS", 0)
    ach.in_flight(manager, flight)
    ach.pickup_event(manager, {"kind": "shockwave", "destroyed": [(0, 0), (1, 0), (2, 0)]})
    ach.ability_used(manager, "boost")


def test_every_report_is_ignored_on_a_tutorial_screen():
    manager = _manager(tutorial=True)
    _report_everything(manager)
    assert manager.session.achievements == {}
    assert manager.session.achievement_progress == {}


def test_the_same_reports_count_outside_the_tutorial():
    manager = _manager(tutorial=False)
    _report_everything(manager)
    unlocked = set(manager.session.achievements)
    assert {"beginners_luck.1", "not_today_gravity.1", "faster_than_light.4", "bounce_house.1",
            "chain_reaction", "pinball_wizard", "not_a_scratch", "thinking_outside_the_box",
            "keep_it_constant", "fashionably_late", "houston", "divide_by_zero"} <= unlocked
    assert manager.session.achievement_progress


def test_unlock_itself_still_works_on_a_tutorial_screen():
    manager = _manager(tutorial=True)
    assert ach.unlock(manager, "is_anyone_out_there")
    assert "is_anyone_out_there" in manager.session.achievements
