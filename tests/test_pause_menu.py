"""Esc in the level screen: closes the top popup first, otherwise opens the pause menu."""

from types import SimpleNamespace

import pygame
import pytest

from vector_drift.physics import Outcome
from vector_drift.scenes import game as game_module
from vector_drift.scenes.base import SceneManager
from vector_drift.scenes.game import ARRIVED, FLIGHT, SETUP, GameScene
from vector_drift.scenes.levels import LevelSelectScene
from vector_drift.scenes.menu import MenuScene
from vector_drift.scenes.win import WinScene
from vector_drift.story import all_seen_keys

pytestmark = pytest.mark.usefixtures("pygame_display")


def _manager():
    sounds = []
    audio = SimpleNamespace(play=lambda *a, **k: sounds.append(("play",) + a),
                            start_loop=lambda name: sounds.append(("start", name)),
                            stop_loop=lambda name: sounds.append(("stop", name)))
    manager = SceneManager(audio)
    manager.session.story_seen = all_seen_keys()     # no story dialogue in the way
    manager.sounds = sounds
    return manager


def _scene(level_id, manager=None, seed=None):
    manager = manager or _manager()
    manager.session.level_id = level_id
    manager.session.random_seed = seed
    scene = GameScene(manager)
    manager.switch(scene)
    return scene


def _key(scene, key, unicode=""):
    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key, mod=0, unicode=unicode,
                                          scancode=0))


def _click(scene, rect):
    pos = rect.center
    scene.handle_event(pygame.event.Event(pygame.MOUSEMOTION, pos=pos, rel=(0, 0), buttons=(0, 0, 0)))
    scene.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=pos, button=1))


def _launch(scene, fx="1", fy="0"):
    scene.editor.set_lines([fx, fy])
    scene._on_text_change(scene.editor)
    scene._try_launch()
    assert scene.state == FLIGHT


# --- Task 1: Esc closes the AI Solver popup ------------------------------------------

def test_esc_closes_the_ai_solver_popup():
    scene = _scene(8, seed=123)
    scene._on_ai_click()
    assert scene.ai_popup

    _key(scene, pygame.K_ESCAPE)
    assert not scene.ai_popup


def test_esc_closes_the_ai_solver_popup_during_flight_without_aborting():
    scene = _scene(8, seed=123)
    _launch(scene, "0.1", "0")
    lives = scene.lives
    scene._on_ai_click()

    _key(scene, pygame.K_ESCAPE)
    assert not scene.ai_popup
    assert scene.state == FLIGHT and scene.flight.running
    assert scene.lives == lives


# --- Task 2: the pause menu ----------------------------------------------------------

def _actions(scene):
    return [action for _button, action in scene.pause_menu.buttons()]


def _press(scene, action):
    """Click the pause-menu button for ``action``."""
    for button, name in scene.pause_menu.buttons():
        if name == action:
            _click(scene, button.rect)
            return
    raise AssertionError(f"no {action!r} button in {_actions(scene)}")


def _lose_a_life(scene):
    (sx, sy), (tx, ty) = scene.level.start, scene.level.target_center
    dx, dy = tx - sx, ty - sy
    norm = (dx * dx + dy * dy) ** 0.5
    _launch(scene, str(-50 * dx / norm), str(-50 * dy / norm))     # hard away from the target
    flight = scene.flight
    while scene.flight is flight and scene.state == FLIGHT:
        scene.update(1 / 60)
    if scene.dialogue is not None:                  # fixed levels comment on a lost life
        scene._close_dialogue()


@pytest.fixture
def solver_stops(monkeypatch):
    """A background solve that records when it is stopped."""
    stopped = []
    job = SimpleNamespace(running=True, cancel=lambda: None, error=None, result=None,
                          stop=lambda *a: stopped.append(True))
    monkeypatch.setattr(game_module, "run_solver_async", lambda *a, **k: job)
    return stopped


def test_esc_opens_and_closes_the_menu_in_setup():
    scene = _scene(1)
    _key(scene, pygame.K_ESCAPE)
    assert scene.pause_menu is not None
    _key(scene, pygame.K_ESCAPE)
    assert scene.pause_menu is None


def test_the_menu_blocks_typing_and_launching():
    scene = _scene(1)
    scene.editor.set_lines(["5", "0"])
    scene._on_text_change(scene.editor)
    _key(scene, pygame.K_ESCAPE)

    scene.handle_event(pygame.event.Event(pygame.TEXTINPUT, text="9"))
    _key(scene, pygame.K_BACKSPACE)
    _key(scene, pygame.K_RETURN)
    assert scene.editor.lines == ["5", "0"]
    assert scene.state == SETUP and scene.flight is None
    assert scene.pause_menu is not None


def test_pausing_a_flight_freezes_it_without_aborting():
    scene = _scene(1)
    _launch(scene, "0.5", "0")
    for _ in range(10):
        scene.update(1 / 60)
    lives = scene.lives

    _key(scene, pygame.K_ESCAPE)
    assert scene.pause_menu is not None
    assert scene.state == FLIGHT and scene.flight.running and scene.lives == lives
    frozen = (scene.flight.time, scene.flight.x, scene.flight.y, scene.flight.vx)
    for _ in range(120):
        scene.update(1 / 60)
    assert (scene.flight.time, scene.flight.x, scene.flight.y, scene.flight.vx) == frozen

    _press(scene, "resume")
    assert scene.pause_menu is None
    scene.update(1 / 60)
    assert scene.flight.time - frozen[0] == pytest.approx(1 / 60, abs=0.02)


