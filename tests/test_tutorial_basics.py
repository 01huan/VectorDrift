"""Basics: the four tutorial steps on the real game screen and engine."""

from types import SimpleNamespace

import pygame
import pytest

from vector_drift import config
from vector_drift.physics import Outcome
from vector_drift.scenes.base import SceneManager
from vector_drift.scenes.game_layout import ARRIVED, FLIGHT, SETUP
from vector_drift.scenes.levels import LevelSelectScene
from vector_drift.scenes.tutorial_basics import HOLD, BasicsScene

pytestmark = pytest.mark.usefixtures("pygame_display")


def _manager():
    audio = SimpleNamespace(play=lambda *a, **k: None, start_loop=lambda *a, **k: None,
                            stop_loop=lambda *a, **k: None, toggle_mute=lambda: None)
    mgr = SceneManager(audio)
    mgr.screen = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    return mgr


def _open(index=0, mgr=None):
    mgr = mgr or _manager()
    scene = BasicsScene(mgr, index)
    mgr.switch(scene)
    return mgr, scene


def _type(scene, fx, fy):
    scene.editor.set_lines([fx, fy])
    scene._on_text_change(scene.editor)


def _run(scene, until, limit=40.0, dt=1 / 30):
    t = 0.0
    while not until() and t < limit:
        scene.update(dt)
        t += dt
    assert until(), f"timed out in state {scene.state}"


def _draw(scene):
    scene.draw(pygame.Surface((config.WINDOW_W, config.WINDOW_H)))


# --- step 1: Fly home ---------------------------------------------------------------------
def test_step1_starts_empty_with_grey_placeholders():
    _, scene = _open(0)
    assert scene.editor.lines == ["", ""]
    assert scene.editor.placeholders == ("5", "0")
    assert scene.counter_text == "1 / 4"
    _draw(scene)


def test_step1_marks_the_play_button_until_it_is_ready_to_launch(monkeypatch):
    from vector_drift.scenes import tutorial_basics as tb
    _, scene = _open(0)
    drawn, pointers = [], []
    real = tb.draw_text
    monkeypatch.setattr(tb, "draw_text",
                        lambda s, text, *a, **k: drawn.append(text) or real(s, text, *a, **k))
    monkeypatch.setattr(tb, "draw_pointer", lambda *a, **k: pointers.append(a))
    _draw(scene)
    assert "Play" in drawn and not pointers         # named, but not pointing at it yet
    _type(scene, "5", "0")
    _draw(scene)
    assert pointers                                   # ready: an arrow points at Play


def test_step1_play_is_off_while_a_line_is_empty():
    _, scene = _open(0)
    assert not scene.run_button.enabled
    scene._try_launch()
    assert scene.state == SETUP and scene.flight is None
    _type(scene, "5", "")
    assert not scene.run_button.enabled
    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN, mod=0,
                                          unicode="\r", scancode=0))
    assert scene.flight is None


def test_step1_fx5_fy0_reaches_the_planet():
    _, scene = _open(0)
    _type(scene, "5", "0")
    assert scene.run_button.enabled
    scene._try_launch()
    assert scene.state == FLIGHT
    _run(scene, lambda: scene.state == ARRIVED)
    assert scene.flight.outcome is Outcome.REACHED
    assert scene.flight.time == pytest.approx(2.3, abs=0.05)
    assert scene.done and scene.caption[0] == "Home! Reach the planet to clear a level."
    scene.update(5.0)                       # no Win screen follows
    assert scene.manager.scene is scene and scene.can_next
    _draw(scene)


def test_step1_a_miss_just_goes_back_without_lives():
    _, scene = _open(0)
    lives = scene.lives
    _type(scene, "0", "5")
    scene._try_launch()
    _run(scene, lambda: scene.state == SETUP)
    assert scene.lives == lives
    assert scene.launch_pos == scene.level.start
    assert "life" not in scene.banner[1] and "lives" not in scene.banner[1]


def test_step1_a_time_up_flies_on_from_where_it_stopped():
    _, scene = _open(0)
    _type(scene, "0.1", "0")
    scene._try_launch()
    _run(scene, lambda: scene.state == SETUP)
    assert scene.launch_pos[0] > scene.level.start[0]


def test_step1_next_opens_step2():
    mgr, scene = _open(0)
    _type(scene, "5", "0")
    scene._try_launch()
    _run(scene, lambda: scene.done)
    scene.advance()
    assert isinstance(mgr.scene, BasicsScene) and mgr.scene.index == 1


# --- step 2: Time's up ----------------------------------------------------------------------
def test_step2_is_a_read_only_demo():
    _, scene = _open(1)
    assert scene.editor.lines == ["1", "0"]
    assert not scene.editor.enabled and not scene.run_button.enabled
    scene.handle_event(pygame.event.Event(pygame.TEXTINPUT, text="9"))
    assert scene.editor.lines == ["1", "0"]


