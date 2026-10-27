"""Tests for the extensible pickup system + shockwave (first pickup)."""

import math

import pygame
import pytest

from vector_drift.data import LevelSpec, ObstacleSpec, PickupSpec, get_level
from vector_drift.physics import Flight, ForceField, Outcome
from vector_drift.pickups import (
    EXTRATIME_DURATION,
    SHOCKWAVE_BLAST_RADIUS,
    SHIELD_DURATION,
    PickupState,
    active_pickups,
    shockwave_effect,
    extratime_effect,
    shield_effect,
    check_pickups_segment,
    discs_overlap,
    obstacles_hit_by_blast,
)

LEVEL = get_level(1)
from vector_drift.data import SHIPS  # noqa: E402

SHIP = SHIPS[LEVEL.ship_id]


def _level_with(obstacles, pickups, start=(-7.0, 0.0)):
    return LevelSpec(id=900, name="Pickup test", start=start,
                     target_center=(7.0, 0.0), target_radius=1.0,
                     ship_id="ship01", obstacles=tuple(obstacles),
                     pickups=tuple(pickups))


PICKUP_KINDS = {"shockwave", "extratime", "shield"}


def test_every_pickup_registry_uses_the_same_kinds():
    from vector_drift import image_assets
    from vector_drift.data import LEVELS
    from vector_drift.level_presets import PRESETS
    from vector_drift.pickups import EFFECTS
    from vector_drift.sprites import PICKUP_RENDERERS

    assert set(EFFECTS) == PICKUP_KINDS
    assert set(PICKUP_RENDERERS) == PICKUP_KINDS
    for kind in PICKUP_KINDS:
        assert image_assets.get_spec(f"pickup.{kind}").path.name == f"{kind}.png"
    assert PickupSpec(center=(0.0, 0.0)).kind == "shockwave"
    assert {p.kind for lv in LEVELS for p in lv.pickups} <= PICKUP_KINDS
    assert {group[0] for preset in PRESETS.values()
            for group in preset.pickup_groups} <= PICKUP_KINDS


def test_pickup_triggers_on_contact():
    pickup = PickupState((0.0, 0.0), 0.45, "shockwave")
    events = check_pickups_segment([pickup], (-1, 0), (1, 0), hull_radius=0.2, ctx=None)
    assert len(events) == 1
    assert pickup.consumed


def test_pickup_misses_when_far():
    pickup = PickupState((0.0, 5.0), 0.45, "shockwave")
    events = check_pickups_segment([pickup], (-1, 0), (1, 0), hull_radius=0.2, ctx=None)
    assert events == []
    assert not pickup.consumed


def test_blast_destroys_inside_and_spares_outside():
    center = (0.0, 0.0)
    inside = ObstacleSpec(center=(1.0, 0.0), radius=0.5)     # edge at 1.5 < 3.0
    edge = ObstacleSpec(center=(4.0, 0.0), radius=0.5)       # near edge 3.5 > 3.0 -> survives
    outside = ObstacleSpec(center=(10.0, 0.0), radius=0.5)   # far away
    survivors, destroyed = obstacles_hit_by_blast(center, SHOCKWAVE_BLAST_RADIUS,
                                                  [inside, edge, outside])
    assert inside in destroyed and outside not in destroyed
    assert edge in survivors           # edge beyond blast disc
    assert outside in survivors and inside not in survivors


def test_blast_rule_uses_edge_distance():
    # dist=3.2, radius=0.5 -> edge at 2.7 <= 3.0 -> destroyed (not center rule).
    grazing = ObstacleSpec(center=(3.2, 0.0), radius=0.5)
    survivors, destroyed = obstacles_hit_by_blast((0, 0), SHOCKWAVE_BLAST_RADIUS, [grazing])
    assert destroyed == [grazing] and survivors == []
    # dist=3.6, radius=0.5 -> edge at 3.1 > 3.0 -> survives.
    far = ObstacleSpec(center=(3.6, 0.0), radius=0.5)
    survivors, destroyed = obstacles_hit_by_blast((0, 0), SHOCKWAVE_BLAST_RADIUS, [far])
    assert survivors == [far] and destroyed == []