def test_the_banner_countdown_pauses_too():
    scene = _scene(1)
    _lose_a_life(scene)
    assert scene.banner is not None
    left = scene.banner[2]
    _key(scene, pygame.K_ESCAPE)
    for _ in range(60):
        scene.update(1 / 60)
    assert scene.banner is not None and scene.banner[2] == left


def test_abort_flight_is_only_offered_during_a_flight():
    scene = _scene(1)
    _key(scene, pygame.K_ESCAPE)
    assert "abort" not in _actions(scene)
    _key(scene, pygame.K_ESCAPE)

    _launch(scene, "0.5", "0")
    lives = scene.lives
    flight = scene.flight
    _key(scene, pygame.K_ESCAPE)
    assert _actions(scene) == ["resume", "abort", "restart", "levels", "menu", "quit"]
    _press(scene, "abort")
    assert scene.pause_menu is None
    assert flight.outcome is Outcome.ABORTED
    assert scene.lives == lives - 1


@pytest.mark.parametrize("level_id, seed", [(2, None), (8, 4321)])
def test_restart_replays_the_level_with_full_lives_and_the_same_formulas(level_id, seed):
    manager = _manager()
    scene = _scene(level_id, manager, seed=seed)
    _lose_a_life(scene)
    assert scene.lives < scene.level.lives
    scene.editor.set_lines(["2", "y"])
    scene._on_text_change(scene.editor)

    _key(scene, pygame.K_ESCAPE)
    assert _actions(scene) == ["resume", "restart", "levels", "menu", "quit"]
    _press(scene, "restart")
    fresh = manager.scene
    assert isinstance(fresh, GameScene) and fresh is not scene
    assert fresh.level.id == level_id
    assert manager.session.random_seed == seed
    assert fresh.lives == fresh.level.lives
    assert fresh.editor.lines == ["2", "y"]
    assert fresh.pause_menu is None


@pytest.mark.parametrize("action, target", [("levels", LevelSelectScene), ("menu", MenuScene)])
def test_levels_and_main_menu_leave_and_stop_the_solver(action, target, solver_stops):
    manager = _manager()
    scene = _scene(8, manager, seed=99)
    scene.update(1 / 60)                            # starts the background solve
    _key(scene, pygame.K_ESCAPE)
    _press(scene, action)
    assert isinstance(manager.scene, target)
    assert solver_stops


def test_quit_asks_first_and_cancel_or_esc_go_back():
    manager = _manager()
    scene = _scene(1, manager)
    _key(scene, pygame.K_ESCAPE)

    _press(scene, "quit")
    assert scene.pause_menu.confirming_quit
    _click(scene, scene.pause_menu.cancel_button.rect)
    assert scene.pause_menu is not None and not scene.pause_menu.confirming_quit

    _press(scene, "quit")
    _key(scene, pygame.K_ESCAPE)
    assert scene.pause_menu is not None and not scene.pause_menu.confirming_quit
    assert manager.running

    _press(scene, "quit")
    _click(scene, scene.pause_menu.quit_button.rect)
    assert not manager.running


def test_enter_confirms_quit():
    manager = _manager()
    scene = _scene(1, manager)
    _key(scene, pygame.K_ESCAPE)
    _press(scene, "quit")
    _key(scene, pygame.K_RETURN)
    assert not manager.running


def test_esc_skips_the_story_dialogue_without_opening_the_menu():
    manager = _manager()
    manager.session.story_seen = set()
    scene = _scene(1, manager)
    assert scene.dialogue is not None

    _key(scene, pygame.K_ESCAPE)
    assert scene.dialogue is None
    assert scene.pause_menu is None


def test_esc_closes_the_hint_without_opening_the_menu():
    scene = _scene(1)
    scene._open_hint()
    assert scene.hint_popup is not None

    _key(scene, pygame.K_ESCAPE)
    assert scene.hint_popup is None
    assert scene.pause_menu is None


def test_esc_in_the_hint_confirmation_only_cancels_it():
    scene = _scene(1)
    scene._open_hint()
    scene.hint_popup.confirming = True

    _key(scene, pygame.K_ESCAPE)
    assert scene.hint_popup is not None and not scene.hint_popup.confirming
    assert scene.pause_menu is None


def test_esc_does_nothing_while_arriving():
    manager = _manager()
    scene = _scene(1, manager)
    _launch(scene, "5", "0")
    while scene.state == FLIGHT:
        scene.update(1 / 60)
    assert scene.state == ARRIVED

    _key(scene, pygame.K_ESCAPE)
    assert scene.pause_menu is None
    for _ in range(600):
        if manager.scene is not scene:
            break
        scene.update(1 / 60)
    assert isinstance(manager.scene, WinScene)


def test_the_thruster_sound_stops_while_paused_and_resumes():
    manager = _manager()
    scene = _scene(1, manager)
    _launch(scene, "0.5", "0")
    manager.sounds.clear()

    _key(scene, pygame.K_ESCAPE)
    assert ("stop", "thruster_loop") in manager.sounds
    manager.sounds.clear()
    _key(scene, pygame.K_ESCAPE)
    assert ("start", "thruster_loop") in manager.sounds


def test_leaving_the_level_mid_flight_stops_the_thruster_sound():
    manager = _manager()
    scene = _scene(1, manager)
    _launch(scene, "0.5", "0")
    manager.sounds.clear()

    manager.switch(MenuScene(manager))
    assert ("stop", "thruster_loop") in manager.sounds
