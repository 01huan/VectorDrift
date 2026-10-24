"""Tests for the extensible pickup system + bomb (first pickup)."""

import math

import pygame
import pytest

from vector_drift.data import LevelSpec, ObstacleSpec, PickupSpec, get_level
from vector_drift.physics import Flight, ForceField, Outcome
from vector_drift.pickups import (
    ADD_TIME_DURATION,
    BOMB_BLAST_RADIUS,
    PENETRATE_DURATION,
    PickupState,
    active_pickups,
    bomb_effect,
    add_time_effect,
    penetrate_effect,
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
                     ship_id="drifter", obstacles=tuple(obstacles),
                     pickups=tuple(pickups))


def test_pickup_triggers_on_contact():
    pickup = PickupState((0.0, 0.0), 0.45, "bomb")
    events = check_pickups_segment([pickup], (-1, 0), (1, 0), hull_radius=0.2, ctx=None)
    assert len(events) == 1
    assert pickup.consumed


def test_pickup_misses_when_far():
    pickup = PickupState((0.0, 5.0), 0.45, "bomb")
    events = check_pickups_segment([pickup], (-1, 0), (1, 0), hull_radius=0.2, ctx=None)
    assert events == []
    assert not pickup.consumed


def test_blast_destroys_inside_and_spares_outside():
    center = (0.0, 0.0)
    inside = ObstacleSpec(center=(1.0, 0.0), radius=0.5)     # edge at 1.5 < 3.0
    edge = ObstacleSpec(center=(4.0, 0.0), radius=0.5)       # near edge 3.5 > 3.0 -> survives
    outside = ObstacleSpec(center=(10.0, 0.0), radius=0.5)   # far away
    survivors, destroyed = obstacles_hit_by_blast(center, BOMB_BLAST_RADIUS,
                                                  [inside, edge, outside])
    assert inside in destroyed and outside not in destroyed
    assert edge in survivors           # edge beyond blast disc
    assert outside in survivors and inside not in survivors


def test_blast_rule_uses_edge_distance():
    # dist=3.2, radius=0.5 -> edge at 2.7 <= 3.0 -> destroyed (not center rule).
    grazing = ObstacleSpec(center=(3.2, 0.0), radius=0.5)
    survivors, destroyed = obstacles_hit_by_blast((0, 0), BOMB_BLAST_RADIUS, [grazing])
    assert destroyed == [grazing] and survivors == []
    # dist=3.6, radius=0.5 -> edge at 3.1 > 3.0 -> survives.
    far = ObstacleSpec(center=(3.6, 0.0), radius=0.5)
    survivors, destroyed = obstacles_hit_by_blast((0, 0), BOMB_BLAST_RADIUS, [far])
    assert survivors == [far] and destroyed == []


def test_bomb_triggers_once():
    pickup = PickupState((0.0, 0.0), 0.45, "bomb")
    first = check_pickups_segment([pickup], (-1, 0), (1, 0), 0.2, ctx=None)
    second = check_pickups_segment([pickup], (-1, 0), (1, 0), 0.2, ctx=None)
    assert len(first) == 1 and second == []
    assert active_pickups([pickup]) == []


def test_bomb_removes_obstacles_through_flight():
    near = ObstacleSpec(center=(1.0, 0.0), radius=0.5)
    far = ObstacleSpec(center=(10.0, 5.0), radius=0.5)
    bomb = PickupSpec(center=(0.0, 0.0), radius=5.0, kind="bomb")
    level = _level_with([near, far], [bomb], start=(0.0, 0.0))
    flight = Flight(ForceField(), SHIP, level)
    n_before = len(flight.obstacle_specs)
    flight.step()  # ship starts on the bomb -> triggers
    assert any(e["kind"] == "bomb" for e in flight.pickup_events)
    centers = [o.center for o in flight.obstacle_specs]
    assert (1.0, 0.0) not in centers           # in blast -> gone
    assert (10.0, 5.0) in centers              # out of blast -> kept
    assert len(flight.obstacle_specs) < n_before
    # Consumed bomb never re-triggers on later steps.
    n_events = len(flight.pickup_events)
    for _ in range(5):
        if flight.running:
            flight.step()
    bombs = [e for e in flight.pickup_events if e["kind"] == "bomb"]
    assert len(bombs) == 1 and len(flight.pickup_events) == n_events


