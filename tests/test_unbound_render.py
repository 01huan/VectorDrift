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


# --- zoom math ---------------------------------------------------------------------
@pytest.mark.parametrize("point", [(0.0, 0.0), (-7.0, 0.0), (9.9, 7.4), (-10.0, -7.5)])
def test_zoom_is_one_while_the_ship_is_on_the_map(point):
    assert fit_zoom(point, MAP) == 1.0


def test_zoom_in_between_keeps_ship_and_map_on_screen():
    zoom = fit_zoom((15.0, 0.0), MAP, margin=0.5)
    assert math.isclose(zoom, 10.0 / 15.5)
    vp = Viewport(zoom=zoom)
    assert vp.half_w >= 15.5 - 1e-9 and vp.half_h >= config.WORLD_HALF_H
    zoom = fit_zoom((3.0, -11.0), MAP, margin=0.5)
    assert math.isclose(zoom, 7.5 / 11.5)


@pytest.mark.parametrize("point", [(20.0, 15.0), (-200.0, 3.0), (0.0, 1500.0), (-4e5, -9e4)])
def test_zoom_has_no_lower_limit(point):
    zoom = fit_zoom(point, MAP, margin=0.5)
    vp = Viewport(zoom=zoom)
    assert vp.half_w >= abs(point[0]) and vp.half_h >= abs(point[1])
    assert math.isclose(vp.half_w, abs(point[0]) + 0.5) or math.isclose(vp.half_h, abs(point[1]) + 0.5)


@pytest.mark.parametrize("point", [(math.inf, 0.0), (0.0, math.nan)])
def test_zoom_ignores_a_ship_that_is_not_a_number(point):
    assert fit_zoom(point, MAP) == 1.0


# --- far zoom: grid, labels and arrows stay readable --------------------------------
@pytest.mark.parametrize("zoom", [1.0, 0.5, 0.1, 1e-3, 1e-6])
def test_grid_line_count_stays_bounded_at_any_zoom(zoom, monkeypatch):
    lines = []
    monkeypatch.setattr(render.pygame.draw, "line", lambda *a, **k: lines.append(a))
    vp = Viewport(zoom=zoom)
    render.draw_grid(pygame.Surface((vp.width, vp.height), pygame.SRCALPHA), vp)
    assert 10 < len(lines) < 400


def test_grid_is_unchanged_at_zoom_one():
    assert render.grid_step(Viewport().scale, render.GRID_MIN_PX * config.UI_SCALE) == 1
    assert render.arrow_spacing(Viewport().scale) == 1.0
    assert render.arrow_spacing(Viewport(zoom=0.5).scale) == 1.0


@pytest.mark.parametrize("zoom", [0.3, 0.01, 1e-4])
def test_far_zoom_labels_are_few_and_round(zoom, monkeypatch):
    texts = []
    real = render.get_font
    monkeypatch.setattr(render, "get_font", lambda *a, **k: SimpleNamespace(
        render=lambda text, *b, **c: texts.append(text) or real(*a, **k).render(text, *b, **c)))
    vp = Viewport(zoom=zoom)
    render.draw_plot_labels(pygame.Surface((vp.width, vp.height), pygame.SRCALPHA), vp)
    numbers = [int(t) for t in texts if t.lstrip("-").isdigit() and t != "0"]
    assert 4 <= len(numbers) <= 40
    step = min(abs(n) for n in numbers)
    assert all(n % step == 0 for n in numbers) and str(step)[0] in "1245"


def test_far_arrows_spread_out():
    near = Viewport(zoom=0.5)
    far = Viewport(zoom=0.05)
    spacing = render.arrow_spacing(far.scale)
    assert spacing > 1.0
    count = len(render.field_samples(far, SimpleNamespace(at=lambda x, y: (1.0, 0.0)), spacing))
    assert count <= len(render.field_samples(near, SimpleNamespace(at=lambda x, y: (1.0, 0.0))))


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
    just_out = fit_zoom((-7.0, 7.5001), MAP, margin=1.0)
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


def test_scene_draws_at_a_very_far_zoom(scene, monkeypatch):
    sizes = []
    real = sprites.draw_ship
    monkeypatch.setattr(sprites, "draw_ship", lambda surface, pos, heading, length, *a, **k:
                        sizes.append(length) or real(surface, pos, heading, length, *a, **k))
    surface = _surface()
    _launch(scene, "0", "10")
    _run_until(scene, lambda: scene.flight.unbound)
    for zoom in (0.3, 1e-2, 1e-4):
        scene.camera.zoom = zoom
        scene.draw(surface)
    # The ship stays visible: never under half its usual size.
    assert min(sizes) >= 0.5 * scene.viewport.length(scene.ship.length) - 1e-9
    assert len(scene._mips) <= game_module.ZOOM_LEVELS_KEPT


def test_arrow_zoom_levels_step_by_at_most_a_cube_root_of_two():
    for zoom in (1.0, 0.9, 0.5, 0.31, 1e-3):
        i = game_module.zoom_level(zoom)
        assert game_module.level_zoom(i) <= zoom + 1e-12
        assert zoom / game_module.level_zoom(i) <= 2 ** (1 / 3) + 1e-9
