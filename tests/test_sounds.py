"""Sound effects: tools/make_sounds.py, the wav files and when the game plays them."""

import importlib.util
import wave

import numpy as np
import pygame
import pytest

from vector_drift import config
from vector_drift.audio import SOUND_SLOTS
from vector_drift.hints import get_hint
from vector_drift.scenes.base import SceneManager
from vector_drift.scenes.dialogue import DialogueBox
from vector_drift.scenes.game import FLIGHT, GameScene
from vector_drift.story import all_seen_keys

SOUNDS_DIR = config.ASSETS_DIR / "sounds"
TOOL = config.ASSETS_DIR.parent / "tools" / "make_sounds.py"


def _tool():
    spec = importlib.util.spec_from_file_location("make_sounds", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read(name):
    with wave.open(str(SOUNDS_DIR / f"{name}.wav")) as f:
        assert (f.getnchannels(), f.getsampwidth(), f.getframerate()) == (1, 2, 44100)
        return np.frombuffer(f.readframes(f.getnframes()), np.int16)


class RecordingAudio:
    def __init__(self):
        self.played = []

    def play(self, name):
        self.played.append(name)

    def start_loop(self, name):
        pass

    def stop_loop(self, name):
        pass


# --- the files ---------------------------------------------------------------------
def test_the_generator_makes_exactly_the_sound_slots():
    assert set(_tool().SOUNDS) == set(SOUND_SLOTS)


@pytest.mark.parametrize("name", SOUND_SLOTS)
def test_every_slot_has_a_short_clean_wav(name):
    x = _read(name)
    assert 0 < len(x) < 3 * 44100
    peak = np.abs(x.astype(int)).max()
    assert 1000 < peak < 32767                      # audible, never clipped


@pytest.mark.parametrize("name", SOUND_SLOTS)
def test_files_match_the_generator(name):
    """Edit tools/make_sounds.py, then rerun it: the files must not drift."""
    assert np.array_equal(_tool().render(name), _read(name))


def test_thruster_loop_has_no_seam():
    x = _read("thruster_loop").astype(int)
    step = np.abs(np.diff(x)).max()
    assert abs(x[0] - x[-1]) <= step


# --- when they play ----------------------------------------------------------------
pygame_scene = pytest.mark.usefixtures("pygame_display")


def _scene(level_id, audio):
    manager = SceneManager(audio)
    manager.session.story_seen = all_seen_keys()
    manager.session.level_id = level_id
    scene = GameScene(manager)
    manager.switch(scene)
    return scene


def _fly(scene, fx, fy):
    scene.editor.set_lines([fx, fy])
    scene._on_text_change(scene.editor)
    scene._try_launch()
    for _ in range(2000):
        if scene.state != FLIGHT:
            return
        scene.update(1 / 60)


@pygame_scene
def test_hitting_a_rock_plays_bounce():
    audio = RecordingAudio()
    scene = _scene(2, audio)                        # one rock in the middle of the path
    _fly(scene, "3", "0")
    assert "bounce" in audio.played


@pygame_scene
def test_passing_a_black_hole_plays_warp_once():
    audio = RecordingAudio()
    scene = _scene(4, audio)
    answer = get_hint(4).answers[0]
    _fly(scene, answer.fx, answer.fy)
    assert audio.played.count("warp") == 1


@pygame_scene
def test_dialogue_blips_while_typing_only():
    audio = RecordingAudio()
    line = "They say Poland cannot into space."
    box = DialogueBox((line,), (0, 0, 800, 600), audio)
    for _ in range(120):
        box.update(1 / 60)
    assert audio.played.count("blip") == len(line) // 3
    box.update(1.0)                                 # the line is done: no more blips
    assert audio.played.count("blip") == len(line) // 3