def test_draw_pickup_does_not_crash(pygame_surface=None):
    import os
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    from vector_drift import sprites
    surface = pygame.Surface((200, 200))
    sprites.draw_pickup(surface, (100, 100), 20, t=0.0, kind="bomb")
    sprites.draw_pickup(surface, (100, 100), 20, t=1.0, kind="unknown-kind")


def test_discs_overlap_shared_rule():
    assert discs_overlap((0, 0), 0.5, (0.9, 0), 0.5)       # edges touch
    assert not discs_overlap((0, 0), 0.5, (1.5, 0), 0.5)    # clear gap
    assert discs_overlap((0, 0), 0.5, (1.5, 0), 0.5, gap=0.6)  # gap closes it


def test_fixed_levels_declare_pickups_like_obstacles():
    lv1, lv2 = get_level(1), get_level(2)
    assert len(lv1.pickups) == 0       # LV1 declares no pickups
    assert len(lv2.pickups) == 1       # LV2 declares one bomb
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
                     ship_id="drifter")
    assert bare.pickups == ()
    assert Flight(ForceField(), SHIP, bare).pickups == ()


def test_random_pickups_on_route_and_unstacked():
    from vector_drift.level_presets import get_preset, RandomPreset
    from vector_drift.physics import segment_hits_circle
    from vector_drift.random_level import generate_with_corridor, place_pickups
    import random as _random

    # PRESET_8 has pickup_groups; PRESET_7 is () so use a custom preset with
    # bombs to actually exercise on-route + unstacked placement.
    preset = RandomPreset(
        level_id=99, name="PickupTest",
        pickup_groups=(("bomb", 2, 0.45),),
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
                         groups=(("bomb", 1, 0.45),)) == ()


def test_pickup_groups_config_driven():
    # Random pickups fully driven by level_presets.py: () = none, and a new
    # kind only needs a group entry (+ its effect/painter elsewhere).
    import random as _random
    from vector_drift.level_presets import RandomPreset
    from vector_drift.random_level import place_pickups as _place

    preset = RandomPreset(level_id=98, name="Groups", num_obstacles=0,
                          num_direct_blockers=0,
                          pickup_groups=(("bomb", 1, 0.45), ("bomb", 2, 0.3)))
    rng = _random.Random(3)
    start, target = (-7.0, 0.0), (7.0, 0.0)
    out = _place(rng, [(start, target)], start, target, placed=(),
                 preset=preset)
    assert len(out) <= 3 and {p.kind for p in out} <= {"bomb"}

    empty = RandomPreset(level_id=97, name="NoPickups", num_obstacles=0,
                         num_direct_blockers=0, pickup_groups=())
    assert _place(_random.Random(3), [(start, target)], start, target,
                  placed=(), preset=empty) == ()


def test_consumed_pickups_persist_across_launches():
    # Same PickupState objects shared across Flights (like GameScene does):
    # once consumed, later launches see it gone -- until lives run out.
    bomb = PickupSpec(center=(0.0, 0.0), radius=5.0, kind="bomb")
    level = _level_with([], [bomb], start=(0.0, 0.0))
    shared = [PickupState.from_spec(s) for s in level.pickups]
    first = Flight(ForceField(), SHIP, level, pickups=shared)
    first.step()
    assert shared[0].consumed and any(e["kind"] == "bomb" for e in first.pickup_events)
    second = Flight(ForceField(), SHIP, level, pickups=shared)
    second.step()
    assert [e for e in second.pickup_events if e["kind"] == "bomb"] == []


def test_add_time_effect_reports_duration():
    pickup = PickupState((0.0, 0.0), 0.45, "add_time")
    event = add_time_effect(pickup, None)
    assert event == {
        "kind": "add_time",
        "center": (0.0, 0.0),
        "add_time_duration": ADD_TIME_DURATION,
    }


def test_penetrate_effect_reports_duration():
    pickup = PickupState((0.0, 0.0), 0.45, "penetrate")
    # Pure effect: works without a Flight (ctx=None), never mutates ctx.
    event = penetrate_effect(pickup, None)
    assert event == {
        "kind": "penetrate",
        "center": (0.0, 0.0),
        "penetrate_duration": PENETRATE_DURATION,
    }
    assert not hasattr(pickup, "_mutated_ctx")


