"""Ability effects: what the player sees when an active ability fires.

Presentation only. The Flight has already applied every rule the moment the
ability was triggered (Flight.boost / shield_pulse / magnet_pulse /
time_freeze / phase_shift / retro_burn / blink); nothing here touches the
flight, the charges or the score. GameScene starts one effect per ability
use (_use_ability_key), ages them every unpaused frame and draws them.

Every effect is a flash at the spot where the ability was used: a soft disc
with two expanding rings around it, plus the ability's name floating up and
fading out. The rings keep their place in world metres and are turned into
screen pixels every frame through the camera, so they follow the ship on a
zoomed-out map too.

The replay scene rebuilds the same effects from the recorded ability events
(replay.ReplayRecord.ability_events), so a saved launch shows the very same
flashes when it is played back.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pygame

from .. import config
from ..config import px
from ..ui import draw_text

# --- how long, how big, what colour --------------------------------------------
ABILITY_FX_S = 0.8               # an ability's flash lasts this long (s)
RING_R0_M = 0.45                # the ring starts this big ...
RING_R1_M = 1.70                # ... and grows to this (m)
RING_WIDTH = 4                  # logical px
LABEL_SIZE = 15
LABEL_LIFT_PX = 26              # the name floats this far up (logical px)
LABEL_OFFSET_M = 0.95           # the name starts this far above the spot (m)

# The colour of each ability's flash.
ABILITY_COLORS = {
    "ability_boost": (255, 170, 70),
    "ability_shield_pulse": (120, 220, 255),
    "ability_magnet": (200, 140, 255),
    "ability_time_freeze": (150, 210, 255),
    "ability_phase": (150, 240, 220),
    "ability_brake": (255, 110, 90),
    "ability_blink": (190, 160, 255),
}
DEFAULT_COLOR = config.TRAIL


def ability_color(ability_id):
    """The flash colour of an ability (a neutral one for unknown ids)."""
    return ABILITY_COLORS.get(str(ability_id), DEFAULT_COLOR)


def _fade(color, progress):
    """The colour dimmed towards the background: the text fades out with it."""
    try:
        p = max(0.0, min(1.0, float(progress)))
        return tuple(max(0, min(255, round(c + (b - c) * p)))
                     for c, b in zip(color, config.BG))
    except (TypeError, ValueError, OverflowError):
        return color


@dataclass
class AbilityEffect:
    """One ability flash: where it happened, what it was and how old it is."""

    ability_id: str = ""
    name: str = ""
    center: tuple = (0.0, 0.0)      # world m
    age: float = 0.0
    duration: float = ABILITY_FX_S

    @property
    def progress(self):
        """0 when it starts, 1 when it is over."""
        return min(1.0, self.age / self.duration) if self.duration > 0 else 1.0


class AbilityEffects:
    """Every ability effect on screen now."""

    def __init__(self):
        self.effects: list[AbilityEffect] = []

    def clear(self):
        self.effects.clear()

    def add(self, ability_id, name, center):
        """Start one effect at ``center`` (world m)."""
        try:
            spot = (float(center[0]), float(center[1]))
        except (TypeError, ValueError, IndexError, OverflowError):
            return
        if not (math.isfinite(spot[0]) and math.isfinite(spot[1])):
            return
        self.effects.append(AbilityEffect(str(ability_id), str(name or ""), spot))

    def update(self, dt):
        """Age every effect by ``dt`` s and drop the ones that are over."""
        try:
            dt = float(dt)
        except (TypeError, ValueError):
            return
        for effect in self.effects:
            effect.age += dt
        self.effects = [e for e in self.effects if e.age < e.duration]

    def __len__(self):
        return len(self.effects)


def effects_at(events, now):
    """The ability effects that are showing at playback time ``now``.

    The replay does not keep a live list of effects: it rebuilds them from
    the recorded events every frame, so seeking back and forth shows exactly
    the flashes that belong to the playback position.
    """
    out = []
    try:
        now = float(now)
    except (TypeError, ValueError):
        return out
    if not math.isfinite(now):
        return out
    for event in events or ():
        if not isinstance(event, dict):
            continue
        try:
            age = now - float(event.get("t", 0.0))
            spot = (float(event.get("x", 0.0)), float(event.get("y", 0.0)))
        except (TypeError, ValueError, OverflowError):
            continue
        if age < 0.0 or age >= ABILITY_FX_S:
            continue
        if not (math.isfinite(age) and math.isfinite(spot[0]) and math.isfinite(spot[1])):
            continue
        out.append(AbilityEffect(str(event.get("ability", "")),
                                 str(event.get("name", "")),
                                 spot, age))
    return out


# --- drawing ------------------------------------------------------------------
def _ring(surface, center, radius, color, alpha, width):
    """One fading ring drawn on its own transparent layer."""
    r = max(1, int(round(radius)))
    if r <= 1 or alpha <= 0:
        return
    size = 2 * r + 4
    layer = pygame.Surface((size, size), pygame.SRCALPHA)
    pygame.draw.circle(layer, (*color, max(0, min(255, int(alpha)))),
                       (size // 2, size // 2), r, max(1, int(width)))
    surface.blit(layer, layer.get_rect(center=(int(round(center[0])), int(round(center[1])))))


def _glow(surface, center, radius, color, alpha):
    """The soft disc inside the ring: the flash itself."""
    r = max(1, int(round(radius)))
    if r <= 1 or alpha <= 0:
        return
    size = 2 * r + 4
    layer = pygame.Surface((size, size), pygame.SRCALPHA)
    pygame.draw.circle(layer, (*color, max(0, min(255, int(alpha)))),
                       (size // 2, size // 2), r)
    surface.blit(layer, layer.get_rect(center=(int(round(center[0])), int(round(center[1])))))


def _pulse(t):
    """A slow 0..1 breathing value: the flash pulses while it shows."""
    try:
        value = 0.5 + 0.5 * math.sin(float(t) * 6.0)
    except (TypeError, ValueError, OverflowError):
        return 0.5
    return value if math.isfinite(value) else 0.5


def draw_effects(surface, effects, to_screen, length, t):
    """Draw the ability effects: two rings and a floating name at each spot.

    ``to_screen`` turns world metres into pixels and ``length`` metres into
    pixels (both from the camera / viewport).
    """
    for effect in effects or ():
        try:
            _draw_one(surface, effect, to_screen, length, t)
        except (pygame.error, TypeError, ValueError, OverflowError, MemoryError):
            continue


def _draw_one(surface, effect, to_screen, length, t):
    cx, cy = to_screen(*effect.center)
    if not (math.isfinite(cx) and math.isfinite(cy)):
        return
    cull = config.MAX_PX_CULL
    if cx < -cull or cx > surface.get_width() + cull or cy < -cull or cy > surface.get_height() + cull:
        return
    p = effect.progress
    color = ability_color(effect.ability_id)
    alpha = round(255 * (1.0 - p))
    if alpha <= 0:
        return
    outer = length(RING_R0_M) + (length(RING_R1_M) - length(RING_R0_M)) * p
    pulse = _pulse(t)
    _glow(surface, (cx, cy), outer * 0.8, color, round(alpha * (0.12 + 0.10 * pulse)))
    _ring(surface, (cx, cy), outer, color, alpha, px(RING_WIDTH))
    _ring(surface, (cx, cy), outer * 0.55, color, round(alpha * 0.7),
          max(1, px(RING_WIDTH) - 1))
    # The ability's name floats up above the spot and fades out with the rings.
    label = effect.name
    if not label:
        return
    try:
        lx, ly = to_screen(effect.center[0], effect.center[1] + LABEL_OFFSET_M)
    except (TypeError, ValueError, OverflowError):
        return
    if not (math.isfinite(lx) and math.isfinite(ly)):
        return
    ly -= px(LABEL_LIFT_PX) * p
    draw_text(surface, label, (lx, ly), LABEL_SIZE, _fade(color, p),
              kind="bold", anchor="center")


__all__ = [
    "ABILITY_FX_S", "ABILITY_COLORS", "DEFAULT_COLOR", "LABEL_LIFT_PX",
    "LABEL_OFFSET_M", "LABEL_SIZE", "RING_R0_M", "RING_R1_M", "RING_WIDTH",
    "AbilityEffect", "AbilityEffects", "ability_color", "draw_effects",
    "effects_at",
]
