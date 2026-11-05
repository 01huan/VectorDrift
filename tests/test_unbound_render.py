"""Unbound on screen: its icon, the dashed map edge and the camera zoom-out."""

import math
from types import SimpleNamespace

import pygame
import pytest

from vector_drift import audio, config, render, sprites
from vector_drift.coords import Viewport, fit_zoom
from vector_drift.data import LevelSpec, ObstacleSpec, PickupSpec
from vector_drift.scenes import game as game_module
from vector_drift.scenes.base import SceneManager
from vector_drift.scenes.game import FLIGHT, SETUP, GameScene
from vector_drift.story import all_seen_keys

pytestmark = pytest.mark.usefixtures("pygame_display")

MAP = (config.WORLD_HALF_W, config.WORLD_HALF_H)
OUTER = (2 * config.WORLD_HALF_W, 2 * config.WORLD_HALF_H)


# --- zoom math ---------------------------------------------------------------------
@pytest.mark.parametrize("point", [(0.0, 0.0), (-7.0, 0.0), (9.9, 7.4), (-10.0, -7.5)])
def test_zoom_is_one_while_the_ship_is_on_the_map(point):
    assert fit_zoom(point, MAP, OUTER) == 1.0


@pytest.mark.parametrize("point", [(20.0, 15.0), (-20.0, 0.0), (0.0, -15.0), (35.0, 2.0), (0.0, 40.0)])
def test_zoom_bottoms_out_where_the_outer_edge_fills_the_plot(point):
    assert fit_zoom(point, MAP, OUTER) == 0.5


def test_zoom_in_between_keeps_ship_and_map_on_screen():
    zoom = fit_zoom((15.0, 0.0), MAP, OUTER, margin=0.5)
    assert math.isclose(zoom, 10.0 / 15.5)
    vp = Viewport(zoom=zoom)
    assert vp.half_w >= 15.5 - 1e-9 and vp.half_h >= config.WORLD_HALF_H
    zoom = fit_zoom((3.0, -11.0), MAP, OUTER, margin=0.5)
    assert math.isclose(zoom, 7.5 / 11.5)


def test_outer_edge_fills_the_plot_at_the_lowest_zoom():
    vp = Viewport(zoom=fit_zoom(OUTER, MAP, OUTER))
    assert math.isclose(vp.half_w, OUTER[0]) and math.isclose(vp.half_h, OUTER[1])
    left, top = vp.to_screen(-OUTER[0], OUTER[1])
    assert math.isclose(left, vp.left) and math.isclose(top, vp.top)


def test_viewport_zoom_scales_every_mapping():
    flat, half = Viewport(), Viewport(zoom=0.5)
    assert flat.zoom == 1.0 and math.isclose(half.scale, flat.scale / 2)
    assert math.isclose(half.length(2.0), flat.length(1.0))
    assert half.to_world(*half.to_screen(13.0, -4.0)) == pytest.approx((13.0, -4.0))


# --- icon ----------------------------------------------------------------------------
def _ink(surface):
    return sum(1 for x in range(surface.get_width()) for y in range(surface.get_height())
               if surface.get_at((x, y)).a > 0)


def test_unbound_icon_draws_without_a_picture(monkeypatch):
    monkeypatch.setattr(sprites, "load_image", lambda *a, **k: None)
    surface = pygame.Surface((80, 80), pygame.SRCALPHA)
    sprites.draw_pickup(surface, (40, 40), 22, 0.0, kind="unbound")
    assert _ink(surface) > 500


def test_unbound_icon_uses_the_picture_when_there_is_one(monkeypatch):
    picture = pygame.Surface((44, 44), pygame.SRCALPHA)
    picture.fill((10, 200, 30, 255))
    asked = []
    monkeypatch.setattr(sprites, "load_image", lambda key, **k: asked.append(key) or picture)
    monkeypatch.setattr(sprites, "PICKUP_RENDERERS", {})     # the painter must not be needed
    surface = pygame.Surface((80, 80), pygame.SRCALPHA)
    sprites.draw_pickup(surface, (40, 40), 22, 0.0, kind="unbound")
    assert asked == ["pickup.unbound"]
    assert tuple(surface.get_at((40, 40))) == (10, 200, 30, 255)


# --- sound ---------------------------------------------------------------------------
def test_unbound_has_a_sound_slot():
    assert "unbound" in audio.SOUND_SLOTS


# --- in the game scene -------------------------------------------------------------
LEVEL = LevelSpec(
    id=1, name="test", start=(-7.0, 0.0), target_center=(7.0, 0.0), target_radius=1.0,
    ship_id="ship01", obstacles=(ObstacleSpec(center=(0.0, 3.0), radius=0.8),),
    pickups=(PickupSpec(center=(-7.0, 0.8), radius=0.45, kind="unbound"),
             PickupSpec(center=(4.0, -4.0), radius=0.45, kind="money")),
)