# --- add_time / penetrate applied to the Flight itself ------------------------
# The same rules must hold for GameScene and the solver, so these drive the
# shared path (Flight.step) rather than any one caller's copy of the logic.

def _add_time_level():
    """Ship parked on an add_time pickup with no force: it can only time out."""
    return LevelSpec(id=902, name="Add time", start=(-7.0, 0.0),
                     target_center=(7.0, 0.0), target_radius=1.0,
                     ship_id="drifter", time_limit=4.0,
                     pickups=(PickupSpec(center=(-7.0, 0.0), kind="add_time"),))


def test_add_time_extends_the_flight_itself():
    flight = Flight(ForceField(), SHIP, _add_time_level())
    while flight.running:
        flight.step()
    assert flight.outcome is Outcome.TIMEOUT
    assert flight.time == pytest.approx(4.0 + ADD_TIME_DURATION)


def test_solver_flight_gets_the_extended_time():
    from vector_drift.solver import EvalConfig, SimulationOutcome, evaluate_candidate, get_template
    template = get_template("general_poly")              # all-zero defaults: no force
    params = dict(zip(template.param_names, template.param_defaults))
    result = evaluate_candidate(level=_add_time_level(), template=template, params=params,
                                config=EvalConfig(record_trajectory=False))
    assert result.record.outcome == SimulationOutcome.TIMEOUT
    assert result.record.time == pytest.approx(4.0 + ADD_TIME_DURATION)


def test_game_scene_flight_gets_the_extended_time_once(pygame_display):
    from types import SimpleNamespace
    from vector_drift.scenes.base import SceneManager
    from vector_drift.scenes.game import GameScene
    audio = SimpleNamespace(play=lambda *a: None, start_loop=lambda *a: None,
                            stop_loop=lambda *a: None)
    scene = GameScene(SceneManager(audio))
    scene.level = _add_time_level()
    scene.pickups = [PickupState.from_spec(s) for s in scene.level.pickups]
    scene.launch_pos = scene.level.start
    scene.editor.set_lines(["0", "0"])
    scene._try_launch()
    flight = scene.flight
    while scene.flight is flight:
        scene.update(1 / 60)
    assert flight.outcome is Outcome.TIMEOUT
    assert flight.time == pytest.approx(4.0 + ADD_TIME_DURATION)


def test_penetrate_passes_one_bumper_then_collisions_return():
    # Constant push to the right, x(t) = -7 + t^2 / 4. The ship takes the
    # pickup at t ~ 1.41 s (effect until ~4.41 s), is inside bumper A from
    # ~3.03 s to ~3.85 s, and reaches bumper B at ~5.02 s: after the effect
    # has ended, with the ship fully outside A the whole time in between.
    hull = SHIP.hull_radius
    bumper_a = ObstacleSpec(center=(-4.0, 0.0), radius=0.5)
    bumper_b = ObstacleSpec(center=(0.0, 0.0), radius=0.5)
    pickup = PickupSpec(center=(-6.0, 0.0), radius=0.3, kind="penetrate")
    flight = Flight(ForceField(c=0.5), SHIP, _level_with([bumper_a, bumper_b], [pickup]))

    def clear_of(bumper):
        return math.dist((flight.x, flight.y), bumper.center) > bumper.radius + hull

    # 1) Through A without a bounce while the effect is active.
    while flight.running and flight.x < bumper_a.center[0] + bumper_a.radius + hull:
        flight.step()
    assert flight.bounces == 0
    assert flight.penetrate_remaining > 0.0

    # 2) The effect runs out between the bumpers, touching neither.
    while flight.running and flight.penetrate_remaining > 0.0:
        flight.step()
    assert flight.bounces == 0
    assert clear_of(bumper_a) and clear_of(bumper_b)

    # 3) Collisions are back: B bounces the ship, which is entirely outside A.
    while flight.running and flight.bounces == 0:
        flight.step()
    assert flight.bounces == 1
    assert flight.vx < 0.0
    assert clear_of(bumper_a)
    assert math.dist((flight.x, flight.y), bumper_b.center) < bumper_b.radius + hull + 0.1
