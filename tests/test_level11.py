"""Level 11 Off the Map: the first three-section level.

Two checkpoints, both pans to the left. Every section reviews the Unbound and
changes one thing in the previous section's formula: section 1 is level 6's
arch over a wall, section 2 flips it under the same wall, section 3 doubles
the x spring to drop into a box in the top-left corner.
"""

import dataclasses
import math

import pytest

from vector_drift import config
from vector_drift.data import (LEVELS, SHIPS, LevelSpec, all_levels, get_level, section_count,
                               section_level, section_shift)
from vector_drift.expr_parser import parse_expression
from vector_drift.level_presets import is_dynamic_level
from vector_drift.physics import Flight, ForceField, Outcome
from vector_drift.pickups import discs_overlap

LEVEL = get_level(11)
SHIP = SHIPS[LEVEL.ship_id]
HULL = SHIP.hull_radius
ROCK_R = 0.8
UNBOUND_R = 0.45
HALF_W, HALF_H = config.WORLD_HALF_W, config.WORLD_HALF_H

START = (8.0, 0.0)
CHECKPOINT = (-8.0, 0.0)
PLANET = (-8.0, 5.0)
WALL = tuple((0.0, y) for y in (-7.5, -6.0, -4.5, -3.0, -1.5, 0.0, 1.5, 3.0, 4.5, 6.0, 7.5))
# The box round the planet, from the left edge along the bottom and up the right side.
BOX = ((-9.7, 2.6), (-8.2, 2.6), (-6.7, 2.6), (-5.5, 2.6), (-5.5, 4.1), (-5.5, 5.6), (-5.5, 7.1))
UNBOUND_ABOVE = (5.5, 6.3)
UNBOUND_BELOW = (5.5, -6.3)
UNBOUND_BOX = (3.9, 4.7)


def section(index):
    return section_level(LEVEL, index)


# --- layout -----------------------------------------------------------------------
def test_level_eleven_is_a_fixed_three_section_level():
    assert isinstance(LEVEL, LevelSpec) and LEVEL in LEVELS
    assert LEVEL.name == "Off the Map"
    assert not is_dynamic_level(11)
    assert section_count(LEVEL) == 3
    assert LEVEL.lives == 5
    for k in range(3):
        s = section(k)
        assert s.start == START
        assert s.target_radius == 1.0
        assert s.time_limit == 10.0
        assert s.holes == ()
        assert all(o.radius == ROCK_R for o in s.obstacles)
        assert all(p.radius == UNBOUND_R and p.kind == "unbound" for p in s.pickups)


def test_level_eleven_has_no_coins():
    for k in range(3):
        assert not [p for p in section(k).pickups if p.kind == "money"]


def test_both_pans_go_16_m_to_the_left():
    # World x: 8 -> -8 (checkpoint) -> -24 (checkpoint) -> -40 (planet).
    assert section_shift(LEVEL, 0) == section_shift(LEVEL, 1) == (-16.0, 0.0)
    sx, sy = section_shift(LEVEL, 0)
    assert (START[0] + sx, START[1] + sy) == CHECKPOINT      # the checkpoint is the next start


def test_section_one_is_a_wall_with_an_unbound_above():
    s = section(0)
    assert s.target_center == CHECKPOINT
    assert sorted(o.center for o in s.obstacles) == sorted(WALL)
    assert [p.center for p in s.pickups] == [UNBOUND_ABOVE]


def test_section_two_is_the_same_wall_with_an_unbound_below():
    s = section(1)
    assert s.target_center == CHECKPOINT
    assert sorted(o.center for o in s.obstacles) == sorted(WALL)
    assert [p.center for p in s.pickups] == [UNBOUND_BELOW]


def test_section_three_is_a_box_in_the_top_left_corner():
    s = section(2)
    assert s.target_center == PLANET
    assert sorted(o.center for o in s.obstacles) == sorted(BOX)
    assert [p.center for p in s.pickups] == [UNBOUND_BOX]


def _sealed(rocks):
    for a, b in zip(rocks, rocks[1:]):
        assert math.dist(a, b) <= 2 * ROCK_R + 2 * HULL, (a, b)


def test_the_wall_seals_the_map_from_top_to_bottom():
    _sealed(WALL)
    assert WALL[0][1] == -HALF_H and WALL[-1][1] == HALF_H     # end rocks centred on the edges


def test_the_box_seals_the_planet_in_with_the_left_and_top_edges():
    _sealed(BOX)
    assert BOX[0][0] - ROCK_R < -HALF_W                  # the bottom reaches past the left edge
    assert BOX[-1][1] + ROCK_R > HALF_H                  # the right side reaches past the top edge
    x, y = PLANET
    assert x < BOX[-1][0] and y > BOX[0][1]              # the planet is inside the box


def _things(s):
    yield "start", s.start, 0.0
    yield "target", s.target_center, s.target_radius
    for p in s.pickups:
        yield f"{p.kind} {p.center}", p.center, p.radius


@pytest.mark.parametrize("index", [0, 1, 2], ids=["section1", "section2", "section3"])
def test_nothing_sits_in_a_rock(index):
    s = section(index)
    for name, center, radius in _things(s):
        for rock in s.obstacles:
            assert not discs_overlap(center, radius, rock.center, rock.radius + HULL), (name, rock.center)


def test_level_select_lists_level_eleven():
    cards = {lv.id: lv for lv in all_levels()}
    assert cards[11] is LEVEL


