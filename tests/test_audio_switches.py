"""Pause menu Music / Sound switches: two independent on-off settings."""

from types import SimpleNamespace

import pygame
import pytest

from vector_drift import audio
from vector_drift.scenes.base import SceneManager
from vector_drift.scenes.game import FLIGHT, GameScene


# --- SoundBank -------------------------------------------------------------------------

class _Sound:
    def __init__(self):
        self.plays = 0

    def play(self, loops=0):
        self.plays += 1
        return _Channel() if loops else None


class _Channel:
    volume = None

    def set_volume(self, v):
        self.volume = v

    def stop(self):
        pass


@pytest.fixture
def bank(monkeypatch):
    volumes = []
    monkeypatch.setattr(pygame.mixer.music, "set_volume", volumes.append)
    b = audio.SoundBank.__new__(audio.SoundBank)
    b.sounds = {"click": _Sound(), "thruster_loop": _Sound()}
    b.music_paths = {}
    b.muted = False
    b.enabled = True
    b._loop_channels = {}
    b._fade = 1.0
    b.music = "level"
    b._next_music = None
    b.music_volumes = volumes
    return b


def test_both_switches_start_on():
    b = audio.SoundBank.__new__(audio.SoundBank)
    assert b.music_on is True and b.sfx_on is True


def test_music_off_silences_music_but_not_effects(bank):
    bank.toggle_music()
    assert bank.music_on is False and bank.sfx_on is True
    assert bank.music_volumes[-1] == 0.0
    bank.play("click")
    assert bank.sounds["click"].plays == 1

    bank.toggle_music()
    assert bank.music_volumes[-1] == pytest.approx(audio.MUSIC_VOLUME)


def test_sound_off_silences_effects_but_not_music(bank):
    bank.start_loop("thruster_loop")
    loop = bank._loop_channels["thruster_loop"]

    bank.toggle_sfx()
    assert bank.sfx_on is False and bank.music_on is True
    bank.play("click")
    assert bank.sounds["click"].plays == 0
    assert loop.volume == 0.0
    assert bank.music_volumes[-1] == pytest.approx(audio.MUSIC_VOLUME)

    bank.toggle_sfx()
    assert loop.volume == 1.0
    bank.play("click")
    assert bank.sounds["click"].plays == 1


def test_a_loop_started_while_sound_is_off_stays_silent(bank):
    bank.toggle_sfx()
    bank.start_loop("thruster_loop")
    assert bank._loop_channels["thruster_loop"].volume == 0.0


def test_ctrl_m_mute_keeps_the_switches(bank):
    bank.toggle_music()
    bank.toggle_mute()
    bank.toggle_mute()
    assert bank.music_on is False and bank.sfx_on is True
    assert bank.music_volumes[-1] == 0.0          # still off: the Music switch wins


def test_switches_are_safe_without_an_audio_device(monkeypatch):
    monkeypatch.setattr(pygame.mixer, "get_init", lambda: None)
    b = audio.SoundBank()
    b.toggle_music()
    b.toggle_sfx()
    assert b.music_on is False and b.sfx_on is False


# --- pause menu ------------------------------------------------------------------------

def _scene():
    log = []
    stub = SimpleNamespace(music_on=True, sfx_on=True, play=lambda *a, **k: log.append(("play",) + a),
                  start_loop=lambda name: None, stop_loop=lambda name: None)
    stub.toggle_music = lambda: setattr(stub, "music_on", not stub.music_on)
    stub.toggle_sfx = lambda: setattr(stub, "sfx_on", not stub.sfx_on)
    manager = SceneManager(stub)
    manager.session.level_id = 1
    manager.session.random_seed = None
    scene = GameScene(manager)
    manager.switch(scene)
    return scene, stub, log


def _esc(scene):
    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, mod=0,
                                          unicode="", scancode=0))


def _click(scene, button):
    pos = button.rect.center
    scene.handle_event(pygame.event.Event(pygame.MOUSEMOTION, pos=pos, rel=(0, 0),
                                          buttons=(0, 0, 0)))
    scene.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=pos, button=1))


@pytest.mark.usefixtures("pygame_display")
def test_the_switches_flip_one_setting_each_and_keep_the_menu_open():
    scene, stub, _log = _scene()
    _esc(scene)
    menu = scene.pause_menu
    assert (menu.music_button.label, menu.sfx_button.label) == ("Music: On", "Sound: On")

    _click(scene, menu.music_button)
    assert scene.pause_menu is menu
    assert (stub.music_on, stub.sfx_on) == (False, True)
    assert menu.music_button.label == "Music: Off" and menu.sfx_button.label == "Sound: On"

    _click(scene, menu.sfx_button)
    assert (stub.music_on, stub.sfx_on) == (False, False)
    assert menu.sfx_button.label == "Sound: Off"


@pytest.mark.usefixtures("pygame_display")
def test_reopening_the_menu_shows_the_saved_state():
    scene, stub, _log = _scene()
    stub.music_on, stub.sfx_on = False, True
    _esc(scene)
    assert scene.pause_menu.music_button.label == "Music: Off"
    assert scene.pause_menu.sfx_button.label == "Sound: On"


@pytest.mark.usefixtures("pygame_display")
def test_switches_do_not_resume_a_paused_flight():
    scene, _stub, _log = _scene()
    scene.editor.set_lines(["0.5", "0"])
    scene._on_text_change(scene.editor)
    scene._try_launch()
    _esc(scene)
    t = scene.flight.time
    _click(scene, scene.pause_menu.music_button)
    for _ in range(30):
        scene.update(1 / 60)
    assert scene.state == FLIGHT and scene.pause_menu is not None
    assert scene.flight.time == t


@pytest.mark.usefixtures("pygame_display")
def test_switches_are_hidden_while_confirming_quit():
    scene, _stub, _log = _scene()
    _esc(scene)
    menu = scene.pause_menu
    menu.confirming_quit = True
    assert menu.toggles() == []
