"""Level 10 Shortcut: chapter 2's first diagonal pan.

Section 1 reviews level 4's wormhole (a steady push plus a spring toward a
slanted line); section 2 reviews the Shield with level 7's swirl (an L-shaped
wall, passed through one rock).
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

LEVEL = get_level(10)
SHIP = SHIPS[LEVEL.ship_id]
HULL = SHIP.hull_radius
ROCK_R = 0.8
HALF_W, HALF_H = config.WORLD_HALF_W, config.WORLD_HALF_H

START = (-7.0, -4.5)
WALL = tuple((2.0, y) for y in (-7.0, -5.4, -3.8, -2.2, -0.6, 1.0, 2.6, 4.2, 5.8, 7.4))
BLACK, WHITE = (-7.0, 1.5), (4.0, -1.0)
ROW = tuple((x, 1.0) for x in (2.0, 3.55, 5.1, 6.65, 8.2, 9.75))
COLUMN = ((2.0, 1.0),) + tuple((2.0, y) for y in (2.55, 4.1, 5.65, 7.2))
SHIELD = (0.0, -4.5)


def first():
    return section_level(LEVEL, 0)


def second():
    return section_level(LEVEL, 1)


# --- layout -----------------------------------------------------------------------
def test_level_ten_is_a_fixed_two_section_level():
    assert isinstance(LEVEL, LevelSpec) and LEVEL in LEVELS
    assert LEVEL.name == "Shortcut"
    assert not is_dynamic_level(10)
    assert section_count(LEVEL) == 2
    assert LEVEL.lives == 5
    for section in (first(), second()):
        assert section.start == START
        assert section.target_radius == 1.0
        assert section.time_limit == 10.0
        assert all(o.radius == ROCK_R for o in section.obstacles)


def test_level_ten_has_no_coins():
    for section in (first(), second()):
        assert not [p for p in section.pickups if p.kind == "money"]


def test_the_pan_goes_up_and_to_the_right():
    assert section_shift(LEVEL, 0) == (14.0, 9.0)       # world (-7, -4.5) -> (7, 4.5) -> (13.5, 9)


def test_section_one_is_a_wall_at_x_2_and_a_wormhole_across_it():
    section = first()
    assert section.target_center == (7.0, 4.5)
    assert sorted(o.center for o in section.obstacles) == sorted(WALL)
    assert section.pickups == ()
    assert len(section.holes) == 1
    hole = section.holes[0]
    assert (hole.black_center, hole.white_center, hole.radius) == (BLACK, WHITE, 0.5)


def test_section_two_is_an_l_shaped_wall_and_one_shield():
    section = second()
    assert section.target_center == (6.5, 4.5)
    assert sorted(o.center for o in section.obstacles) == sorted(set(ROW) | set(COLUMN))
    assert section.holes == ()
    assert [(p.center, p.radius, p.kind) for p in section.pickups] == [(SHIELD, 0.45, "shield")]


def _sealed(rocks):
    for a, b in zip(rocks, rocks[1:]):
        assert math.dist(a, b) <= 2 * ROCK_R + 2 * HULL, (a, b)


def test_section_one_wall_seals_the_map_from_top_to_bottom():
    _sealed(WALL)
    assert WALL[0][1] - ROCK_R < -HALF_H and WALL[-1][1] + ROCK_R > HALF_H


def test_section_two_wall_seals_the_top_right_corner():
    _sealed(ROW)
    _sealed(COLUMN)
    assert ROW[-1][0] + ROCK_R > HALF_W                 # the row reaches the right edge
    assert COLUMN[-1][1] + ROCK_R > HALF_H              # the column reaches the top edge
    x, y = second().target_center
    assert x > COLUMN[0][0] and y > ROW[0][1]           # the planet is inside the corner


def _things(section):
    yield "start", section.start, 0.0
    yield "target", section.target_center, section.target_radius
    for hole in section.holes:
        yield "black hole", hole.black_center, hole.radius
        yield "white hole", hole.white_center, hole.radius
    for p in section.pickups:
        yield f"{p.kind} {p.center}", p.center, p.radius


@pytest.mark.parametrize("index", [0, 1], ids=["section1", "section2"])
def test_nothing_sits_in_a_rock(index):
    section = section_level(LEVEL, index)
    for name, center, radius in _things(section):
        for rock in section.obstacles:
            assert not discs_overlap(center, radius, rock.center, rock.radius + HULL), (name, rock.center)


def test_level_select_lists_level_ten():
    cards = {lv.id: lv for lv in all_levels()}
    assert cards[10] is LEVEL


# --- reference answers and near misses --------------------------------------------------
# Section 1: level 4's steady push plus a spring toward the line y = -x/2 (k = 3).
SPRING = ("2", "-1.5x - 3y")
# Section 2: level 7's swirl round (-6, -2.5), through the Shield and one rock.
SWIRL = ("-y - 2.5", "x + 6")
SHIELDED_ROCK = (5.1, 1.0)


def _fly(level, fx, fy):
    field = ForceField.from_exprs(parse_expression(fx), parse_expression(fy))
    flight = Flight(field, SHIP, level)
    while flight.running:
        flight.step()
    return flight


def test_section_one_swings_through_the_wormhole_into_the_checkpoint():
    flight = _fly(first(), *SPRING)
    assert flight.outcome is Outcome.REACHED
    assert flight.bounces == 0
    assert flight.teleports == 1
    assert flight.time == pytest.approx(1.62, abs=0.05)


def test_section_two_takes_the_shield_through_the_wall():
    flight = _fly(second(), *SWIRL)
    assert flight.outcome is Outcome.REACHED
    assert flight.bounces == 0
    assert flight.time == pytest.approx(3.51, abs=0.05)
    assert {p.center for p in flight.pickups if p.consumed} == {SHIELD}
    used = [e["center"] for e in flight.pickup_events if e["kind"] == "shield_used"]
    assert used == [SHIELDED_ROCK]


def test_section_one_cannot_just_push_straight_up():
    flight = _fly(first(), "0", "5")
    assert flight.teleports == 1                       # into the black hole ...
    assert flight.outcome is not Outcome.REACHED       # ... and straight up out of the white one


def test_section_two_wall_is_closed_without_the_shield():
    bare = dataclasses.replace(second(), pickups=())
    assert _fly(bare, *SWIRL).outcome is not Outcome.REACHED


def test_section_one_answer_leaves_the_map_in_section_two():
    assert _fly(second(), *SPRING).outcome is Outcome.OUT_OF_BOUNDS


# Every 5 deg at four strengths (288 pushes); checked every 1 deg when the level was made.
CONSTANT_PUSHES = [(deg, size) for deg in range(0, 360, 5) for size in (1, 2, 4, 8)]


@pytest.mark.parametrize("index", [0, 1], ids=["section1", "section2"])
def test_no_constant_push_clears_a_section(index):
    section = section_level(LEVEL, index)
    reached = []
    for deg, size in CONSTANT_PUSHES:
        fx = size * math.cos(math.radians(deg))
        fy = size * math.sin(math.radians(deg))
        if _fly(section, f"{fx:.6f}", f"{fy:.6f}").outcome is Outcome.REACHED:
            reached.append((deg, size))
    assert reached == []


# --- the game: checkpoint, pan up and right, win; the answer is paid once ------------
def _scene():
    from types import SimpleNamespace

    from vector_drift.scenes.base import SceneManager
    from vector_drift.scenes.game import GameScene

    audio = SimpleNamespace(play=lambda *a, **k: None, start_loop=lambda *a, **k: None,
                            stop_loop=lambda *a, **k: None)
    manager = SceneManager(audio)
    manager.session.level_id = 10
    scene = GameScene(manager)
    manager.switch(scene)
    return manager, scene


def _type(scene, fx, fy):
    scene.editor.set_lines([fx, fy])
    scene._on_text_change(scene.editor)


@pytest.mark.usefixtures("pygame_display")
def test_level_ten_plays_through_its_checkpoint_to_the_win():
    import pygame

    from vector_drift.scenes.game import ARRIVED, FLIGHT, PANNING

    _, scene = _scene()
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))

    for answer, expected in ((SPRING, PANNING), (SWIRL, ARRIVED)):
        _type(scene, *answer)
        scene._try_launch()
        while scene.state == FLIGHT:
            scene.update(0.05)
            scene.draw(surface)
        assert scene.state == expected
        while scene.state == PANNING:
            scene.update(0.05)
            scene.draw(surface)
    assert scene.section_index == 1
    assert scene.lives == LEVEL.lives
    assert scene.total_time == pytest.approx(1.62 + 3.51, abs=0.15)


@pytest.mark.usefixtures("pygame_display")
def test_level_ten_answer_is_paid_once_for_both_sections():
    import pygame

    from vector_drift.scenes.game import FLIGHT, PANNING

    assert 10 not in config.FREE_ANSWER_LEVELS
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
    assert 10 in manager.session.paid_answer_levels

    # Through the checkpoint to section 2.
    _type(scene, *SPRING)
    scene._try_launch()
    while scene.state in (FLIGHT, PANNING):
        scene.update(0.05)
        scene.draw(surface)
    assert scene.section_index == 1

    # Section 2: its own answer page opens straight away, at no charge.
    popup = open_answer()
    assert popup.on_answer_page and not popup.confirming
    assert popup.hint is scene.hint and scene.hint.section == 2
    assert int(manager.session.money) == 25 - config.HINT_ANSWER_COST
