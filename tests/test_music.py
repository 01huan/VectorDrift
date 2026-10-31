"""Music: the three tracks, their loop points, and which scene plays which."""

import importlib.util
import wave

import numpy as np
import pygame
import pytest

from vector_drift import config
from vector_drift.audio import MUSIC_SLOTS, SoundBank
from vector_drift.scenes.base import SceneManager

MUSIC_DIR = config.ASSETS_DIR / "music"
TOOL = config.ASSETS_DIR.parent / "tools" / "make_music.py"


def _read(name):
    with wave.open(str(MUSIC_DIR / f"{name}.wav")) as f:
        assert (f.getnchannels(), f.getsampwidth(), f.getframerate()) == (1, 2, 22050)
        return np.frombuffer(f.readframes(f.getnframes()), np.int16).astype(int)


def test_the_generator_makes_exactly_the_music_slots():
    spec = importlib.util.spec_from_file_location("make_music", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert set(module.TRACKS) == set(MUSIC_SLOTS)


@pytest.mark.parametrize("name", list(MUSIC_SLOTS))
def test_every_track_exists_and_is_not_clipped(name):
    x = _read(name)
    assert 30 * 22050 < len(x) < 120 * 22050
    assert 3000 < np.abs(x).max() < 32767


@pytest.mark.parametrize("name", [n for n, loops in MUSIC_SLOTS.items() if loops])
def test_looping_tracks_have_no_jump_at_the_loop_point(name):
    x = _read(name)
    typical = np.percentile(np.abs(np.diff(x)), 99)
    assert abs(x[-1] - x[0]) <= typical


def test_opening_fades_out_to_silence():
    x = _read("opening")
    assert np.abs(x[-2205:]).max() < 300


# --- switching -----------------------------------------------------------------------
@pytest.fixture
def bank():
    pygame.mixer.init()
    yield SoundBank()
    pygame.mixer.quit()


def _settle(bank, name):
    """Start ``name`` and let its fade-in finish."""
    bank.set_music(name)
    bank.update(0.01)
    bank.update(2.0)


def test_first_track_starts_at_once_then_fades_in(bank):
    bank.set_music("menu")
    bank.update(0.01)
    assert bank.music == "menu"
    bank.update(2.0)
    assert bank._fade == 1.0


def test_changing_track_fades_out_first(bank):
    _settle(bank, "menu")
    bank.set_music("level")
    bank.update(0.1)
    assert bank.music == "menu" and bank._fade < 1.0
    bank.update(1.0)
    assert bank.music == "level"


def test_asking_for_the_same_track_keeps_it_playing(bank):
    _settle(bank, "menu")
    bank.set_music("menu")
    bank.update(0.1)
    assert bank.music == "menu" and bank._fade == 1.0


class RecordingAudio:
    def __init__(self):
        self.music = []

    def set_music(self, name):
        self.music.append(name)

    def play(self, name):
        pass

    def start_loop(self, name):
        pass

    def stop_loop(self, name):
        pass


@pytest.mark.usefixtures("pygame_display")
def test_each_scene_asks_for_its_track():
    from vector_drift.scenes.fail import FailScene
    from vector_drift.scenes.game import GameScene
    from vector_drift.scenes.intro import IntroScene
    from vector_drift.scenes.levels import LevelSelectScene
    from vector_drift.scenes.menu import MenuScene
    from vector_drift.story import all_seen_keys

    audio = RecordingAudio()
    manager = SceneManager(audio)
    manager.session.story_seen = all_seen_keys()
    for scene_class in (MenuScene, IntroScene, LevelSelectScene, GameScene):
        manager.switch(scene_class(manager))
    manager.switch(FailScene(manager))              # keeps the level music
    assert audio.music == ["menu", "opening", "menu", "level"]
