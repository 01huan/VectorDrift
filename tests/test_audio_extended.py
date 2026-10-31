import pygame

from vector_drift import audio
from vector_drift import config


def test_soundbank_enabled_missing_slots(monkeypatch, tmp_path):
    monkeypatch.setattr(pygame.mixer, "get_init", lambda: object())
    monkeypatch.setattr(config, "ASSETS_DIR", tmp_path)
    monkeypatch.setattr(pygame.mixer.music, "set_volume", lambda v: None)
    bank = audio.SoundBank()
    assert bank.enabled is True
    assert bank.sounds == {}
    assert bank.music_path is None
    # exercise no-op methods
    bank.play("click")
    bank.start_loop("thruster_loop")
    bank.stop_loop("thruster_loop")
    bank.start_music()
    bank.toggle_mute()
    assert bank.muted is True


def test_soundbank_enabled_with_fake_sound(monkeypatch, tmp_path):
    # create a fake sound file path by monkeypatching _find
    fake_path = tmp_path / "click.ogg"
    fake_path.write_bytes(b"")
    monkeypatch.setattr(pygame.mixer, "get_init", lambda: object())
    monkeypatch.setattr(audio, "_find", lambda folder, name: fake_path if name == "click" else None)

    class FakeSound:
        def __init__(self, path):
            self.path = path
            self.volume = None

        def set_volume(self, v):
            self.volume = v

        def play(self, loops=0):
            return None

    monkeypatch.setattr(pygame.mixer, "Sound", FakeSound)
    monkeypatch.setattr(pygame.mixer.music, "set_volume", lambda v: None)
    bank = audio.SoundBank()
    assert "click" in bank.sounds
    # play path
    bank.play("click")
    # start_loop / stop_loop with a channel
    class FakeChannel:
        def __init__(self):
            self.volume = None

        def set_volume(self, v):
            self.volume = v

        def stop(self):
            pass

    sound = bank.sounds["click"]
    monkeypatch.setattr(sound, "play", lambda loops=-1: FakeChannel())
    bank.start_loop("click")
    assert "click" in bank._loop_channels
    bank.start_loop("click")  # already looping -> no-op
    bank.stop_loop("click")
    assert "click" not in bank._loop_channels
    # toggle mute with loop channels
    bank._loop_channels["click"] = FakeChannel()
    bank.toggle_mute()
    assert bank.muted is True
