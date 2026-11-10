"""Tests for the procedural generation modules (level_modules)."""

import math
import os

import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from vector_drift.data import get_level
from vector_drift.level_modules import (
    GENERATORS,
    generate_layout,
    known_modules,
)
from vector_drift.level_presets import PRESET_8
from vector_drift.level_validator import validate_level
from dataclasses import replace

TEMPLATES = {t.generator: t for t in PRESET_8.templates}

ALL_MODULES = ("corridor", "extreme_time", "wormhole_network", "maze", "bomb")


def _module_layout(module, seed):
    template = TEMPLATES[module]
    preset = replace(template, templates=(), name=PRESET_8.name)
    return generate_layout(seed, preset)


def _validate(module, seed, **kwargs):
    template = TEMPLATES[module]
    preset = replace(template, templates=(), name=PRESET_8.name)
    layout = _module_layout(module, seed)
    args = dict(preset=preset, route=layout.route, segments=layout.segments,
                teleports=layout.teleports, walls=layout.walls,
                generator=layout.module, seed=seed, run_solver=False)
    args.update(kwargs)
    return layout, validate_level(layout.level, **args)


def test_known_modules_are_registered():
    assert set(known_modules()) == set(ALL_MODULES)
    assert set(GENERATORS) == set(ALL_MODULES)


def test_every_module_builds_a_valid_layout():
    for module in ALL_MODULES:
        for seed in (1, 7, 42):
            layout = _module_layout(module, seed)
            assert layout.module == module
            assert layout.level.id == 8
            assert layout.level.name == PRESET_8.name
            # The module must guarantee a route exists by construction.
            assert layout.segments or layout.route


def test_every_module_layout_validates():
    for module in ALL_MODULES:
        for seed in (1, 7, 42):
            layout, report = _validate(module, seed)
            assert report.ok, f"{module} seed {seed}: {[c.message for c in report.errors]}"
            assert report.generator == module


def test_layouts_are_deterministic_per_seed():
    for module in ALL_MODULES:
        a = _module_layout(module, 123)
        b = _module_layout(module, 123)
        assert a.level.start == b.level.start
        assert a.level.target_center == b.level.target_center
        assert [(o.center, o.radius) for o in a.level.obstacles] == \
               [(o.center, o.radius) for o in b.level.obstacles]
        assert [p.center for p in a.level.pickups] == [p.center for p in b.level.pickups]
        assert a.level.holes == b.level.holes


def test_wormhole_network_chains_teleports_across_gates():
    layout = _module_layout("wormhole_network", 5)
    holes = layout.level.holes
    assert len(holes) == TEMPLATES["wormhole_network"].num_holes
    assert len(layout.teleports) == len(holes)
    # Black holes are placed on the start side, white holes on the target side.
    start_x = layout.level.start[0]
    target_x = layout.level.target_center[0]
    direction = 1.0 if target_x > start_x else -1.0
    for hole in holes:
        if direction > 0:
            assert hole.black_center[0] < hole.white_center[0]
        else:
            assert hole.black_center[0] > hole.white_center[0]
    # The walls are reported for the validator's seal check.
    assert len(layout.walls) == len(holes)
    _, report = _validate("wormhole_network", 5)
    assert report.ok


def test_maze_entrance_and_exit_are_cell_centers():
    cell = 3.0
    layout = _module_layout("maze", 5)
    cols, rows = 6, 5
    x0, y0 = -cell * cols / 2, -cell * rows / 2

    def center(col, row):
        return (x0 + (col + 0.5) * cell, y0 + (row + 0.5) * cell)

    assert layout.level.start == pytest.approx(center(0, 0))
    assert layout.level.target_center == pytest.approx(center(cols - 1, rows - 1))
    route = layout.route
    # BFS path: every step is exactly one cell in one axis.
    for a, b in zip(route, route[1:]):
        assert math.dist(a, b) == pytest.approx(cell)
    _, report = _validate("maze", 5)
    assert report.ok


def test_bomb_module_requires_a_shockwave():
    layout = _module_layout("bomb", 5)
    shocks = [p for p in layout.level.pickups if p.kind == "shockwave"]
    assert shocks, "bomb level must place at least one shockwave"
    # The required shockwave sits outside the ring that seals the target.
    target = layout.level.target_center
    for shock in shocks:
        assert math.dist(shock.center, target) >= 4.0
    # The intended route collects it before entering the ring.
    assert layout.segments[0][1] == pytest.approx(shocks[0].center)
    _, report = _validate("bomb", 5)
    assert report.ok


def test_extreme_time_route_winds_more_than_the_direct_line():
    layout = _module_layout("extreme_time", 5)
    direct = math.dist(layout.level.start, layout.level.target_center)
    winding = sum(math.dist(a, b) for a, b in layout.segments)
    assert winding > direct * 1.05
    _, report = _validate("extreme_time", 5)
    assert report.ok


def test_level8_offers_every_module():
    seen = set()
    for seed in range(40):
        _, report = generate_random_level_seeded(seed)
        seen.add(report.generator)
        assert report.ok
    assert seen == set(ALL_MODULES)


def generate_random_level_seeded(seed):
    from vector_drift.random_level import generate_random_level
    return generate_random_level(8, seed=seed, run_solver=False,
                                 return_report=True)


def test_unknown_module_is_rejected():
    preset = replace(TEMPLATES["corridor"], templates=(), generator="no_such_module")
    with pytest.raises(ValueError):
        generate_layout(1, preset)


def test_get_level_level8_uses_generation():
    level = get_level(8, seed=4242)
    assert level.id == 8
    assert level.obstacles is not None
