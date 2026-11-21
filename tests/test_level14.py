"""Level 14 Boomerang: chapter two's finale, the abs switch with everything before it.

Three sections, two checkpoints; the pans go up (0, 13), then up and to the
right (16, 13). Section 1 loops outside the map with Unbound and a switch
that only pushes up past the right edge, section 2 needs both the Shockwave
and the Shield, section 3 combines a wormhole, a Shield and a switch at x = -2.
"""

import dataclasses

import pytest

from vector_drift import config
from vector_drift.data import (LEVELS, SHIPS, LevelSpec, all_levels, get_level, section_count,
                               section_level, section_shift)
from vector_drift.expr_parser import parse_expression
from vector_drift.level_presets import is_dynamic_level
from vector_drift.physics import Flight, ForceField, Outcome
from vector_drift.pickups import discs_overlap

LEVEL = get_level(14)
SHIP = SHIPS[LEVEL.ship_id]
HULL = SHIP.hull_radius
ROCK_R = 0.8
PICKUP_R = 0.45

ROW = (-9.6, -8.0, -6.4, -4.8, -3.2, -1.6, 0.0, 1.6, 3.2, 4.8, 6.4, 8.0, 9.6)
STARTS = ((-8.0, -6.5), (-7.0, -7.0), (-8.0, -6.5))
TARGETS = ((-7.0, 6.0), (8.0, 6.5), (7.0, 6.0))
ROCKS = (
    tuple((x, -4.8) for x in ROW) + ((3.5, -1.5), (2.5, 4.25), (-3.75, 4.5)),
    tuple((x, -2.0) for x in ROW) + tuple((4.0, y) for y in (-0.4, 1.2, 2.8, 4.4, 6.0, 7.5)),
    tuple((-2.0, y) for y in (-7.5, -6.0, -4.5, -3.0, -1.5, 0.0, 1.5, 3.0, 4.5, 6.0, 7.5))
    + tuple((x, 2.0) for x in (5.0, 6.7, 8.4, 10.1))
    + tuple((5.0, y) for y in (3.1, 5.0, 6.9)),
)
UNBOUND = (3.0, -6.5)
SHOCKWAVE = (-6.0, -3.5)
SHIELD_2 = (1.5, 3.1)
SHIELD_3 = (3.0, 2.2)
BLACK_HOLE, WHITE_HOLE, HOLE_R = (-8.0, 2.0), (1.0, -4.0), 0.5
SECTION_IDS = ["section1", "section2", "section3"]


def section(index):
    return section_level(LEVEL, index)


# --- layout -----------------------------------------------------------------------
def test_level_fourteen_is_a_fixed_three_section_level():
    assert isinstance(LEVEL, LevelSpec) and LEVEL in LEVELS
    assert LEVEL.name == "Boomerang"
    assert not is_dynamic_level(14)
    assert section_count(LEVEL) == 3
    assert LEVEL.lives == 5
    for k in range(3):
        s = section(k)
        assert s.target_radius == 1.0
        assert s.time_limit == 10.0
        assert all(o.radius == ROCK_R for o in s.obstacles)
        assert all(p.radius == PICKUP_R for p in s.pickups)
        assert not [p for p in s.pickups if p.kind == "money"]       # no coins


@pytest.mark.parametrize("index", [0, 1, 2], ids=SECTION_IDS)
def test_start_target_and_rocks_match_the_plan(index):
    s = section(index)
    assert s.start == STARTS[index]
    assert s.target_center == TARGETS[index]
    assert len(s.obstacles) == len(ROCKS[index])
    assert {o.center for o in s.obstacles} == set(ROCKS[index])


def test_section_one_has_only_the_unbound():
    s = section(0)
    assert s.holes == ()
    assert [(p.kind, p.center, p.radius) for p in s.pickups] == [("unbound", UNBOUND, PICKUP_R)]


def test_section_two_has_only_the_shockwave_and_the_shield():
    s = section(1)
    assert s.holes == ()
    assert sorted((p.kind, p.center, p.radius) for p in s.pickups) == [
        ("shield", SHIELD_2, PICKUP_R), ("shockwave", SHOCKWAVE, PICKUP_R)]


