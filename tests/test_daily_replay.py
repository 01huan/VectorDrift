"""Daily challenge clears in the achievements, and daily launches in the replays."""

from datetime import date
from types import SimpleNamespace

import pygame
import pytest

from vector_drift import achievements, config, daily_level
from vector_drift.daily_level import daily_map, replay_daily_day
from vector_drift.replay import ReplayRecord, normalize_records
from vector_drift.scenes.base import SceneManager
from vector_drift.scenes.game import GameScene
from vector_drift.scenes.replay import ReplayScene
from vector_drift.scenes.win import WinScene

pytestmark = pytest.mark.usefixtures("pygame_display")

DAY = date(2026, 11, 19)


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    monkeypatch.setattr(daily_level, "daily_today", lambda now=None: DAY)


def _manager():
    audio = SimpleNamespace(play=lambda *a, **k: None, start_loop=lambda *a, **k: None,
                            stop_loop=lambda *a, **k: None)
    return SceneManager(audio)


def _daily(manager):
    manager.session.level_id = config.DAILY_LEVEL_ID
    manager.session.daily_day = DAY
    manager.session.random_seed = None
    scene = GameScene(manager)
    manager.switch(scene)
    return scene


def _win(scene):
    answer = daily_map(DAY)
    scene.editor.set_lines([answer.fx, answer.fy])
    scene._on_text_change(scene.editor)
    scene._try_launch()
    for _ in range(60 * 25):
        if isinstance(scene.manager.scene, WinScene):
            break
        scene.update(1 / 60)
    assert isinstance(scene.manager.scene, WinScene)


# --- achievements --------------------------------------------------------------------

def test_a_daily_clear_reports_kind_daily(monkeypatch):
    calls = []
    monkeypatch.setattr(achievements, "clear", lambda manager, **kw: calls.append(kw))
    manager = _manager()
    scene = _daily(manager)

    _win(scene)

    (call,) = calls
    assert call["kind"] == "daily"
    assert call["level_id"] == config.DAILY_LEVEL_ID
    assert call["has_rocks"] is True
    assert call["attempts"] == 1 and call["lives_left"] == config.DAILY_LIVES
    assert call["solution_used"] is False and call["solver_used"] is False
    assert {"bounces", "went_off_map", "shield_saved", "resumed", "total_time", "fx", "fy",
            "community_key"} <= set(call)


def test_a_daily_clear_counts_for_general_achievements_only():
    manager = _manager()
    scene = _daily(manager)
    scene.lives = 1                  # cleared on the last life

    _win(scene)

    progress = achievements.progress(manager.session)
    assert progress.get(achievements.ONE_LIFE_CLEARS) == 1
    assert isinstance(progress.get(achievements.BEST_CLEAR_TIME), float)
    assert config.DAILY_LEVEL_ID not in (progress.get(achievements.FIRST_TRY_LEVELS) or [])
    assert config.DAILY_LEVEL_ID not in (progress.get(achievements.CLEAN_CLEARS) or [])
    assert not progress.get(achievements.RANDOM_CLEARS)


# --- replays --------------------------------------------------------------------------

def _played_replays():
    manager = _manager()
    _win(_daily(manager))
    return manager, manager.session.replays


def test_a_daily_launch_keeps_its_day_and_generator_version():
    _, replays = _played_replays()

    (rec,) = replays
    assert rec["level_id"] == config.DAILY_LEVEL_ID
    assert rec["daily_day"] == "2026-11-19"
    assert rec["daily_version"] == config.DAILY_GENERATOR_VERSION
    assert ReplayRecord.from_dict(rec).to_dict() == rec
    assert replay_daily_day(rec) == DAY


def test_other_replays_carry_no_daily_fields():
    rec = ReplayRecord(level_id=1).to_dict()
    assert "daily_day" not in rec and "daily_version" not in rec
    assert replay_daily_day(rec) is None


def test_a_daily_replay_rebuilds_the_day_s_map():
    manager, replays = _played_replays()
    scene = ReplayScene(manager)

    assert scene.records == replays
    assert scene._level == daily_map(DAY).level
    assert scene._level_label(replays[0]) == "Daily 2026-11-19"
    scene.draw(pygame.Surface((config.WINDOW_W, config.WINDOW_H)))


@pytest.mark.parametrize("change", [
    {"daily_version": config.DAILY_GENERATOR_VERSION + 1},
    {"daily_version": None},
    {"daily_day": "2026-02-30"},
    {"daily_day": None},
])
def test_a_daily_replay_that_cannot_be_rebuilt_is_not_listed(change):
    manager, replays = _played_replays()
    broken = dict(replays[0], **change)
    fixed_level = dict(ReplayRecord(level_id=1, created_at=1.0).to_dict())
    manager.session.replays = normalize_records([broken, fixed_level])

    scene = ReplayScene(manager)

    assert [r["level_id"] for r in scene.records] == [1]
    scene.draw(pygame.Surface((config.WINDOW_W, config.WINDOW_H)))