def test_step2_times_out_then_flies_on_and_reaches():
    mgr, scene = _open(1)
    _run(scene, lambda: scene.state == HOLD)
    assert scene.pending is Outcome.TIMEOUT
    assert scene.flight.time == pytest.approx(4.0)
    assert scene.flight.x == pytest.approx(1.02, abs=0.01)
    assert scene.caption[1] == "ship" and scene.caption[0].startswith("Time's up.")
    _draw(scene)
    scene.advance()
    assert scene.state == FLIGHT
    assert scene.flight.trail[0][0] == pytest.approx(1.02, abs=0.01)    # from where it stopped
    _run(scene, lambda: scene.state == HOLD)
    assert scene.pending is Outcome.REACHED
    assert scene.flight.time == pytest.approx(3.1, abs=0.05)
    assert scene.caption[0] == "It flew on from where it stopped."
    scene.advance()
    assert mgr.scene.index == 2


# --- step 3: Out of bounds -------------------------------------------------------------------
def test_step3_goes_out_of_bounds_and_back_to_start():
    mgr, scene = _open(2)
    assert scene.editor.lines == ["0", "5"]
    _run(scene, lambda: scene.state == HOLD)
    assert scene.pending is Outcome.OUT_OF_BOUNDS
    assert scene.flight.time == pytest.approx(1.73, abs=0.02)
    assert scene.flight.y > config.WORLD_HALF_H            # stopped on the frame it left
    assert scene.caption[0] == "Out of bounds. The ship left the map."
    scene.advance()
    assert scene.state == SETUP and scene.flight is None
    assert scene.launch_pos == scene.level.start
    assert scene.caption[1] == "start"
    _draw(scene)
    scene.advance()
    assert mgr.scene.index == 3


# --- step 4: Help ---------------------------------------------------------------------------
def test_step4_marks_the_hint_button_and_starts_playing():
    mgr, scene = _open(3)
    assert scene.caption[1] == "hint"
    _draw(scene)
    assert not scene.ai_button.enabled                     # marked, not usable
    pos = scene.card_button.rect.center
    scene.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=pos))
    scene.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=pos))
    assert isinstance(mgr.scene, LevelSelectScene)


# --- leaving and side effects ------------------------------------------------------------------
@pytest.mark.parametrize("index", [0, 1, 2, 3])
def test_esc_leaves_to_level_select_and_gives_the_session_back(index):
    mgr = _manager()
    mgr.session.fx_text, mgr.session.fy_text = "x", "y"
    mgr.session.level_id = 4
    _, scene = _open(index, mgr)
    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, mod=0,
                                          unicode="", scancode=0))
    assert isinstance(mgr.scene, LevelSelectScene)
    assert (mgr.session.fx_text, mgr.session.fy_text, mgr.session.level_id) == ("x", "y", 4)


def test_basics_changes_no_coins_progress_records_or_replays(monkeypatch):
    from vector_drift.account import integration
    saves = []
    monkeypatch.setattr(integration, "save_progress", lambda *a, **k: saves.append(a))
    mgr = _manager()
    session = mgr.session
    money, records, replays = session.money, dict(session.records), list(session.replays or [])
    unlocked, counters = dict(session.achievements), dict(session.achievement_progress)
    _, scene = _open(0, mgr)
    _type(scene, "0", "5")
    scene._try_launch()
    _run(scene, lambda: scene.state == SETUP)
    _type(scene, "5", "0")
    scene._try_launch()
    _run(scene, lambda: scene.done)
    for index in (1, 2):
        scene.advance()
        scene = mgr.scene
        _run(scene, lambda: scene.state == HOLD)
        scene.advance()
        _run(scene, lambda: scene.state in (HOLD, SETUP))
    assert session.money == money and session.records == records
    assert list(session.replays or []) == replays
    assert saves == []
    assert session.achievements == unlocked and session.achievement_progress == counters


def test_basics_hides_lives_and_assist_buttons():
    _, scene = _open(0)
    assert not scene.show_lives and not scene.show_assists and not scene.show_level_row
    pos = scene.ai_button.rect.center
    scene.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=pos))
    scene.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=pos))
    assert scene.hint_popup is None and not scene.ai_popup


def test_basics_keeps_its_buttons_hidden_and_shows_no_ability_slots():
    _, scene = _open(0)
    assert not scene.show_abilities                     # abilities do nothing in the tutorial
    assert not hasattr(scene, "inventory_button")
    assert not hasattr(scene, "prev_ship") and not hasattr(scene, "next_ship")
    hidden = scene._hidden_buttons()
    assert {scene.level_button, scene.lab_button, scene.ai_button} == set(hidden)
    for button in hidden:
        pos = button.rect.center
        scene.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=pos))
    assert scene.manager.scene is scene                 # level button did not leave
    assert not scene.lab_popup and scene.hint_popup is None and not scene.ai_popup
    assert scene._hovered_ability() is None
    _draw(scene)
