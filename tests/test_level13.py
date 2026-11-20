"""Level 13 Change of Course: the abs switch on the y axis, and the first change of pan direction.

Three sections, two checkpoints; the pans go up (0, 13), then right (16, 0).
y + abs(y) is 0 below y = 0 and 2y above it; -y + abs(y) is the other way
round. Section 1 crosses a wall by wormhole with the switch at y = 0,
section 2 moves the switch to y = -1 and needs the Shockwave, section 3
reviews level 10's swirl, flipped, with the Shield.
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

LEVEL = get_level(13)
SHIP = SHIPS[LEVEL.ship_id]
HULL = SHIP.hull_radius
ROCK_R = 0.8
PICKUP_R = 0.45

STARTS = ((6.0, -6.0), (-1.5, -6.5), (-8.0, 4.5))
TARGETS = ((-1.5, 6.5), (8.0, 4.5), (5.5, -4.5))
ROCKS = (
    tuple((x, 0.0) for x in (-9.6, -8.0, -6.4, -4.8, -3.2, -1.6, 0.0, 1.6, 3.2, 4.8, 6.4, 8.0, 9.6)),
    tuple((2.5, y) for y in (-4.7, -3.1, -1.5, 0.1, 1.7, 3.3, 4.9, 6.5))
    + tuple((0.0, y) for y in (-4.7, -3.1, -1.5))
    + tuple((x, -4.7) for x in (-4.8, -3.2, 4.1, 5.0)),
    tuple((x, -1.0) for x in (1.0, 2.5, 4.0, 5.5, 7.0, 8.5, 10.0))
    + tuple((1.0, y) for y in (-2.5, -4.0, -5.5, -7.0)),
)
BLACK_HOLE, WHITE_HOLE, HOLE_R = (6.0, -2.5), (4.0, 2.0), 0.5
SHOCKWAVE = (-0.5, 1.6)
SHIELD = (-1.0, 4.5)
SECTION_IDS = ["section1", "section2", "section3"]


def section(index):
    return section_level(LEVEL, index)


# --- layout -----------------------------------------------------------------------
def test_level_thirteen_is_a_fixed_three_section_level():
    assert isinstance(LEVEL, LevelSpec) and LEVEL in LEVELS
    assert LEVEL.name == "Change of Course"
    assert not is_dynamic_level(13)
    assert section_count(LEVEL) == 3
    assert LEVEL.lives == 5
    for k in range(3):
        s = section(k)
        assert s.target_radius == 1.0
        assert s.time_limit == 10.0
        assert all(o.radius == ROCK_R for o in s.obstacles)
        assert not [p for p in s.pickups if p.kind == "money"]       # no coins


@pytest.mark.parametrize("index", [0, 1, 2], ids=SECTION_IDS)
def test_start_target_and_rocks_match_the_plan(index):
    s = section(index)
    assert s.start == STARTS[index]
    assert s.target_center == TARGETS[index]
    assert len(s.obstacles) == len(ROCKS[index])
    assert {o.center for o in s.obstacles} == set(ROCKS[index])


def test_section_one_has_only_the_wormhole():
    s = section(0)
    assert s.pickups == ()
    (hole,) = s.holes
    assert (hole.black_center, hole.white_center, hole.radius) == (BLACK_HOLE, WHITE_HOLE, HOLE_R)


def test_section_two_has_only_the_shockwave():
    s = section(1)
    assert s.holes == ()
    assert [(p.kind, p.center, p.radius) for p in s.pickups] == [("shockwave", SHOCKWAVE, PICKUP_R)]


def test_section_three_has_only_the_shield():
    s = section(2)
    assert s.holes == ()
    assert [(p.kind, p.center, p.radius) for p in s.pickups] == [("shield", SHIELD, PICKUP_R)]


def test_the_pans_go_up_then_to_the_right():
    # World: (6, -6) -> (-1.5, 6.5) -> (8, 17.5) -> (21.5, 8.5).
    assert section_shift(LEVEL, 0) == (0.0, 13.0)
    assert section_shift(LEVEL, 1) == (16.0, 0.0)


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


def test_level_select_lists_level_thirteen():
    cards = {lv.id: lv for lv in all_levels()}
    assert cards[13] is LEVEL


def test_level_thirteen_gives_its_xp():
    assert config.XP_FIXED_LEVEL_BASE[13] == 340


# --- reference answers and near misses --------------------------------------------------
# Section 1: a spring toward y = 0 below the wall, a push to the left above it.
B1 = ("-4(y + abs(y))", "-y + abs(y)")
# Section 2: the same switch moved to y = -1, pushing to the right above it.
B2 = ("10((y + 1) + abs(y + 1))", "-(y + 1) + abs(y + 1)")
# Section 3: level 10's swirl flipped upside down, clockwise round (-7, 2.5).
B3 = ("y - 2.5", "-x - 7")
ANSWERS = (B1, B2, B3)
TIMES = (1.29, 1.79, 3.51)
NEAR_MISSES = [
    ("0", "5"),
    ("5", "5"),
    ("-3", "5"),
    ("2", "3"),
    ("-x", "6 - y"),
    ("y", "-x"),
]


def _fly(level, fx, fy):
    field = ForceField.from_exprs(parse_expression(fx), parse_expression(fy))
    flight = Flight(field, SHIP, level)
    while flight.running:
        flight.step()
    return flight


def _events(flight):
    return [event.get("kind") for event in flight.pickup_events]


def _push_left(c):
    return f"-{c:g}(y + abs(y))", "-y + abs(y)"


def _push_right(c=10, h=1):
    if h == 0:
        return f"{c:g}(y + abs(y))", "-y + abs(y)"
    y = f"y + {h:g}"
    return f"{c:g}(({y}) + abs({y}))", f"-({y}) + abs({y})"


def test_the_helpers_write_the_reference_answers():
    assert _push_left(4) == B1
    assert _push_right() == B2


@pytest.mark.parametrize("index", [0, 1, 2], ids=SECTION_IDS)
def test_each_reference_answer_reaches_without_a_bounce(index):
    flight = _fly(section(index), *ANSWERS[index])
    assert flight.outcome is Outcome.REACHED
    assert flight.bounces == 0
    assert flight.time == pytest.approx(TIMES[index], abs=0.05)


def test_section_one_goes_through_the_wormhole():
    assert _fly(section(0), *B1).teleports == 1


def test_section_two_takes_the_shockwave():
    assert "shockwave" in _events(_fly(section(1), *B2))


def test_section_three_takes_the_shield_and_uses_it():
    events = _events(_fly(section(2), *B3))
    assert "shield" in events and "shield_used" in events


@pytest.mark.parametrize("index", [0, 1, 2], ids=SECTION_IDS)
@pytest.mark.parametrize("answer", [0, 1, 2], ids=["B1", "B2", "B3"])
def test_only_its_own_answer_clears_a_section(index, answer):
    outcome = _fly(section(index), *ANSWERS[answer]).outcome
    assert (outcome is Outcome.REACHED) == (answer == index)


@pytest.mark.parametrize("index", [0, 1, 2], ids=SECTION_IDS)
@pytest.mark.parametrize("field", NEAR_MISSES, ids=lambda f: f"({f[0]}, {f[1]})")
def test_constant_linear_and_swirl_fields_do_not_clear_a_section(index, field):
    assert _fly(section(index), *field).outcome is not Outcome.REACHED


def test_section_one_needs_the_wormhole():
    bare = dataclasses.replace(section(0), holes=())
    assert _fly(bare, *B1).outcome is not Outcome.REACHED


@pytest.mark.parametrize("index", [1, 2], ids=["section2", "section3"])
def test_sections_two_and_three_need_their_pickup(index):
    bare = dataclasses.replace(section(index), pickups=())
    assert _fly(bare, *ANSWERS[index]).outcome is not Outcome.REACHED


@pytest.mark.parametrize("c", [3, 4, 5, 6, 7])
def test_section_one_takes_a_range_of_push_strengths(c):
    assert _fly(section(0), *_push_left(c)).outcome is Outcome.REACHED


def test_section_one_misses_with_too_weak_a_push():
    assert _fly(section(0), *_push_left(2)).outcome is not Outcome.REACHED


@pytest.mark.parametrize("c", [8, 10, 15, 20])
def test_section_two_takes_a_range_of_push_strengths(c):
    assert _fly(section(1), *_push_right(c=c)).outcome is Outcome.REACHED


@pytest.mark.parametrize("c", [6, 25])
def test_section_two_misses_with_too_weak_or_too_strong_a_push(c):
    assert _fly(section(1), *_push_right(c=c)).outcome is not Outcome.REACHED


@pytest.mark.parametrize("h", [1, 1.5])
def test_section_two_takes_a_range_of_switch_lines(h):
    assert _fly(section(1), *_push_right(h=h)).outcome is Outcome.REACHED


@pytest.mark.parametrize("h", [0, 0.5, 2])
def test_section_two_misses_with_the_switch_too_low_or_too_high(h):
    assert _fly(section(1), *_push_right(h=h)).outcome is not Outcome.REACHED


# --- the game: two checkpoints, a pan up then a pan right, win; the answer is paid once ------
def _scene():
    from types import SimpleNamespace

    from vector_drift.scenes.base import SceneManager
    from vector_drift.scenes.game import GameScene

    audio = SimpleNamespace(play=lambda *a, **k: None, start_loop=lambda *a, **k: None,
                            stop_loop=lambda *a, **k: None)
    manager = SceneManager(audio)
    manager.session.level_id = 13
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
def test_level_thirteen_plays_through_two_checkpoints_to_the_win():
    import pygame

    from vector_drift.scenes.game import ARRIVED, PANNING, SETUP

    _, scene = _scene()
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    assert scene.section_index == 0 and scene.lives == LEVEL.lives
    pans = []

    # Each section: a miss costs a life and relaunches from this section's start;
    # its own answer reaches the checkpoint, which gives the life back.
    for k, miss in ((0, ("0", "5")), (1, B1)):
        assert _launch(scene, surface, miss) == SETUP
        assert scene.section_index == k and scene.lives == LEVEL.lives - 1
        assert tuple(scene.launch_pos) == STARTS[k]
        assert _launch(scene, surface, ANSWERS[k], pans) == PANNING
        assert scene.section_index == k + 1 and scene.lives == LEVEL.lives
        assert tuple(scene.launch_pos) == STARTS[k + 1]
        assert scene.pan is None                                    # settled on the next section

    # The camera went up, then to the right.
    (up, up_frames), (right, right_frames) = pans
    _check_pan(up, up_frames, 0)
    _check_pan(right, right_frames, 1)
    assert up.shift == (0.0, 13.0) and right.shift == (16.0, 0.0)

    # Section 3: section 2's answer misses; the swirl takes the Shield into the planet.
    assert _launch(scene, surface, B2) == SETUP
    assert scene.section_index == 2 and scene.lives == LEVEL.lives - 1
    assert tuple(scene.launch_pos) == STARTS[2]
    assert _launch(scene, surface, B3) == ARRIVED
    assert scene.section_index == 2


@pytest.mark.xfail(reason="level 13 hints pending", strict=True)
@pytest.mark.usefixtures("pygame_display")
def test_level_thirteen_answer_is_paid_once_for_all_three_sections():
    import pygame

    from vector_drift.scenes.game import PANNING

    assert 13 not in config.FREE_ANSWER_LEVELS
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
    assert 13 in manager.session.paid_answer_levels

    # Sections 2 and 3: each one's own answer page opens straight away, at no charge.
    for answer, section_number in ((B1, 2), (B2, 3)):
        assert _launch(scene, surface, answer) == PANNING
        assert scene.section_index == section_number - 1
        popup = open_answer()
        assert popup.on_answer_page and not popup.confirming
        assert popup.hint is scene.hint and scene.hint.section == section_number
        assert int(manager.session.money) == 25 - config.HINT_ANSWER_COST
