"""Pickup effects: what the player sees when the ship takes a pickup.

Presentation only. The Flight has already applied every rule the moment a
pickup triggered (Flight._apply_pickup_events); nothing here touches the
flight, the score or the coins. GameScene adds one effect per pickup event
(_drain_pickup_events), ages them every unpaused frame and draws them:

* burst (shockwave, shield): the pickup grows to BURST_SCALE and fades out.
* fly (extratime, money): a "+N" text flies to the timer or the coin count;
  that number shows the new value only once the text arrives, then jumps.
* life: the glowing ship of a checkpoint's life floats up and fades out; the
  lives-counter icon it lit up (if any) jumps.
* edge (unbound): the map edge flashes in its dashed-edge colour.

World effects keep their position in world metres and are turned into
screen pixels every frame through the camera; the fly texts start from the
screen point where the pickup was and end on the HUD.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# --- how long, how big, what colour --------------------------------------------
BURST_S = 0.5               # shockwave / shield: the pickup grows and fades this long
BURST_SCALE = 2.0           # ... up to this many times its size
FLY_S = 0.6                 # extratime / money: the "+N" text takes this long to reach the HUD
FLY_TEXT_SIZE = 22
EXTRATIME_COLOR = (120, 235, 130)   # "+3" text, and the timer while it flashes
MONEY_COLOR = (255, 206, 84)        # "+N" coins text
LIFE_S = 0.8                # life: the glowing ship floats up, grows and fades this long
LIFE_RADIUS_SCALE = 1.6     # it is drawn like a checkpoint of this many pickup radii
EDGE_S = 0.4                # unbound: the map edge flashes this long
EDGE_FLASH_IN = 24          # logical px: the flash starts this far inside the edge, moves out to it
EDGE_FLASH_WIDTH = 4        # logical px
HUD_POP_S = 0.3             # the timer / coin count / newly lit life icon jumps this long ...
HUD_POP_SCALE = 1.3         # ... growing to this size and back
POP_HEAD_START = 0.2        # share of the jump already done on its first frame
DEFAULT_RADIUS_M = 0.45     # pickup radius when the event's pickup is not found

# What a fly text heads for, and what jumps on the HUD.
TIMER, COINS, LIFE = "timer", "coins", "life"


@dataclass
class PickupEffect:
    style: str                      # "burst" | "fly" | "life" | "edge"
    kind: str                       # the pickup kind that made it
    duration: float
    center: tuple = (0.0, 0.0)      # burst / life: world m; fly: screen px it starts from
    radius: float = 0.0             # burst / life: the pickup's radius in m
    bounds: tuple = (0.0, 0.0)      # edge: the map's half width and height in m
    target: str = ""                # fly: TIMER or COINS
    text: str = ""                  # fly: "+3", "+1", ...
    color: tuple = (255, 255, 255)  # fly: text colour
    amount: float = 0.0             # fly: what the target is short of until the text arrives
    age: float = 0.0

    @property
    def progress(self):
        """0 when it starts, 1 when it is over."""
        return min(1.0, self.age / self.duration) if self.duration > 0 else 1.0


class PickupEffects:
    """Every pickup effect on screen now, and the HUD numbers that jump."""

    def __init__(self):
        self.effects: list[PickupEffect] = []
        self.pops: dict[str, list] = {}     # TIMER / COINS / LIFE -> [age, life icon index]

    def clear(self):
        self.effects.clear()
        self.pops.clear()

    # --- adding ------------------------------------------------------------
    def burst(self, kind, center, radius):
        self.effects.append(PickupEffect("burst", kind, BURST_S, center=tuple(center),
                                         radius=float(radius)))

    def fly(self, kind, target, text, color, amount, start):
        self.effects.append(PickupEffect("fly", kind, FLY_S, center=tuple(start), target=target,
                                         text=text, color=color, amount=amount))

    def life(self, center, radius, lit_index=None):
        """The life floats up; ``lit_index`` is the lives icon it lit (None: lives were full)."""
        self.effects.append(PickupEffect("life", "life", LIFE_S, center=tuple(center),
                                         radius=float(radius)))
        if lit_index is not None:
            self.pops[LIFE] = [0.0, lit_index]

    def edge(self, bounds):
        self.effects.append(PickupEffect("edge", "unbound", EDGE_S, bounds=tuple(bounds)))

    # --- time --------------------------------------------------------------
    def update(self, dt):
        """Age everything by ``dt`` s; a fly text that arrives makes its target jump."""
        for name in list(self.pops):
            self.pops[name][0] += dt
            if self.pops[name][0] >= HUD_POP_S:
                del self.pops[name]
        running = []
        for effect in self.effects:
            effect.age += dt
            if effect.age < effect.duration:
                running.append(effect)
            elif effect.style == "fly":
                self.pops[effect.target] = [effect.age - effect.duration, None]
        self.effects = running

    # --- what the HUD shows ------------------------------------------------
    def pending(self, target):
        """How much ``target`` still waits for: the texts flying to it now."""
        return sum(e.amount for e in self.effects if e.style == "fly" and e.target == target)

    def pop_scale(self, name, index=None):
        """Size of a jumping HUD item: 1 when still, up to HUD_POP_SCALE mid-jump.

        For LIFE, ``index`` is the lives icon asked about; only the one the
        life lit up jumps.
        """
        pop = self.pops.get(name)
        if pop is None or (name == LIFE and pop[1] != index):
            return 1.0
        # Already part way up on the first frame, biggest a third of the way in,
        # back to 1 at the end.
        q = POP_HEAD_START + (1.0 - POP_HEAD_START) * min(1.0, pop[0] / HUD_POP_S)
        return 1.0 + (HUD_POP_SCALE - 1.0) * math.sin(math.pi * q)

    def popping(self, name):
        return name in self.pops


__all__ = [
    "BURST_S", "BURST_SCALE", "FLY_S", "FLY_TEXT_SIZE", "EXTRATIME_COLOR", "MONEY_COLOR",
    "LIFE_S", "LIFE_RADIUS_SCALE", "EDGE_S", "EDGE_FLASH_IN", "EDGE_FLASH_WIDTH",
    "HUD_POP_S", "HUD_POP_SCALE", "POP_HEAD_START", "DEFAULT_RADIUS_M", "TIMER", "COINS", "LIFE",
    "PickupEffect", "PickupEffects",
]
