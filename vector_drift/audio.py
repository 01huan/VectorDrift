"""Sound effects and music loaded from optional CC0 asset files.

Missing files (or no audio device) simply mean silence for that slot.
See assets/README.md for the slot list.
"""

import pygame

from . import config

SOUND_SLOTS = ["click", "error", "launch", "thruster_loop", "life_lost", "win", "game_over"]
MUSIC_SLOT = "bgm"
EXTENSIONS = (".ogg", ".wav", ".mp3")

SFX_VOLUME = 0.7
MUSIC_VOLUME = 0.35


def _find(folder, name):
    for ext in EXTENSIONS:
        path = config.ASSETS_DIR / folder / (name + ext)
        if path.exists():
            return path
    return None


class SoundBank:
    def __init__(self):
        self.sounds = {}
        self.music_path = None
        self.muted = False
        self.enabled = pygame.mixer.get_init() is not None
        self._loop_channels = {}
        if not self.enabled:
            print("[audio] No audio device; running silent.")
            return

        missing = []
        for name in SOUND_SLOTS:
            path = _find("sounds", name)
            if path is None:
                missing.append(name)
                continue
            try:
                sound = pygame.mixer.Sound(str(path))
                sound.set_volume(SFX_VOLUME)
                self.sounds[name] = sound
            except pygame.error as exc:
                print(f"[audio] Could not load {path.name}: {exc}")
        self.music_path = _find("music", MUSIC_SLOT)
        if missing:
            print(f"[audio] Silent slots (no file in assets/sounds): {', '.join(missing)}")

    # -- effects ------------------------------------------------------------
    def play(self, name):
        sound = self.sounds.get(name)
        if sound and not self.muted:
            sound.play()

    def start_loop(self, name):
        sound = self.sounds.get(name)
        if sound and name not in self._loop_channels:
            channel = sound.play(loops=-1)
            if channel is not None:
                channel.set_volume(0.0 if self.muted else 1.0)
                self._loop_channels[name] = channel

    def stop_loop(self, name):
        channel = self._loop_channels.pop(name, None)
        if channel is not None:
            channel.stop()

    # -- music --------------------------------------------------------------
    def start_music(self):
        if not (self.enabled and self.music_path):
            return
        if pygame.mixer.music.get_busy():
            return
        try:
            pygame.mixer.music.load(str(self.music_path))
            pygame.mixer.music.set_volume(0.0 if self.muted else MUSIC_VOLUME)
            pygame.mixer.music.play(loops=-1)
        except pygame.error as exc:
            print(f"[audio] Could not play music: {exc}")

    # -- mute ---------------------------------------------------------------
    def toggle_mute(self):
        self.muted = not self.muted
        if not self.enabled:
            return
        for channel in self._loop_channels.values():
            channel.set_volume(0.0 if self.muted else 1.0)
        pygame.mixer.music.set_volume(0.0 if self.muted else MUSIC_VOLUME)