def test_shockwave_triggers_once():
    pickup = PickupState((0.0, 0.0), 0.45, "shockwave")
    first = check_pickups_segment([pickup], (-1, 0), (1, 0), 0.2, ctx=None)
    second = check_pickups_segment([pickup], (-1, 0), (1, 0), 0.2, ctx=None)
    assert len(first) == 1 and second == []
    assert active_pickups([pickup]) == []


def test_shockwave_removes_obstacles_through_flight():
    near = ObstacleSpec(center=(1.0, 0.0), radius=0.5)
    far = ObstacleSpec(center=(10.0, 5.0), radius=0.5)
    shockwave = PickupSpec(center=(0.0, 0.0), radius=5.0, kind="shockwave")
    level = _level_with([near, far], [shockwave], start=(0.0, 0.0))
    flight = Flight(ForceField(), SHIP, level)
    n_before = len(flight.obstacle_specs)
    flight.step()  # ship starts on the shockwave -> triggers
    assert any(e["kind"] == "shockwave" for e in flight.pickup_events)
    centers = [o.center for o in flight.obstacle_specs]
    assert (1.0, 0.0) not in centers           # in blast -> gone
    assert (10.0, 5.0) in centers              # out of blast -> kept
    assert len(flight.obstacle_specs) < n_before
    # Consumed shockwave never re-triggers on later steps.
    n_events = len(flight.pickup_events)
    for _ in range(5):
        if flight.running:
            flight.step()
    shockwaves = [e for e in flight.pickup_events if e["kind"] == "shockwave"]
    assert len(shockwaves) == 1 and len(flight.pickup_events) == n_events


def test_draw_pickup_does_not_crash(pygame_surface=None):
    import os
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    from vector_drift import sprites
    surface = pygame.Surface((200, 200))
    sprites.draw_pickup(surface, (100, 100), 20, t=0.0, kind="shockwave")
    sprites.draw_pickup(surface, (100, 100), 20, t=1.0, kind="unknown-kind")


def test_discs_overlap_shared_rule():
    assert discs_overlap((0, 0), 0.5, (0.9, 0), 0.5)       # edges touch
    assert not discs_overlap((0, 0), 0.5, (1.5, 0), 0.5)    # clear gap
    assert discs_overlap((0, 0), 0.5, (1.5, 0), 0.5, gap=0.6)  # gap closes it


def test_fixed_levels_declare_pickups_like_obstacles():
    lv1, lv2 = get_level(1), get_level(2)
    assert len(lv1.pickups) == 0       # LV1 declares no pickups
    assert len(lv2.pickups) == 0       # LV2 declares no pickups
    discs = [(o.center, o.radius) for o in lv2.obstacles]
    discs += [(lv2.start, 0.0), (lv2.target_center, lv2.target_radius)]
    for p in lv2.pickups:
        assert not any(discs_overlap(p.center, p.radius, c, r, 0.3) for c, r in discs)


def test_fixed_levels_owned_by_data():
    # LV1 declares no pickups; deleting it in data.py means zero pickups --
    # nothing is injected behind the author's back.
    assert len(get_level(1).pickups) == 0
    bare = LevelSpec(id=901, name="Bare", start=(-7.0, 0.0),
                     target_center=(7.0, 0.0), target_radius=1.0,
                     ship_id="ship01")
    assert bare.pickups == ()
    assert Flight(ForceField(), SHIP, bare).pickups == ()