class Audio:
    def __init__(self):
        self.played = []

    def play(self, name):
        self.played.append(name)

    def start_loop(self, name):
        pass

    def stop_loop(self, name):
        pass

    def toggle_mute(self):
        pass


@pytest.fixture
def scene(monkeypatch):
    monkeypatch.setattr(game_module, "get_level", lambda *a, **k: LEVEL)
    manager = SceneManager(Audio())
    manager.session.story_seen = all_seen_keys()
    manager.session.level_id = 1
    s = GameScene(manager)
    manager.switch(s)
    return s


def _surface():
    return pygame.Surface((config.WINDOW_W, config.WINDOW_H))


def _launch(scene, fx, fy):
    scene.editor.set_lines([fx, fy])
    scene._on_text_change(scene.editor)
    scene._try_launch()
    assert scene.state == FLIGHT


def _run_until(scene, done, surface=None, frames=3000):
    for _ in range(frames):
        if done():
            return
        scene.update(1 / 60)
        if surface is not None:
            scene.draw(surface)
    raise AssertionError("condition never met")


def test_taking_unbound_plays_its_sound(scene):
    _launch(scene, "0", "10")
    _run_until(scene, lambda: scene.flight.unbound)
    assert "unbound" in scene.audio.played


def test_camera_zooms_out_off_the_map_and_back_in(scene):
    surface = _surface()
    # Swing up past the top edge (y peaks at 10 m) and come back down.
    _launch(scene, "0", "10 - 2*y")
    assert scene.camera.zoom == 1.0
    _run_until(scene, lambda: scene.flight.y > 9.5, surface)
    assert scene.camera.zoom < 0.85
    assert scene.camera.half_h >= scene.flight.y              # the ship stays on screen
    _run_until(scene, lambda: scene.flight.y < 5.0, surface)
    _run_until(scene, lambda: scene.camera.zoom == 1.0, surface, frames=120)
    scene.draw(surface)


def test_zoom_changes_smoothly_at_the_map_edge():
    just_out = fit_zoom((-7.0, 7.5001), MAP, OUTER, margin=1.0)
    assert 0.999 < just_out <= 1.0


def test_the_ship_never_leaves_the_screen_while_zooming_out(scene):
    _launch(scene, "1.6 - 0.1*x", "10 - 2*y")       # up past the edge fast, then back down
    previous = scene.camera.zoom
    for _ in range(400):
        if scene.state != FLIGHT:
            break
        scene.update(1 / 60)
        if scene.flight is None:
            break
        cam, f = scene.camera, scene.flight
        assert abs(f.x) <= cam.half_w + 1e-6 and abs(f.y) <= cam.half_h + 1e-6
        half = 0.5 * scene.ship.length              # well past the edge: the whole ship shows
        if abs(f.y) > MAP[1] + half:
            assert abs(f.y) + half <= cam.half_h + 1e-6
        assert abs(cam.zoom - previous) < 0.03
        previous = cam.zoom


def test_camera_stops_at_the_outer_edge_and_resets_for_the_next_life(scene):
    surface = _surface()
    _launch(scene, "0", "10")
    _run_until(scene, lambda: scene.state != FLIGHT, surface)
    assert scene.state == SETUP
    assert scene.camera.zoom >= 0.5
    _run_until(scene, lambda: scene.camera.zoom == 1.0, surface, frames=120)


def test_zoomed_drawing_scales_props_with_the_camera(scene, monkeypatch):
    drawn = []
    real = sprites.draw_obstacle
    monkeypatch.setattr(sprites, "draw_obstacle",
                        lambda surface, center, radius, *a, **k: drawn.append(radius) or
                        real(surface, center, radius, *a, **k))
    surface = _surface()
    scene.draw(surface)
    flat = drawn[-1]
    _launch(scene, "0", "10")
    _run_until(scene, lambda: scene.camera.zoom < 0.7, surface)
    scene.draw(surface)
    assert math.isclose(drawn[-1], flat * scene.camera.zoom)


def test_map_edge_is_dashed_only_while_unbound(scene, monkeypatch):
    calls = []
    monkeypatch.setattr(render, "draw_dashed_rect", lambda *a, **k: calls.append(a))
    surface = _surface()
    scene.draw(surface)
    assert calls == []

    _launch(scene, "0", "10")
    scene.draw(surface)
    assert calls == []                                # not taken yet
    _run_until(scene, lambda: scene.flight.unbound)
    scene.draw(surface)
    assert len(calls) == 1

    _run_until(scene, lambda: scene.state != FLIGHT)  # the life ends
    calls.clear()
    scene.draw(surface)
    assert calls == []
