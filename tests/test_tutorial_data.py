"""tutorial.toml: its format, and every map flown by the real engine.

The expected results are the ones written in the tutorial spec (ship01,
1 kg, dt = 1/120 s): each check flies the map from the data file with the
game's own Flight and compares.
"""

import math
from dataclasses import replace

import pytest

from vector_drift import config
from vector_drift.data_models import SHIPS
from vector_drift.physics import Flight, Outcome
from vector_drift.tutorial import (NO_TARGET, TUTORIAL_LEVEL_ID, TutorialFormatError, force_field,
                                   parse_tutorial, tutorial)

SHIP = SHIPS["ship01"]


def fly(level, force, start=None, cap=None, watch=None):
    """Fly ``level`` with ``force`` until it ends or ``cap`` seconds pass."""
    flight = Flight(force_field(force), SHIP, level, start=start)
    limit = round(cap / flight.dt) if cap else 10 ** 7
    while flight.running and flight.steps < limit:
        before = (flight.x, flight.y, flight.vx, flight.vy)
        flight.step()
        if watch:
            watch(flight, before)
    return flight


def step(n):
    return tutorial().basics[n - 1]


def item(name):
    for cat in tutorial().guide:
        for it in cat.items:
            if it.name == name:
                return it
    raise KeyError(name)


# --- format -------------------------------------------------------------------
def test_ship_is_the_one_the_spec_was_flown_with():
    assert SHIP.mass == 1.0 and config.DT == pytest.approx(1 / 120)


def test_basics_has_four_steps_in_order():
    assert [s.kind for s in tutorial().basics] == ["play", "demo", "demo", "card"]
    assert [s.title for s in tutorial().basics] == ["Fly home", "Time's up", "Out of bounds", "Help"]


def test_guide_categories_and_items():
    guide = tutorial().guide
    assert [c.name for c in guide] == ["Obstacles", "Portals", "Pickups"]
    assert [i.name for i in guide[2].items] == ["Shockwave", "Extratime", "Unbound", "Shield"]
    assert len(item("Shield").parts) == 2


def test_no_ability_in_the_guide():
    names = {i.name for c in tutorial().guide for i in c.items}
    assert not names & {"Boost", "Shield Pulse", "Magnet", "Time Freeze"}


def test_texts_match_the_spec():
    assert step(1).placeholders == ("5", "0")
    assert step(1).success == "Home! Reach the planet to clear a level."
    assert "Type **Fx = 5** and **Fy = 0**, then press the green **Play** button" in step(1).text
    assert step(2).beats[1].text == "It flew on from where it stopped."
    assert step(3).beats[0].text == "Out of bounds. The ship left the map."
    assert step(4).button == "Start playing" and step(4).point == "hint"
    assert item("Shockwave").parts[0].text == "Blasts every rock within 3 m."
    assert item("Extratime").parts[0].show_timer


def test_maps_are_ordinary_tutorial_levels():
    level = step(1).map.level()
    assert level.id == TUTORIAL_LEVEL_ID and level.ship_id == "ship01"
    assert level.start == (-7.0, 0.0) and level.target_center == (7.0, 0.0)
    guide_level = item("Rock").parts[0].map.level()
    assert not item("Rock").parts[0].map.has_target
    assert guide_level.target_center == NO_TARGET


def test_tutorial_level_id_is_not_a_game_level():
    from vector_drift.data import all_levels, is_custom_map
    from vector_drift.hints import get_hint
    from vector_drift.level_presets import is_dynamic_level
    assert TUTORIAL_LEVEL_ID not in {lv.id for lv in all_levels()}
    assert not is_dynamic_level(TUTORIAL_LEVEL_ID) and not is_custom_map(TUTORIAL_LEVEL_ID)
    assert get_hint(TUTORIAL_LEVEL_ID) is None


@pytest.mark.parametrize("data, message", [
    ({"basics": {"step": []}, "guide": {}}, "basics step"),
    ({"basics": {"step": [{"kind": "fly"}]}, "guide": {}}, "'kind'"),
    ({"extra": 1}, "unknown keys"),
])
def test_bad_files_are_reported(data, message):
    with pytest.raises(TutorialFormatError, match=message):
        parse_tutorial(data)


def test_a_bad_force_is_reported():
    data = {"basics": {"step": [{"kind": "demo", "title": "t", "force": ["1 +", "0"],
                                 "map": {"start": [0, 0]},
                                 "beat": [{"launch": True, "text": "x"}]}]}}
    with pytest.raises(TutorialFormatError, match="force"):
        parse_tutorial(data)


# --- Basics, flown ------------------------------------------------------------------
def test_basics_1_fx5_reaches_the_planet():
    flight = fly(step(1).map.level(), ("5", "0"))
    assert flight.outcome is Outcome.REACHED
    assert flight.time == pytest.approx(2.3, abs=0.05)


