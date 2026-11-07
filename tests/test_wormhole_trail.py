"""The trail is not joined across a wormhole: it stops at the black hole and restarts at the white."""

import math
from types import SimpleNamespace

import pygame
import pytest

from vector_drift import config
from vector_drift.data import SHIPS, get_level
from vector_drift.expr_parser import parse_expression
from vector_drift.physics import Flight, ForceField, Outcome
from vector_drift.replay import ReplayFrame, normalize_records
from vector_drift.scenes import replay as replay_module
from vector_drift.scenes.base import SceneManager
from vector_drift.scenes.game import FLIGHT, GameScene
from vector_drift.scenes.replay import ReplayScene, trail_strokes

pytestmark = pytest.mark.usefixtures("pygame_display")
LEVEL4 = get_level(4)
(BLACK, WHITE, HOLE_R), = LEVEL4.holes
FX, FY = "2", "1 - 0.5x - 2y"           # level 4's hint answer: in at (-3, 4), out at (2, 4)


def _flight():
    field = ForceField.from_exprs(parse_expression(FX), parse_expression(FY))
    flight = Flight(field, SHIPS["ship01"], LEVEL4, holes=LEVEL4.holes)
    while flight.running:
        flight.step()
    return flight


def _manager():
    audio = SimpleNamespace(play=lambda *a, **k: None, start_loop=lambda *a, **k: None,
                            stop_loop=lambda *a, **k: None, toggle_mute=lambda: None)
    manager = SceneManager(audio)
    return manager


def _fly_level4():
    manager = _manager()
    manager.session.level_id = 4
    manager.session.fx_text, manager.session.fy_text = FX, FY
    scene = GameScene(manager)
    manager.switch(scene)
    scene._try_launch()
    while scene.state == FLIGHT:
        scene.update(1 / 60)
    return scene


# --- physics: where the trail breaks ---------------------------------------------------
def test_the_trail_breaks_once_at_the_wormhole():
    flight = _flight()
    assert flight.outcome is Outcome.REACHED and flight.teleports == 1
    (i,) = flight.trail_breaks
    reach = HOLE_R + SHIPS["ship01"].hull_radius
    assert math.dist(flight.trail[i - 1], BLACK) < reach + 0.2     # the stroke ends in the black hole
    assert flight.trail[i] == WHITE                                 # the next one starts at the white


def test_a_flight_without_holes_has_no_breaks():
    flight = Flight(ForceField.from_exprs(parse_expression("5"), parse_expression("0")),
                    SHIPS["ship01"], get_level(1))
    while flight.running:
        flight.step()
    assert flight.trail_breaks == []


# --- game: the trail layer -------------------------------------------------------------
def _trail_pixels(scene):
    surface = pygame.Surface((scene.viewport.width, scene.viewport.height), pygame.SRCALPHA)
    scene.trail.draw(surface, (0, 0))
    return surface


def _px(scene, x, y):
    vp = scene.viewport
    return round(vp.cx - vp.left + x * vp.scale), round(vp.cy - vp.top - y * vp.scale)


def test_the_game_trail_has_no_line_between_the_holes():
    scene = _fly_level4()
    surface = _trail_pixels(scene)
    # The ship never flies through x in [-2, 1] (the rock wall between the
    # holes): any trail there is the black -> white hole join.
    x0, _ = _px(scene, -2.0, 0.0)
    x1, _ = _px(scene, 1.0, 0.0)
    band = pygame.Rect(x0, 0, x1 - x0, surface.get_height())
    assert surface.subsurface(band).get_bounding_rect().width == 0
    assert surface.get_bounding_rect().width > 0        # both strokes are drawn


# --- replay -------------------------------------------------------------------------------
def test_the_game_marks_the_frame_after_the_teleport():
    scene = _fly_level4()
    warps = [f for f in scene._replay_frames if f.get("warp")]
    assert len(warps) == 1
    assert math.dist((warps[0]["x"], warps[0]["y"]), WHITE) < 0.5
    (rec,) = scene.manager.session.replays
    assert sum(1 for f in rec["frames"] if f.get("warp")) == 1     # survives normalize_records


def test_warp_is_only_written_when_set():
    assert "warp" not in ReplayFrame(x=1.0).to_dict()
    assert ReplayFrame(x=1.0, warp=True).to_dict()["warp"] is True
    for value in (False, None, 1, "yes"):
        assert ReplayFrame.from_dict({"x": 1.0, "warp": value}).warp is False
    assert ReplayFrame.from_dict({"x": 1.0, "warp": True}).warp is True


def _frame(t, x, y, vx=1.0, vy=0.0, **extra):
    return {"t": t, "x": x, "y": y, "vx": vx, "vy": vy, "fx": 0.0, "fy": 0.0, **extra}


def test_a_warp_frame_starts_a_new_stroke():
    frames = [_frame(0.0, -4.0, 4.0), _frame(0.1, -3.5, 4.0), _frame(0.2, 2.0, 4.0, warp=True),
              _frame(0.3, 2.5, 4.0)]
    assert [len(s) for s in trail_strokes(frames)] == [2, 2]


def test_an_old_record_breaks_where_the_ship_jumps():
    frames = [_frame(0.0, -4.0, 4.0), _frame(1 / 60, -3.9, 4.0), _frame(2 / 60, 2.0, 4.0),
              _frame(3 / 60, 2.1, 4.0)]
    assert [len(s) for s in trail_strokes(frames)] == [2, 2]


def test_fast_ordinary_flight_stays_one_stroke():
    # 30 m/s covers 0.5 m a frame: that is flying, not a jump.
    frames = [_frame(i / 60, -9.0 + 0.5 * i, 0.0, vx=30.0) for i in range(30)]
    assert len(trail_strokes(frames)) == 1
    # ReplayFrame objects work the same as dicts.
    assert len(trail_strokes([ReplayFrame.from_dict(f) for f in frames])) == 1


def test_the_replay_draws_two_strokes_through_the_wormhole(monkeypatch):
    scene = _fly_level4()
    manager = scene.manager
    replay = ReplayScene(manager)
    manager.switch(replay)
    replay.player.seek(len(replay.player.record.frames) - 1)
    strokes = []
    real = pygame.draw.lines
    monkeypatch.setattr(replay_module.pygame.draw, "lines",
                        lambda surface, color, closed, pts, *a: (strokes.append(pts),
                                                                 real(surface, color, closed, pts, *a))[1])
    replay.draw(pygame.Surface((config.WINDOW_W, config.WINDOW_H)))

    trail = [pts for pts in strokes if len(pts) > 2]
    assert len(trail) == 2
    vp = replay._viewport
    assert math.dist(trail[1][0], vp.to_screen(*WHITE)) < vp.length(0.5)