def test_random_pickups_on_route_and_unstacked():
    from vector_drift.level_presets import get_preset, RandomPreset
    from vector_drift.physics import segment_hits_circle
    from vector_drift.random_level import generate_with_corridor, place_pickups
    import random as _random

    # PRESET_8 has pickup_groups; PRESET_7 is () so use a custom preset with
    # shockwaves to actually exercise on-route + unstacked placement.
    preset = RandomPreset(
        level_id=99, name="PickupTest",
        pickup_groups=(("shockwave", 2, 0.45),),
        num_obstacles=6, num_direct_blockers=0,
    )
    for seed in range(10):
        level, _, segments = generate_with_corridor(seed=seed, preset=preset)
        expected = sum(n for _, n, _ in (preset.pickup_groups or ()))
        assert len(level.pickups) == expected
        kinds = sorted(p.kind for p in level.pickups)
        assert kinds == sorted(k for k, n, _ in (preset.pickup_groups or ()) for _ in range(n))
        discs = [(o.center, o.radius) for o in level.obstacles]
        discs += [(level.start, 0.0), (level.target_center, level.target_radius)]
        for i, p in enumerate(level.pickups):
            # On the hidden route so the ship can reach it.
            limit = p.radius + preset.pickup_corridor_max
            assert any(segment_hits_circle(a, b, p.center, limit) for a, b in segments)
            # No stacking with obstacles, endpoints, or earlier pickups.
            peers = discs + [(q.center, q.radius) for q in level.pickups[:i]]
            assert not any(discs_overlap(p.center, p.radius, c, r,
                                         preset.min_obstacle_gap) for c, r in peers)
        # Same seed -> same layout (deterministic, incl. pickups).
        again = generate_with_corridor(seed=seed, preset=preset)[0]
        assert [(p.center, p.radius) for p in again.pickups] == [
            (p.center, p.radius) for p in level.pickups]

    # place_pickups never raises on a crowded route -- returns fewer instead.
    rng = _random.Random(0)
    assert place_pickups(rng, [((0, 0), (1, 0))], (0, 0), (1, 0),
                         placed=[((0.2, 0), 5.0)],
                         groups=(("shockwave", 1, 0.45),)) == ()


def test_pickup_groups_config_driven():
    # Random pickups fully driven by level_presets.py: () = none, and a new
    # kind only needs a group entry (+ its effect/painter elsewhere).
    import random as _random
    from vector_drift.level_presets import RandomPreset
    from vector_drift.random_level import place_pickups as _place

    preset = RandomPreset(level_id=98, name="Groups", num_obstacles=0,
                          num_direct_blockers=0,
                          pickup_groups=(("shockwave", 1, 0.45), ("shockwave", 2, 0.3)))
    rng = _random.Random(3)
    start, target = (-7.0, 0.0), (7.0, 0.0)
    out = _place(rng, [(start, target)], start, target, placed=(),
                 preset=preset)
    assert len(out) <= 3 and {p.kind for p in out} <= {"shockwave"}

    empty = RandomPreset(level_id=97, name="NoPickups", num_obstacles=0,
                         num_direct_blockers=0, pickup_groups=())
    assert _place(_random.Random(3), [(start, target)], start, target,
                  placed=(), preset=empty) == ()


def test_consumed_pickups_persist_across_launches():
    # Same PickupState objects shared across Flights (like GameScene does):
    # once consumed, later launches see it gone -- until lives run out.
    shockwave = PickupSpec(center=(0.0, 0.0), radius=5.0, kind="shockwave")
    level = _level_with([], [shockwave], start=(0.0, 0.0))
    shared = [PickupState.from_spec(s) for s in level.pickups]
    first = Flight(ForceField(), SHIP, level, pickups=shared)
    first.step()
    assert shared[0].consumed and any(e["kind"] == "shockwave" for e in first.pickup_events)
    second = Flight(ForceField(), SHIP, level, pickups=shared)
    second.step()
    assert [e for e in second.pickup_events if e["kind"] == "shockwave"] == []