def test_basics_2_times_out_then_flies_on_from_there():
    s = step(2)
    assert s.force == ("1", "0") and s.map.time_limit == 4.0
    first = fly(s.map.level(), s.force)
    assert first.outcome is Outcome.TIMEOUT and first.time == pytest.approx(4.0)
    assert first.x == pytest.approx(1.02, abs=0.01) and first.y == pytest.approx(0.0)
    second = fly(s.map.level(), s.force, start=(first.x, first.y))
    assert second.outcome is Outcome.REACHED
    assert second.time == pytest.approx(3.1, abs=0.05)


def test_basics_3_goes_out_of_bounds_at_the_top():
    s = step(3)
    assert s.force == ("0", "5") and s.map.time_limit == 10.0
    flight = fly(s.map.level(), s.force)
    assert flight.outcome is Outcome.OUT_OF_BOUNDS
    assert flight.time == pytest.approx(1.73, abs=0.02)
    assert flight.y > config.WORLD_HALF_H


# --- Field guide, flown -------------------------------------------------------------
def test_rock_bounces_the_ship_upward():
    part = item("Rock").parts[0]
    hits = []
    flight = fly(part.map.level(), part.force, cap=part.cap,
                 watch=lambda f, b: hits.append((f.time, b[3], f.vy)) if f.bounces and not hits else None)
    assert flight.running and part.cap == 2.3
    t, vy_before, vy_after = hits[0]
    assert t == pytest.approx(1.6, abs=0.05)
    assert vy_after > 0 >= vy_before - 1e-9               # pushed up off the rock's top half
    free = fly(part.map.level(), part.force)
    assert free.outcome is Outcome.OUT_OF_BOUNDS and free.time == pytest.approx(2.53, abs=0.02)


def test_rock_bounce_keeps_the_speed():
    part = item("Rock").parts[0]
    speeds = []

    def watch(f, before):
        if f.bounces and not speeds:
            speeds.append((math.hypot(before[2], before[3]), math.hypot(f.vx, f.vy)))
    fly(part.map.level(), part.force, cap=part.cap, watch=watch)
    before, after = speeds[0]
    assert after == pytest.approx(before, rel=0.03)


def test_holes_teleport_at_the_same_speed():
    part = item("Black / white hole").parts[0]
    seen = []

    def watch(f, before):
        if f.teleports and not seen:
            seen.append((before, (f.x, f.y, f.vx, f.vy)))
    flight = fly(part.map.level(), part.force, cap=part.cap, watch=watch)
    assert flight.running and flight.teleports == 1 and flight.bounces == 0
    (bx, _by, bvx, bvy), (ax, _ay, avx, avy) = seen[0]
    assert bx < -2.5 and ax > 2.5                         # jumped from x = -3 to x = 3
    assert math.hypot(avx, avy) == pytest.approx(math.hypot(bvx, bvy), rel=0.02)
    assert flight.trail_breaks                            # the trail is not joined


def test_shockwave_clears_the_near_rocks_only():
    part = item("Shockwave").parts[0]
    flight = fly(part.map.level(), part.force, cap=part.cap)
    assert flight.running and flight.bounces == 0
    assert [o.center for o in flight.obstacle_specs] == [(5.5, 2.5)]
    assert flight.x > 2.2 and flight.y == pytest.approx(0.0)   # flew over (2.2, 0)
    assert any(e["kind"] == "shockwave" for e in flight.pickup_events)


def test_extratime_adds_three_seconds():
    part = item("Extratime").parts[0]
    level = part.map.level()
    assert level.time_limit == 3.0 and part.cap == 3.5
    flight = fly(level, part.force, cap=part.cap)
    assert flight.running                                 # still flying past the old 3 s
    assert flight.max_steps * flight.dt == pytest.approx(6.0)
    assert [e["kind"] for e in flight.pickup_events] == ["extratime"]


def test_unbound_flies_past_the_top_edge():
    part = item("Unbound").parts[0]
    flight = fly(part.map.level(), part.force, cap=part.cap)
    assert flight.running and flight.unbound
    assert flight.outcome is not Outcome.OUT_OF_BOUNDS
    assert flight.y > config.WORLD_HALF_H


def test_shield_passes_through_one_rock():
    part = item("Shield").parts[0]
    ys = []

    def watch(f, before):
        if before[0] < 0 <= f.x:
            ys.append(f.y)
    flight = fly(part.map.level(), part.force, cap=part.cap, watch=watch)
    assert flight.running and flight.bounces == 0
    assert ys and ys[0] == pytest.approx(0.0)
    assert flight.vy == pytest.approx(0.0)


def test_shield_bounces_off_the_map_edge_once():
    part = item("Shield").parts[1]
    flips = []

    def watch(f, before):
        if before[3] > 0 >= f.vy:
            flips.append((f.time, f.y))
    flight = fly(part.map.level(), part.force, cap=part.cap, watch=watch)
    assert flight.running
    assert len(flips) == 1
    assert flips[0][0] == pytest.approx(1.7, abs=0.05)
    assert flips[0][1] > config.WORLD_HALF_H - 0.5        # at the top edge
    bare = replace(part.map.level(), pickups=())
    no_shield = fly(bare, part.force)
    assert no_shield.outcome is Outcome.OUT_OF_BOUNDS and no_shield.time == pytest.approx(1.7, abs=0.05)
