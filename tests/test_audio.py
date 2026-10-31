import pygame

from vector_drift import audio
from vector_drift import config


def test_find_returns_none_when_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "ASSETS_DIR", tmp_path)
    assert audio._find("sounds", "nope") is None


def test_soundbank_disabled_when_no_mixer(monkeypatch):
    monkeypatch.setattr(pygame.mixer, "get_init", lambda: None)
    bank = audio.SoundBank()
    assert bank.enabled is False
    assert bank.sounds == {}
    # no-op paths
    bank.play("click")
    bank.start_loop("click")
    bank.stop_loop("click")
    bank.start_music()
    bank.toggle_mute()
    assert bank.muted is True


def test_soundbank_toggle_mute_enabled(monkeypatch):
    # Pretend mixer is available but no sounds/music
    monkeypatch.setattr(pygame.mixer, "get_init", lambda: object())
    monkeypatch.setattr(pygame.mixer.music, "set_volume", lambda v: None)
    bank = audio.SoundBank.__new__(audio.SoundBank)
    # minimal init bypass: set attributes manually
    bank.sounds = {}
    bank.music_path = None
    bank.muted = False
    bank.enabled = True
    bank._loop_channels = {}
    bank.toggle_mute()
    assert bank.muted is True
    # second toggle
    bank.toggle_mute()
    assert bank.muted is False
