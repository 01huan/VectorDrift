"""Multi-section levels: SectionSpec, one section as a LevelSpec, the pan between two."""

import pytest

from vector_drift.data import (LEVELS, LevelSpec, ObstacleSpec, PickupSpec, SectionSpec,
                               get_level, multi_section_level, section_count, section_level,
                               section_shift)
from vector_drift.level_presets import is_dynamic_level

ROCK = ObstacleSpec(center=(0.0, 2.0), radius=0.8)
COIN = PickupSpec(center=(1.0, -3.0), radius=0.45, kind="money")
HOLE = ((-3.0, 4.0), (2.0, 4.0), 0.5)

# Three sections: the first pan goes up-right (diagonal), the second straight up.
THREE = multi_section_level(
    id=42, name="Three Screens", ship_id="ship01", lives=3,
    sections=(
        SectionSpec(start=(-7.0, -5.0), target_center=(6.0, 4.0)),
        SectionSpec(start=(-6.0, -4.0), target_center=(0.0, 5.5), time_limit=8.0,
                    target_radius=0.9, obstacles=(ROCK,), pickups=(COIN,), holes=(HOLE,)),
        SectionSpec(start=(0.0, -5.5), target_center=(5.0, 0.0), target_radius=1.2),
    ),
)


@pytest.mark.parametrize("level", [lv for lv in LEVELS if not lv.sections], ids=lambda lv: f"level{lv.id}")
def test_one_screen_levels_are_their_own_single_section(level):
    assert section_count(level) == 1
    assert section_level(level, 0) is level
    with pytest.raises(IndexError):
        section_level(level, 1)
    with pytest.raises(IndexError):
        section_shift(level, 0)


def test_a_level_without_sections_keeps_every_field():
    plain = LevelSpec(id=1, name="x", start=(-7.0, 0.0), target_center=(7.0, 0.0),
                      target_radius=1.0, ship_id="ship01")
    assert plain.sections == ()
    assert section_level(plain, 0) == plain


def test_section_count():
    assert section_count(THREE) == 3


def test_the_level_itself_mirrors_section_one():
    first = section_level(THREE, 0)
    assert (THREE.start, THREE.target_center, THREE.time_limit) == (
        first.start, first.target_center, first.time_limit)


def test_each_section_becomes_an_ordinary_level():
    for index, section in enumerate(THREE.sections):
        level = section_level(THREE, index)
        assert isinstance(level, LevelSpec)
        assert level.sections == ()
        assert (level.id, level.name, level.lives, level.ship_id) == (42, "Three Screens", 3, "ship01")
        assert level.start == section.start
        assert level.target_center == section.target_center
        assert level.target_radius == section.target_radius
        assert level.time_limit == section.time_limit
        assert level.obstacles == section.obstacles
        assert level.pickups == section.pickups
        assert level.holes == section.holes


def test_section_props_and_limits_come_from_that_section_only():
    middle = section_level(THREE, 1)
    assert middle.obstacles == (ROCK,) and middle.pickups == (COIN,) and middle.holes == (HOLE,)
    assert middle.time_limit == 8.0 and middle.target_radius == 0.9
    first, last = section_level(THREE, 0), section_level(THREE, 2)
    assert first.obstacles == first.pickups == first.holes == ()
    assert first.time_limit == 10.0
    assert last.target_radius == 1.2 and last.obstacles == ()


@pytest.mark.parametrize("index", [-1, 3])
def test_a_missing_section_is_an_index_error(index):
    with pytest.raises(IndexError):
        section_level(THREE, index)


def test_pans_follow_the_coordinates_not_a_fixed_direction():
    # Diagonal: checkpoint (6, 4) minus next start (-6, -4).
    assert section_shift(THREE, 0) == (12.0, 8.0)
    # Straight up: checkpoint (0, 5.5) minus next start (0, -5.5).
    assert section_shift(THREE, 1) == (0.0, 11.0)
    with pytest.raises(IndexError):
        section_shift(THREE, 2)                 # no pan after the last section


def test_the_checkpoint_stays_put_across_a_pan():
    """Checkpoint k in section k coords == start k+1 in section k+1 coords + pan."""
    for index in range(section_count(THREE) - 1):
        sx, sy = section_shift(THREE, index)
        here, there = THREE.sections[index], THREE.sections[index + 1]
        assert (there.start[0] + sx, there.start[1] + sy) == pytest.approx(here.target_center)


def test_a_pan_to_the_left_and_down_is_negative():
    level = multi_section_level(
        id=43, name="Back", ship_id="ship01",
        sections=(SectionSpec(start=(7.0, 5.0), target_center=(-7.0, -5.0)),
                  SectionSpec(start=(7.0, 5.0), target_center=(0.0, 0.0))))
    assert section_shift(level, 0) == (-14.0, -10.0)


def test_a_multi_section_level_needs_two_sections():
    with pytest.raises(ValueError):
        multi_section_level(id=44, name="One", ship_id="ship01",
                            sections=(SectionSpec(start=(0.0, 0.0), target_center=(5.0, 0.0)),))


def test_fixed_levels_still_load_by_id():
    for level in LEVELS:
        if not is_dynamic_level(level.id):
            assert get_level(level.id) is level