def test_section_three_has_only_the_shield_and_the_wormhole():
    s = section(2)
    assert [(p.kind, p.center, p.radius) for p in s.pickups] == [("shield", SHIELD_3, PICKUP_R)]
    (hole,) = s.holes
    assert (hole.black_center, hole.white_center, hole.radius) == (BLACK_HOLE, WHITE_HOLE, HOLE_R)


def test_the_pans_go_up_then_up_and_to_the_right():
    # World: (-8, -6.5) -> (-7, 6) -> (8, 19.5) -> (23, 32).
    assert section_shift(LEVEL, 0) == (0.0, 13.0)
    assert section_shift(LEVEL, 1) == (16.0, 13.0)


def _things(s):
    yield "start", s.start, 0.0
    yield "target", s.target_center, s.target_radius
    for p in s.pickups:
        yield f"{p.kind} {p.center}", p.center, p.radius
    for h in s.holes:
        yield "black hole", h.black_center, h.radius
        yield "white hole", h.white_center, h.radius


@pytest.mark.parametrize("index", [0, 1, 2], ids=SECTION_IDS)
def test_nothing_sits_in_a_rock(index):
    s = section(index)
    for name, center, radius in _things(s):
        for rock in s.obstacles:
            assert not discs_overlap(center, radius, rock.center, rock.radius + HULL), (name, rock.center)


def test_level_select_lists_level_fourteen():
    cards = {lv.id: lv for lv in all_levels()}
    assert cards[14] is LEVEL


def test_level_fourteen_gives_its_xp():
    assert config.XP_FIXED_LEVEL_BASE[14] == 360


# --- reference answers and near misses --------------------------------------------------
# Section 1: a spring toward x = 4, and a push up only outside the right edge (x > 10).
C1 = ("4 - x", "0.25((x - 10) + abs(x - 10))")
# Section 2: straight up through the Shockwave, then bending right through the Shield.
C2 = ("y + 7", "2")
# Section 3: no sideways force left of the wall at x = -2, a push right past it.
C3 = ("(x + 2) + abs(x + 2)", "3")
ANSWERS = (C1, C2, C3)
TIMES = (5.89, 3.60, 3.42)
NEAR_MISSES = [
    ("0", "5"),
    ("5", "5"),
    ("3", "3"),
    ("-x", "2"),
    ("4 - x", "0"),          # the spring without the switch
    ("-2x + 8", "1"),        # a linear shortcut
    ("y", "-x"),             # a swirl
]


def _fly(level, fx, fy):
    field = ForceField.from_exprs(parse_expression(fx), parse_expression(fy))
    flight = Flight(field, SHIP, level)
    while flight.running:
        flight.step()
    return flight


def _events(flight):
    return [event.get("kind") for event in flight.pickup_events]


def _lift(c):
    return "4 - x", f"{c:g}((x - 10) + abs(x - 10))"


def _bend(c=1, f=3):
    fx = "(x + 2) + abs(x + 2)" if c == 1 else f"{c:g}((x + 2) + abs(x + 2))"
    return fx, f"{f:g}"


def _without(s, *kinds):
    return dataclasses.replace(s, pickups=tuple(p for p in s.pickups if p.kind not in kinds))


def test_the_helpers_write_the_reference_answers():
    assert _lift(0.25) == C1
    assert _bend() == C3


@pytest.mark.parametrize("index", [0, 1, 2], ids=SECTION_IDS)
def test_each_reference_answer_reaches_without_a_bounce(index):
    flight = _fly(section(index), *ANSWERS[index])
    assert flight.outcome is Outcome.REACHED
    assert flight.bounces == 0
    assert flight.time == pytest.approx(TIMES[index], abs=0.05)


def test_section_one_takes_the_unbound():
    assert "unbound" in _events(_fly(section(0), *C1))


def test_section_two_takes_the_shockwave_and_the_shield_and_uses_it():
    events = _events(_fly(section(1), *C2))
    assert "shockwave" in events
    assert "shield" in events and "shield_used" in events


def test_section_three_goes_through_the_wormhole_and_uses_the_shield():
    flight = _fly(section(2), *C3)
    assert flight.teleports == 1
    events = _events(flight)
    assert "shield" in events and "shield_used" in events


@pytest.mark.parametrize("index", [0, 1, 2], ids=SECTION_IDS)
@pytest.mark.parametrize("answer", [0, 1, 2], ids=["C1", "C2", "C3"])
def test_only_its_own_answer_clears_a_section(index, answer):
    outcome = _fly(section(index), *ANSWERS[answer]).outcome
    assert (outcome is Outcome.REACHED) == (answer == index)


