"""Extensible pickup (prop) system with bomb as the first implementation.

Data: ``PickupSpec`` lives in data.py alongside ObstacleSpec/LevelSpec,
so FIXED levels declare pickups like obstacles (data.py is the only
place: no pickups there = no pickups in game). RANDOM levels declare
theirs in level_presets.py (``pickup_groups``). Generic logic here:
``PickupState`` (spec + consumed flag), segment-based collision (reuses
physics.segment_hits_circle, no tunneling), ``EFFECTS`` registry.
Specific behavior: ``bomb_effect`` + ``obstacles_hit_by_blast``.

Adding a new pickup (only 3 steps):
1. effect: ``@register_effect("new_kind")`` on a function
   ``effect(pickup, ctx) -> dict | None``.
2. painter: one entry in ``sprites.PICKUP_RENDERERS["new_kind"]``.
3. placement: fixed -> add ``PickupSpec(kind="new_kind", ...)`` in
   data.py; random -> add ``("new_kind", count, radius)`` to the
   preset's ``pickup_groups`` in level_presets.py.
No changes to collision loop, game loop, Flight, or GameScene.
"""

import logging
import math

log = logging.getLogger(__name__)

# --- tunable constants (single place to adjust) ---------------------------
BOMB_BLAST_RADIUS = 3.0      # explosion radius in meters (world coords)


def discs_overlap(c0, r0, c1, r1, gap=0.0):
    """True when two discs touch/overlap (edge distance <= gap).

    Shared placement rule for pickup<->pickup, pickup<->obstacle and
    obstacle<->obstacle -- one rule, one place, world meters.
    """
    try:
        return math.dist(c0, c1) <= float(r0) + float(r1) + float(gap)
    except (TypeError, ValueError, OverflowError):
        return True  # unreadable coords: treat as overlapping (safe side)


class PickupState:
    """Runtime pickup: static spec plus consumed lifecycle flag.

    ``consumed`` guarantees single-trigger: once True the pickup never
    participates in collision or effects again.
    """

    __slots__ = ("center", "radius", "kind", "consumed", "duration")

    def __init__(self, center, radius, kind="bomb"):
        self.center = (float(center[0]), float(center[1]))
        self.radius = float(radius)
        self.kind = kind
        self.consumed = False
        self.duration = 5.0  # for add_time effect; ignored by other kinds

    @classmethod
    def from_spec(cls, spec):
        return cls(spec.center, spec.radius, getattr(spec, "kind", "bomb"))

    def __repr__(self):
        return (f"PickupState(center={self.center}, radius={self.radius}, "
                f"kind={self.kind!r}, consumed={self.consumed})")


# --- effect registry --------------------------------------------------------
EFFECTS = {}


def register_effect(kind):
    """Decorator registering a pickup effect for ``kind``.

    Effect signature: ``effect(pickup, ctx) -> dict | None`` where ``ctx``
    is the Flight (has ``obstacle_specs``, ``obstacles``, ``hull_radius``).
    The caller marks ``consumed`` BEFORE calling the effect, so re-entry
    never double-applies.
    """
    def deco(func):
        EFFECTS[kind] = func
        return func
    return deco


def _obstacle_center_radius(ob):
    """Return (center, radius) for either an ObstacleSpec object or a
    (center, radius) tuple spec."""
    if isinstance(ob, tuple) and len(ob) == 2 and isinstance(ob[1], (int, float)):
        return ob[0], float(ob[1])
    return (ob.center[0], ob.center[1]), float(ob.radius)


def obstacles_hit_by_blast(center, blast_radius, obstacles):
    """Split obstacles into (survivors, destroyed) by the blast.

    Rule: an obstacle (circle ``center``/``radius``) is destroyed when its
    EDGE touches the blast disc, i.e.
    ``dist(bomb, obstacle_center) <= blast_radius + obstacle.radius``.
    World meters, same coordinates as physics. Preserves input order.
    """
    survivors, destroyed = [], []
    for ob in obstacles:
        ob_center, ob_radius = _obstacle_center_radius(ob)
        dist = math.dist(center, (ob_center[0], ob_center[1]))
        if dist <= blast_radius + ob_radius:
            destroyed.append(ob)
        else:
            survivors.append(ob)
    return survivors, destroyed


@register_effect("bomb")
def bomb_effect(pickup, ctx, blast_radius=BOMB_BLAST_RADIUS):
    """Bomb: destroy obstacles whose edge lies within the blast disc.

    Rewrites ``ctx.obstacle_specs`` and rebuilds ``ctx.obstacles`` (the
    hull-enlarged physics tuple). Returns an event dict for scene sync.
    Never touches unrelated game data.
    """
    specs = list(getattr(ctx, "obstacle_specs", ()) or ())
    survivors, destroyed = obstacles_hit_by_blast(pickup.center, blast_radius, specs)
    ctx.obstacle_specs = survivors
    hull = float(getattr(ctx, "hull_radius", 0.0))
    ctx.obstacles = tuple(
        ((c[0], c[1]), r + hull, getattr(ob, "restitution", 1.0))
        for ob in survivors
        for c, r in [_obstacle_center_radius(ob)]
    )
    return {"kind": "bomb", "center": pickup.center,
            "blast_radius": blast_radius, "destroyed": list(destroyed)}

@register_effect("add_time")
def add_time_effect(pickup, ctx):
    """Add time: increase the game time.

    Rewrites ``ctx.time``. Returns an event dict for scene sync.
    Never touches unrelated game data.
    """
    return {"kind": "add_time", "center": pickup.center, "duration": pickup.duration}


class _NullCtx:
    """Fallback ctx when no Flight is given (keeps bomb testable)."""

    def __init__(self, hull_radius=0.0):
        self.hull_radius = float(hull_radius)
        self.obstacle_specs = []
        self.obstacles = ()


def check_pickups_segment(pickups, p0, p1, hull_radius, ctx=None):
    """Trigger pickups hit by segment p0->p1. Returns list of event dicts.

    Shared lifecycle for ALL kinds: skips consumed pickups, marks consumed
    BEFORE running the effect (single-trigger even if it raises),
    dispatches via EFFECTS. Unknown kinds are consumed with no effect.
    """
    from .physics import segment_hits_circle  # lazy: avoids import cycle

    events = []
    for pickup in pickups or ():
        if pickup.consumed:
            continue
        try:
            hit = segment_hits_circle(p0, p1, pickup.center, pickup.radius + hull_radius)
        except (TypeError, ValueError, OverflowError):
            continue
        if not hit:
            continue
        pickup.consumed = True
        effect = EFFECTS.get(pickup.kind)
        if effect is None:
            events.append({"kind": pickup.kind, "center": pickup.center, "destroyed": []})
            continue
        try:
            event = effect(pickup, ctx) if ctx is not None else effect(pickup, _NullCtx(hull_radius))
        except Exception:
            log.warning("pickup effect %r raised; consumed with no effect", pickup.kind, exc_info=True)
            events.append({"kind": pickup.kind, "center": pickup.center, "destroyed": []})
            continue
        if event is None:
            event = {"kind": pickup.kind, "center": pickup.center, "destroyed": []}
        events.append(event)
    return events


def active_pickups(pickups):
    """Pickups still in play (not consumed)."""
    return [p for p in pickups or () if not p.consumed]

