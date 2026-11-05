"""Checkpoints: a run carries across the sections of a multi-section level (no window)."""

from types import SimpleNamespace

import pygame
import pytest

from vector_drift import config
from vector_drift.data import SectionSpec, multi_section_level
from vector_drift.physics import Outcome
from vector_drift.scenes import game as game_module
from vector_drift.scenes.base import SceneManager
from vector_drift.scenes.fail import FailScene
from vector_drift.scenes.game import ARRIVED, FLIGHT, PANNING, SETUP, GameScene
from vector_drift.scenes.win import WinScene

pytestmark = pytest.mark.usefixtures("pygame_display")

# Fx = 5, Fy = 0 flies every section: each start and target share one y.
# Section 2 is short (4 s) so TIMEOUT tests stay quick.
TWO = multi_section_level(
    id=90, name="Two Screens", ship_id="ship01", lives=3,
    sections=(
        SectionSpec(start=(-7.0, 0.0), target_center=(7.0, 0.0)),
        SectionSpec(start=(-7.0, 0.0), target_center=(7.0, 0.0), time_limit=4.0),
    ),
)
# Pans: (7, 0) - (-7, -3) = (14, 3), then (7, -3) - (-7, 2) = (14, -5).
THREE = multi_section_level(
    id=91, name="Three Screens", ship_id="ship01", lives=3,
    sections=(
        SectionSpec(start=(-7.0, 0.0), target_center=(7.0, 0.0)),
        SectionSpec(start=(-7.0, -3.0), target_center=(7.0, -3.0)),
        SectionSpec(start=(-7.0, 2.0), target_center=(7.0, 2.0)),
    ),
)
FAKES = {TWO.id: TWO, THREE.id: THREE}


class Audio:
    def __init__(self):
        self.played = []

    def play(self, name, *a, **k):
        self.played.append(name)

    def start_loop(self, *a, **k):
        pass

    def stop_loop(self, *a, **k):
        pass

    def toggle_mute(self):
        pass


@pytest.fixture(autouse=True)
def fake_levels(monkeypatch):
    real = game_module.get_level
    monkeypatch.setattr(game_module, "get_level",
                        lambda lid, seed=None: FAKES[lid] if lid in FAKES else real(lid, seed=seed))


def _scene(level=TWO, fx="5", fy="0", manager=None):
    manager = manager or SceneManager(Audio())
    manager.session.level_id = level.id
    manager.session.fx_text, manager.session.fy_text = fx, fy
    scene = GameScene(manager)
    manager.switch(scene)
    return scene


def _key(scene, key):
    scene.manager.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key, mod=0, unicode="", scancode=0))


def _set_field(scene, fx, fy):
    scene.editor.set_lines([fx, fy])
    scene._on_text_change(scene.editor)


def _fly(scene, fx=None, fy=None):
    """Launch with Enter and run until the flight ends."""
    if fx is not None:
        _set_field(scene, fx, fy)
    assert scene.state == SETUP and scene.valid
    _key(scene, pygame.K_RETURN)
    assert scene.state == FLIGHT
    for _ in range(2000):
        if scene.state != FLIGHT or scene.manager.scene is not scene:
            return
        scene.update(0.05)
    raise AssertionError("flight never ended")


def _finish_pan(scene):
    assert scene.state == PANNING
    steps = int(config.CHECKPOINT_PAN_DURATION / 0.05) + 2
    for _ in range(steps):
        scene.update(0.05)
    assert scene.state == SETUP


def _lose_a_life(scene):
    """Out of bounds to the left (not a TIMEOUT)."""
    _fly(scene, "-5", "0")
    assert scene.flight is None and scene.state == SETUP


# --- reaching a checkpoint -------------------------------------------------------
def test_reaching_a_checkpoint_is_not_a_win():
    scene = _scene()
    _fly(scene)

    assert scene.state == PANNING
    assert scene.section_index == 1
    assert scene.manager.scene is scene                 # no WinScene
    assert TWO.id not in scene.manager.session.records  # not a clear
    assert not isinstance(scene.manager.scene, WinScene)
    assert scene.dialogue is None                       # no win line
    assert "win" not in scene.manager.audio.played


def test_the_checkpoint_gives_a_life_and_plays_the_life_sound():
    scene = _scene()
    _lose_a_life(scene)
    assert scene.lives == 2

    _fly(scene, "5", "0")

    assert scene.lives == 3
    assert scene.manager.audio.played.count("life") == 1


def test_the_checkpoint_life_is_capped_at_the_level_lives():
    scene = _scene()
    assert scene.lives == TWO.lives

    _fly(scene)

    assert scene.lives == TWO.lives
    assert "life" in scene.manager.audio.played


def test_after_the_pan_the_next_section_is_set_up():
    scene = _scene(THREE)
    _set_field(scene, "5", "0")
    _fly(scene)
    _finish_pan(scene)

    assert scene.section_index == 1
    assert scene.launch_pos == THREE.sections[1].start
    assert scene.level.start == THREE.sections[1].start
    assert scene.level.target_center == THREE.sections[1].target_center
    assert scene.level.sections == ()
    assert scene.pan is None


def test_formulas_are_kept_and_editable_after_the_pan():
    scene = _scene(fx="5", fy="0")
    _fly(scene)
    _finish_pan(scene)

    assert scene.editor.lines == ["5", "0"]
    assert scene.editor.enabled and scene.run_button.enabled
    _set_field(scene, "4", "0")
    assert scene.editor.lines == ["4", "0"] and scene.valid