def test_extratime_effect_reports_duration():
    pickup = PickupState((0.0, 0.0), 0.45, "extratime")
    event = extratime_effect(pickup, None)
    assert event == {
        "kind": "extratime",
        "center": (0.0, 0.0),
        "extratime_duration": EXTRATIME_DURATION,
    }


def test_shield_effect_reports_duration():
    pickup = PickupState((0.0, 0.0), 0.45, "shield")
    # Pure effect: works without a Flight (ctx=None), never mutates ctx.
    event = shield_effect(pickup, None)
    assert event == {
        "kind": "shield",
        "center": (0.0, 0.0),
        "shield_duration": SHIELD_DURATION,
    }
    assert not hasattr(pickup, "_mutated_ctx")


# --- extratime / shield applied to the Flight itself ------------------------
# The same rules must hold for GameScene and the solver, so these drive the
# shared path (Flight.step) rather than any one caller's copy of the logic.

def _extratime_level():
    """Ship parked on an extratime pickup with no force: it can only time out."""
    return LevelSpec(id=902, name="Extratime", start=(-7.0, 0.0),
                     target_center=(7.0, 0.0), target_radius=1.0,
                     ship_id="ship01", time_limit=4.0,
                     pickups=(PickupSpec(center=(-7.0, 0.0), kind="extratime"),))


def test_extratime_extends_the_flight_itself():
    flight = Flight(ForceField(), SHIP, _extratime_level())
    while flight.running:
        flight.step()
    assert flight.outcome is Outcome.TIMEOUT
    assert flight.time == pytest.approx(4.0 + EXTRATIME_DURATION)


def test_solver_flight_gets_the_extended_time():
    from vector_drift.solver import EvalConfig, SimulationOutcome, evaluate_candidate, get_template
    template = get_template("general_poly")              # all-zero defaults: no force
    params = dict(zip(template.param_names, template.param_defaults))
    result = evaluate_candidate(level=_extratime_level(), template=template, params=params,
                                config=EvalConfig(record_trajectory=False))
    assert result.record.outcome == SimulationOutcome.TIMEOUT
    assert result.record.time == pytest.approx(4.0 + EXTRATIME_DURATION)


def test_game_scene_flight_gets_the_extended_time_once(pygame_display):
    from types import SimpleNamespace
    from vector_drift.scenes.base import SceneManager
    from vector_drift.scenes.game import GameScene
    audio = SimpleNamespace(play=lambda *a: None, start_loop=lambda *a: None,
                            stop_loop=lambda *a: None)
    scene = GameScene(SceneManager(audio))
    scene.level = _extratime_level()
    scene.pickups = [PickupState.from_spec(s) for s in scene.level.pickups]
    scene.launch_pos = scene.level.start
    scene.editor.set_lines(["0", "0"])
    scene._try_launch()
    flight = scene.flight
    while scene.flight is flight:
        scene.update(1 / 60)
    assert flight.outcome is Outcome.TIMEOUT
    assert flight.time == pytest.approx(4.0 + EXTRATIME_DURATION)


def _protected_flight(bumpers, vx=2.0):
    """No force, ``vx`` to the right from (-7, 0), protection taken at the start."""
    pickup = PickupSpec(center=(-7.0, 0.0), radius=0.3, kind="shield")
    flight = Flight(ForceField(), SHIP, _level_with(bumpers, [pickup]))
    flight.vx = vx
    flight.step()
    assert flight.shield_remaining > 0.0
    return flight


def _inside(flight, bumper):
    return math.dist((flight.x, flight.y), bumper.center) < bumper.radius + SHIP.hull_radius


def _used_events(flight):
    return [e for e in flight.pickup_events if e["kind"] == "shield_used"]