@pytest.mark.parametrize("index", [0, 1, 2], ids=SECTION_IDS)
@pytest.mark.parametrize("field", NEAR_MISSES, ids=lambda f: f"({f[0]}, {f[1]})")
def test_constant_linear_and_swirl_fields_do_not_clear_a_section(index, field):
    assert _fly(section(index), *field).outcome is not Outcome.REACHED


def test_section_one_needs_the_unbound():
    assert _fly(_without(section(0), "unbound"), *C1).outcome is not Outcome.REACHED


@pytest.mark.parametrize("kind", ["shockwave", "shield"])
def test_section_two_needs_both_pickups(kind):
    assert _fly(_without(section(1), kind), *C2).outcome is not Outcome.REACHED


def test_section_three_needs_the_shield():
    assert _fly(_without(section(2), "shield"), *C3).outcome is not Outcome.REACHED


def test_section_three_needs_the_wormhole():
    bare = dataclasses.replace(section(2), holes=())
    assert _fly(bare, *C3).outcome is not Outcome.REACHED


@pytest.mark.parametrize("c", [0.23, 0.24, 0.25, 0.26])
def test_section_one_takes_a_narrow_range_of_lifts(c):
    assert _fly(section(0), *_lift(c)).outcome is Outcome.REACHED


@pytest.mark.parametrize("c", [0.2, 0.3])
def test_section_one_misses_with_too_weak_or_too_strong_a_lift(c):
    assert _fly(section(0), *_lift(c)).outcome is not Outcome.REACHED


@pytest.mark.parametrize("field", [("2y + 14", "4"), ("0.5(y + 7)", "1")],
                         ids=lambda f: f"({f[0]}, {f[1]})")
def test_section_two_only_minds_the_ratio(field):
    assert _fly(section(1), *field).outcome is Outcome.REACHED


@pytest.mark.parametrize("fy", ["1.6", "2.4"])
def test_section_two_misses_with_the_ratio_off(fy):
    assert _fly(section(1), "y + 7", fy).outcome is not Outcome.REACHED


@pytest.mark.parametrize("c, f", [(1, 2.6), (1, 3.4), (0.8, 3)])
def test_section_three_takes_a_range_of_pushes(c, f):
    assert _fly(section(2), *_bend(c, f)).outcome is Outcome.REACHED


def test_section_three_misses_with_too_strong_a_push_right():
    assert _fly(section(2), *_bend(1.2, 3)).outcome is not Outcome.REACHED


# --- the game: two checkpoints, a pan up then a diagonal pan, win; the answer is paid once ---
def _scene():
    from types import SimpleNamespace

    from vector_drift.scenes.base import SceneManager
    from vector_drift.scenes.game import GameScene

    audio = SimpleNamespace(play=lambda *a, **k: None, start_loop=lambda *a, **k: None,
                            stop_loop=lambda *a, **k: None)
    manager = SceneManager(audio)
    manager.session.level_id = 14
    scene = GameScene(manager)
    manager.switch(scene)
    return manager, scene


def _type(scene, fx, fy):
    scene.editor.set_lines([fx, fy])
    scene._on_text_change(scene.editor)


def _launch(scene, surface, answer, pans=None):
    """Fly ``answer`` through any pan that follows; the state it ends in.

    Every pan seen is appended to ``pans`` as (pan, offsets at each frame).
    """
    from vector_drift.scenes.game import FLIGHT, PANNING
    from vector_drift.scenes.game_layout import pan_offsets

    _type(scene, *answer)
    scene._try_launch()
    while scene.state == FLIGHT:
        scene.update(0.05)
        scene.draw(surface)
    reached = scene.state
    frames = []
    pan = scene.pan
    while scene.state == PANNING:
        frames.append(pan_offsets(pan.shift, pan.progress))
        scene.update(0.05)
        scene.draw(surface)
    if pans is not None and frames:
        pans.append((pan, frames))
    return reached