def test_flight_time_adds_up_across_sections():
    scene = _scene()
    _fly(scene)
    first = scene.total_time
    assert first > 0
    _finish_pan(scene)
    _fly(scene)
    assert scene.total_time > first


# --- no input during the pan -------------------------------------------------------
def test_esc_and_enter_do_nothing_during_the_pan():
    scene = _scene()
    _fly(scene)
    attempts = scene.attempts

    _key(scene, pygame.K_ESCAPE)
    _key(scene, pygame.K_RETURN)
    _key(scene, pygame.K_KP_ENTER)

    assert scene.pause_menu is None
    assert scene.state == PANNING and scene.attempts == attempts
    assert scene.flight is None


def test_buttons_do_nothing_during_the_pan():
    scene = _scene()
    _fly(scene)

    for button in (scene.run_button, scene.ai_button, scene.level_button):
        for kind in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
            scene.handle_event(pygame.event.Event(kind, button=1, pos=button.rect.center))

    assert scene.manager.scene is scene
    assert scene.state == PANNING
    assert scene.hint_popup is None and not scene.ai_popup


def test_the_pan_takes_the_configured_time():
    scene = _scene()
    _fly(scene)
    scene.update(config.CHECKPOINT_PAN_DURATION * 0.9)
    assert scene.state == PANNING
    scene.update(config.CHECKPOINT_PAN_DURATION * 0.2)
    assert scene.state == SETUP


# --- losing a life after the checkpoint -----------------------------------------------
def test_a_lost_life_in_section_two_relaunches_from_the_checkpoint():
    scene = _scene()
    _fly(scene)
    _finish_pan(scene)

    _lose_a_life(scene)

    assert scene.section_index == 1
    assert scene.launch_pos == TWO.sections[1].start
    assert scene.lives == TWO.lives - 1


def test_a_timeout_in_section_two_resumes_where_the_ship_stopped():
    scene = _scene()
    _fly(scene)
    _finish_pan(scene)

    _fly(scene, "0.5", "0")                    # 4 s limit: x = -7 + 0.25 * 16 = -3

    assert scene.section_index == 1
    assert scene.launch_pos[0] == pytest.approx(-3.0, abs=0.1)
    assert scene.launch_pos[1] == pytest.approx(0.0)


def test_out_of_lives_in_section_two_fails_and_retry_starts_over():
    scene = _scene(fx="-5", fy="0")
    _fly(scene, "5", "0")
    _finish_pan(scene)
    manager = scene.manager
    for _ in range(TWO.lives):
        if manager.scene is not scene:
            break
        _fly(scene, "-5", "0")

    assert isinstance(manager.scene, FailScene)
    _key(manager.scene, pygame.K_RETURN)        # Retry Level

    retry = manager.scene
    assert isinstance(retry, GameScene) and retry is not scene
    assert retry.section_index == 0
    assert retry.launch_pos == TWO.sections[0].start
    assert retry.lives == TWO.lives


def test_pause_menu_restart_starts_over_from_section_one():
    scene = _scene()
    _fly(scene)
    _finish_pan(scene)
    _lose_a_life(scene)

    scene._open_pause()
    scene.audio.play = lambda *a, **k: None
    # Same path as clicking Restart in the pause menu.
    scene.pause_menu.handle_event = lambda event: "restart"
    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_r, mod=0, unicode="r", scancode=0))

    restarted = scene.manager.scene
    assert isinstance(restarted, GameScene) and restarted is not scene
    assert restarted.section_index == 0
    assert restarted.launch_pos == TWO.sections[0].start
    assert restarted.lives == TWO.lives


# --- the last section --------------------------------------------------------------
def test_three_sections_play_through_to_the_win():
    scene = _scene(THREE)
    manager = scene.manager

    for index in range(2):
        assert scene.section_index == index
        _fly(scene)
        assert scene.state == PANNING
        _finish_pan(scene)
    assert scene.section_index == 2 and scene.launch_pos == THREE.sections[2].start

    _fly(scene)
    assert scene.state == ARRIVED
    assert manager.audio.played.count("win") == 1
    for _ in range(100):
        if manager.scene is not scene:
            break
        scene.update(0.05)
        if scene.dialogue is not None:
            scene.dialogue = None
            scene._close_dialogue()

    assert isinstance(manager.scene, WinScene)
    assert manager.session.records[THREE.id] == pytest.approx(scene.total_time)
    assert manager.session.stats["lives_left"] == THREE.lives


def test_multi_section_flights_are_not_stored_as_replays():
    scene = _scene()
    _fly(scene)
    _finish_pan(scene)
    _lose_a_life(scene)
    assert scene.manager.session.replays in (None, [])


def test_one_screen_levels_still_store_replays_and_win_directly():
    manager = SceneManager(Audio())
    manager.session.level_id = 1
    manager.session.fx_text, manager.session.fy_text = "5", "0"
    scene = GameScene(manager)
    manager.switch(scene)
    scene.dialogue = None
    _fly(scene)
    assert scene.state == ARRIVED and scene.section_index == 0
    assert len(manager.session.replays) == 1


def test_section_pan_progress_eases_from_zero_to_one():
    pan = game_module.SectionPan(shift=(14.0, 0.0), level=TWO, pickups=[], holes=[], arrival=(7.0, 0.0))
    assert pan.progress == 0.0
    pan.t = config.CHECKPOINT_PAN_DURATION / 2
    assert pan.progress == pytest.approx(0.5)
    pan.t = config.CHECKPOINT_PAN_DURATION * 0.1
    assert pan.progress < 0.1                   # slow start
    pan.t = config.CHECKPOINT_PAN_DURATION * 5
    assert pan.progress == 1.0