def test_shield_is_used_up_on_the_first_bumper_and_carries_the_ship_through():
    # A is touched at ~0.65 s and B at ~2.15 s: both inside the 3 s window,
    # but only A is passed. B bounces the ship back, and A, now hit from
    # outside, bounces it again.
    bumper_a = ObstacleSpec(center=(-5.0, 0.0), radius=0.5)
    bumper_b = ObstacleSpec(center=(-2.0, 0.0), radius=0.5)
    flight = _protected_flight([bumper_a, bumper_b])

    while flight.running and not _inside(flight, bumper_a):
        flight.step()
    assert flight.shield_remaining == 0.0      # used up the moment A is touched
    assert len(_used_events(flight)) == 1
    assert flight.bounces == 0

    while flight.running and _inside(flight, bumper_a):
        flight.step()
    assert flight.bounces == 0                    # ... yet A is passed all the way
    assert (flight.vx, flight.vy) == (2.0, 0.0)

    while flight.running and flight.bounces == 0:
        flight.step()
    assert flight.time < SHIELD_DURATION       # the old window would still be open
    assert flight.vx < 0.0                        # B bounced it

    while flight.running and flight.bounces == 1:
        flight.step()
    assert flight.vx > 0.0                        # A is solid again from outside
    assert not _inside(flight, bumper_a)
    assert len(_used_events(flight)) == 1


def test_unused_shield_runs_out_and_the_next_bumper_bounces():
    bumper = ObstacleSpec(center=(0.0, 0.0), radius=0.5)  # touched at ~3.15 s
    flight = _protected_flight([bumper])
    while flight.running and flight.bounces == 0:
        flight.step()
    assert flight.time > SHIELD_DURATION
    assert flight.vx < 0.0
    assert _used_events(flight) == []


def _scene_on(level, fx="2", fy="0"):
    from types import SimpleNamespace
    from vector_drift.scenes.base import SceneManager
    from vector_drift.scenes.game import GameScene
    played = []
    audio = SimpleNamespace(play=played.append, start_loop=lambda *a: None,
                            stop_loop=lambda *a: None)
    scene = GameScene(SceneManager(audio))
    scene.level = level
    scene.pickups = [PickupState.from_spec(s) for s in level.pickups]
    scene.launch_pos = level.start
    scene.editor.set_lines([fx, fy])
    scene._try_launch()
    return scene, played


def test_scene_shows_the_shield_while_protected_and_plays_shield_break(pygame_display, monkeypatch):
    from vector_drift import config, sprites
    shields = []
    real_draw_shield = sprites.draw_shield
    monkeypatch.setattr(sprites, "draw_shield",
                        lambda *a, **k: (shields.append(a), real_draw_shield(*a, **k)))
    bumper = ObstacleSpec(center=(-5.0, 0.0), radius=0.5)   # Fx = 2: touched at ~1.14 s
    pickup = PickupSpec(center=(-7.0, 0.0), radius=0.3, kind="shield")
    scene, played = _scene_on(_level_with([bumper], [pickup]))
    screen = pygame.Surface((config.WINDOW_W, config.WINDOW_H))

    scene.update(1 / 60)
    scene.draw(screen)
    assert scene.flight.shield_remaining > 0.0
    assert shields                                 # protected: the bubble is drawn

    while scene.flight is not None and scene.flight.shield_remaining > 0.0:
        scene.update(1 / 60)
    assert played.count("shield_break") == 1       # the moment the rock is touched
    shields.clear()
    scene.draw(screen)
    assert shields == []                           # protection gone: no bubble


def test_telemetry_no_longer_lists_shield_seconds(pygame_display, monkeypatch):
    from vector_drift.scenes import game
    pickup = PickupSpec(center=(-7.0, 0.0), radius=0.3, kind="shield")
    scene, _ = _scene_on(_level_with([], [pickup]))
    scene.update(1 / 60)
    assert scene.flight.shield_remaining > 0.0
    texts = []
    monkeypatch.setattr(game, "draw_text", lambda surface, text, *a, **k: texts.append(text))
    scene._draw_telemetry(pygame.Surface((400, 300)), scene.editor.footer_body)
    assert texts and not any("Shield" in t for t in texts)
