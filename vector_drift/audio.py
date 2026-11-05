"""Sound effects and music loaded from optional asset files.

Missing files (or no audio device) simply mean silence for that slot.
See assets/README.md for the slot list.
"""

import pygame

from . import config

SOUND_SLOTS = ["click", "error", "launch", "thruster_loop", "life_lost", "win", "game_over",
               "shield_break", "shockwave", "extratime", "shield", "life", "money",
               "bounce", "warp", "blip", "purchase", "unbound"]
# Music tracks (assets/music) and whether each one loops.
MUSIC_SLOTS = {"menu": True, "opening": False, "level": True}
FADE_OUT_S = 0.6
FADE_IN_S = 1.0
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
    # Pause-menu switches, independent of each other and of Ctrl+M ``muted``
    # (which silences both). Class defaults so bare instances still work.
    music_on = True
    sfx_on = True

    def __init__(self):
        self.sounds = {}
        self.music_paths = {}
        self.music = None               # track now playing (or fading in)
        self._next_music = None         # track to start once the fade-out ends
        self._fade = 1.0                # 0..1 music fade level
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
        for name in MUSIC_SLOTS:
            path = _find("music", name)
            if path is not None:
                self.music_paths[name] = path
        if missing:
            print(f"[audio] Silent slots (no file in assets/sounds): {', '.join(missing)}")

    # -- effects ------------------------------------------------------------
    def play(self, name):
        sound = self.sounds.get(name)
        if sound and self._sfx_audible():
            sound.play()

    def start_loop(self, name):
        sound = self.sounds.get(name)
        if sound and name not in self._loop_channels:
            channel = sound.play(loops=-1)
            if channel is not None:
                channel.set_volume(1.0 if self._sfx_audible() else 0.0)
                self._loop_channels[name] = channel

    def stop_loop(self, name):
        channel = self._loop_channels.pop(name, None)
        if channel is not None:
            channel.stop()

    # -- music --------------------------------------------------------------
    def set_music(self, name):
        """Fade over to track ``name`` (None = silence). The same track keeps playing."""
        if name == self.music and self._next_music is None:
            return
        if name == self.music:                      # changed back mid-fade
            self._next_music = None
            return
        self._next_music = name
        if self.music is None:
            self._fade = 0.0                        # nothing to fade out

    def update(self, dt):
        """Run the music fades; call once per frame."""
        if self._next_music is not None:
            self._fade = max(0.0, self._fade - dt / FADE_OUT_S)
            if self._fade <= 0.0:
                self._start(self._next_music)
                self._next_music = None
        elif self.music is not None and self._fade < 1.0:
            self._fade = min(1.0, self._fade + dt / FADE_IN_S)
        self._apply_music_volume()

    def _start(self, name):
        self.music = name
        if not self.enabled:
            return
        pygame.mixer.music.stop()
        path = self.music_paths.get(name)
        if path is None:
            return
        try:
            pygame.mixer.music.load(str(path))
            pygame.mixer.music.set_volume(0.0)
            pygame.mixer.music.play(loops=-1 if MUSIC_SLOTS[name] else 0)
        except pygame.error as exc:
            print(f"[audio] Could not play music: {exc}")

    def _apply_music_volume(self):
        if self.enabled:
            audible = self.music_on and not self.muted
            pygame.mixer.music.set_volume(MUSIC_VOLUME * self._fade if audible else 0.0)

    # -- mute ---------------------------------------------------------------
    def _sfx_audible(self):
        return self.sfx_on and not self.muted

    def _apply_loop_volume(self):
        for channel in self._loop_channels.values():
            channel.set_volume(1.0 if self._sfx_audible() else 0.0)

    def _apply_switches(self):
        if not self.enabled:
            return
        self._apply_loop_volume()
        self._apply_music_volume()

    def toggle_mute(self):
        """Ctrl+M: silence everything (keeps the music/sfx switches as they are)."""
        self.muted = not self.muted
        self._apply_switches()

    def toggle_music(self):
        """Pause-menu Music switch; sound effects are untouched."""
        self.music_on = not self.music_on
        self._apply_switches()

    def toggle_sfx(self):
        """Pause-menu Sound switch; music is untouched."""
        self.sfx_on = not self.sfx_on
        self._apply_switches()