# --- reference answers and near misses --------------------------------------------------
# Section 1: level 6's arch flown right to left, over the top of the wall.
OVER = ("-0.25x", "6 - y")
# Section 2: the same arch with the sign of the y spring's centre flipped, under the wall.
UNDER = ("-0.25x", "-6 - y")
# Section 3: the section 1 arch with an x spring twice as strong, into the box from above.
DROP = ("-0.5x", "6 - y")
ANSWERS = (OVER, UNDER, DROP)
TIMES = (5.66, 5.66, 4.68)
UNBOUNDS = (UNBOUND_ABOVE, UNBOUND_BELOW, UNBOUND_BOX)


def _fly(level, fx, fy):
    field = ForceField.from_exprs(parse_expression(fx), parse_expression(fy))
    flight = Flight(field, SHIP, level)
    while flight.running:
        flight.step()
    return flight


@pytest.mark.parametrize("index", [0, 1, 2], ids=["section1", "section2", "section3"])
def test_each_reference_answer_takes_its_unbound_and_reaches(index):
    flight = _fly(section(index), *ANSWERS[index])
    assert flight.outcome is Outcome.REACHED
    assert flight.bounces == 0
    assert flight.time == pytest.approx(TIMES[index], abs=0.05)
    assert {p.center for p in flight.pickups if p.consumed} == {UNBOUNDS[index]}


@pytest.mark.parametrize("index", [0, 1, 2], ids=["section1", "section2", "section3"])
@pytest.mark.parametrize("answer", [0, 1, 2], ids=["over", "under", "drop"])
def test_only_its_own_answer_clears_a_section(index, answer):
    outcome = _fly(section(index), *ANSWERS[answer]).outcome
    if answer == index:
        assert outcome is Outcome.REACHED
    else:
        assert outcome is Outcome.OUT_OF_BOUNDS


@pytest.mark.parametrize("index", [0, 1, 2], ids=["section1", "section2", "section3"])
def test_no_section_is_cleared_without_its_unbound(index):
    bare = dataclasses.replace(section(index), pickups=())
    assert _fly(bare, *ANSWERS[index]).outcome is Outcome.OUT_OF_BOUNDS


# Every 5 deg at four strengths (288 pushes per section).
CONSTANT_PUSHES = [(deg, size) for deg in range(0, 360, 5) for size in (1, 2, 4, 8)]


@pytest.mark.parametrize("index", [0, 1, 2], ids=["section1", "section2", "section3"])
def test_no_constant_push_clears_a_section(index):
    s = section(index)
    reached = []
    for deg, size in CONSTANT_PUSHES:
        fx = size * math.cos(math.radians(deg))
        fy = size * math.sin(math.radians(deg))
        if _fly(s, f"{fx:.6f}", f"{fy:.6f}").outcome is Outcome.REACHED:
            reached.append((deg, size))
    assert reached == []


# --- the game: two checkpoints, two pans to the left, win; the answer is paid once ---------
def _scene():
    from types import SimpleNamespace

    from vector_drift.scenes.base import SceneManager
    from vector_drift.scenes.game import GameScene

    audio = SimpleNamespace(play=lambda *a, **k: None, start_loop=lambda *a, **k: None,
                            stop_loop=lambda *a, **k: None)
    manager = SceneManager(audio)
    manager.session.level_id = 11
    scene = GameScene(manager)
    manager.switch(scene)
    return manager, scene


def _type(scene, fx, fy):
    scene.editor.set_lines([fx, fy])
    scene._on_text_change(scene.editor)


def _launch(scene, surface, answer):
    """Fly ``answer`` through any pan that follows; the state it ends in."""
    from vector_drift.scenes.game import FLIGHT, PANNING

    _type(scene, *answer)
    scene._try_launch()
    while scene.state == FLIGHT:
        scene.update(0.05)
        scene.draw(surface)
    reached = scene.state
    while scene.state == PANNING:
        scene.update(0.05)
        scene.draw(surface)
    return reached


@pytest.mark.usefixtures("pygame_display")
def test_level_eleven_plays_through_two_checkpoints_to_the_win():
    import pygame

    from vector_drift.scenes.game import ARRIVED, PANNING, SETUP

    _, scene = _scene()
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    assert scene.section_index == 0 and scene.lives == LEVEL.lives

    # Section 1 at full lives: the checkpoint's extra life is capped.
    assert _launch(scene, surface, OVER) == PANNING
    assert scene.section_index == 1 and scene.lives == LEVEL.lives
    assert tuple(scene.launch_pos) == START

    # Section 2: section 1's answer flies out over the wall without an Unbound; the
    # next life starts at the checkpoint, and reaching the next one gives it back.
    assert _launch(scene, surface, OVER) == SETUP
    assert scene.section_index == 1 and scene.lives == LEVEL.lives - 1
    assert tuple(scene.launch_pos) == START
    assert _launch(scene, surface, UNDER) == PANNING
    assert scene.section_index == 2 and scene.lives == LEVEL.lives

    # Section 3: the planet.
    assert _launch(scene, surface, DROP) == ARRIVED
    assert scene.section_index == 2 and scene.lives == LEVEL.lives


@pytest.mark.xfail(reason="level 11 hints pending", strict=True)
@pytest.mark.usefixtures("pygame_display")
def test_level_eleven_answer_is_paid_once_for_all_three_sections():
    import pygame

    from vector_drift.scenes.game import PANNING

    assert 11 not in config.FREE_ANSWER_LEVELS
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
    assert 11 in manager.session.paid_answer_levels

    # Sections 2 and 3: each one's own answer page opens straight away, at no charge.
    for answer, section_number in ((OVER, 2), (UNDER, 3)):
        assert _launch(scene, surface, answer) == PANNING
        assert scene.section_index == section_number - 1
        popup = open_answer()
        assert popup.on_answer_page and not popup.confirming
        assert popup.hint is scene.hint and scene.hint.section == section_number
        assert int(manager.session.money) == 25 - config.HINT_ANSWER_COST