def _check_pan(pan, frames, k):
    """The pan after section k + 1 moves by its shift and holds the checkpoint in place."""
    import math

    assert pan.shift == section_shift(LEVEL, k)
    assert math.dist(pan.arrival, TARGETS[k]) <= 1.0 + HULL       # touched the checkpoint
    assert len(frames) > 2
    assert frames[0][0] == pytest.approx((0.0, 0.0))            # starts on the old section
    assert frames[-1][1] == pytest.approx((0.0, 0.0), abs=0.5)  # ends on the new one
    for old_offset, new_offset in frames:
        old_checkpoint = (TARGETS[k][0] + old_offset[0], TARGETS[k][1] + old_offset[1])
        new_start = (STARTS[k + 1][0] + new_offset[0], STARTS[k + 1][1] + new_offset[1])
        assert old_checkpoint == pytest.approx(new_start)


@pytest.mark.usefixtures("pygame_display")
def test_level_fourteen_plays_through_two_checkpoints_to_the_win():
    import pygame

    from vector_drift.scenes.game import ARRIVED, PANNING, SETUP

    _, scene = _scene()
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    assert scene.section_index == 0 and scene.lives == LEVEL.lives
    pans = []

    # Each section: a miss off the map costs a life and relaunches from this
    # section's start (a time-up would resume where the ship stopped instead);
    # its own answer reaches the checkpoint, which gives the life back.
    for k, miss in ((0, ("5", "5")), (1, C1)):
        assert _launch(scene, surface, miss) == SETUP
        assert scene.section_index == k and scene.lives == LEVEL.lives - 1
        assert tuple(scene.launch_pos) == STARTS[k]
        assert _launch(scene, surface, ANSWERS[k], pans) == PANNING
        assert scene.section_index == k + 1 and scene.lives == LEVEL.lives
        assert tuple(scene.launch_pos) == STARTS[k + 1]
        assert scene.pan is None                                    # settled on the next section

    # The camera went up, then up and to the right.
    (up, up_frames), (diagonal, diagonal_frames) = pans
    _check_pan(up, up_frames, 0)
    _check_pan(diagonal, diagonal_frames, 1)
    assert up.shift == (0.0, 13.0) and diagonal.shift == (16.0, 13.0)

    # Section 3: section 2's answer misses; the switch at x = -2 takes the
    # wormhole and the Shield into the planet.
    assert _launch(scene, surface, C2) == SETUP
    assert scene.section_index == 2 and scene.lives == LEVEL.lives - 1
    assert tuple(scene.launch_pos) == STARTS[2]
    assert _launch(scene, surface, C3) == ARRIVED
    assert scene.section_index == 2


@pytest.mark.usefixtures("pygame_display")
def test_reaching_a_checkpoint_at_full_lives_keeps_the_cap():
    import pygame

    from vector_drift.scenes.game import PANNING

    _, scene = _scene()
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    for k in (0, 1):
        assert scene.lives == LEVEL.lives
        assert _launch(scene, surface, ANSWERS[k]) == PANNING
        assert scene.section_index == k + 1 and scene.lives == LEVEL.lives


@pytest.mark.xfail(reason="level 14 hints pending", strict=True)
@pytest.mark.usefixtures("pygame_display")
def test_level_fourteen_answer_is_paid_once_for_all_three_sections():
    import pygame

    from vector_drift.scenes.game import PANNING

    assert 14 not in config.FREE_ANSWER_LEVELS
    manager, scene = _scene()
    manager.session.money.add(25)
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    scene.draw(surface)

    def open_answer():
        scene._open_hint()
        popup = scene.hint_popup
        while popup.page < popup.answer_page - 1:
            popup.page += 1
        scene._request_hint_answer()
        return popup

    # Section 1: asked first, with the price; paying shows the answer page.
    popup = open_answer()
    assert popup.confirming and popup.confirm_price is not None
    scene._show_hint_answer(config.HINT_ANSWER_COST)
    assert popup.on_answer_page
    assert int(manager.session.money) == 25 - config.HINT_ANSWER_COST
    assert 14 in manager.session.paid_answer_levels

    # Sections 2 and 3: each one's own answer page opens straight away, at no charge.
    for answer, section_number in ((C1, 2), (C2, 3)):
        assert _launch(scene, surface, answer) == PANNING
        assert scene.section_index == section_number - 1
        popup = open_answer()
        assert popup.on_answer_page and not popup.confirming
        assert popup.hint is scene.hint and scene.hint.section == section_number
        assert int(manager.session.money) == 25 - config.HINT_ANSWER_COST
