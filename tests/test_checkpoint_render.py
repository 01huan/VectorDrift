"""Checkpoint art and the pan between level sections (headless)."""

import math
from types import SimpleNamespace

import pygame
import pytest

from vector_drift import config, image_assets, sprites
from vector_drift.data import SHIPS, ObstacleSpec, SectionSpec, multi_section_level
from vector_drift.scenes import game as game_module
from vector_drift.scenes.base import SceneManager
from vector_drift.scenes.game import PANNING, SETUP, GameScene, pan_offsets

pytestmark = pytest.mark.usefixtures("pygame_display")

ROCK = ObstacleSpec(center=(-5.0, 4.0), radius=0.8)
# Pans (14, 3) then (14, -5), as in test_checkpoints.
THREE = multi_section_level(
    id=91, name="Three Screens", ship_id="ship01", lives=3,
    sections=(
        SectionSpec(start=(-7.0, 0.0), target_center=(7.0, 0.0), obstacles=(ROCK,)),
        SectionSpec(start=(-7.0, -3.0), target_center=(7.0, -3.0)),
        SectionSpec(start=(-7.0, 2.0), target_center=(7.0, 2.0)),
    ),
)


@pytest.fixture(autouse=True)
def fake_level(monkeypatch):
    real = game_module.get_level
    monkeypatch.setattr(game_module, "get_level",
                        lambda lid, seed=None: THREE if lid == THREE.id else real(lid, seed=seed))


@pytest.fixture
def drawn(monkeypatch):
    """Record where checkpoints, planets, rocks and start pads are drawn (screen px)."""
    calls = {"checkpoint": [], "target": [], "obstacle": [], "start": []}
    for name, key in (("draw_checkpoint", "checkpoint"), ("draw_target", "target"),
                      ("draw_obstacle", "obstacle"), ("draw_start_marker", "start")):
        real = getattr(sprites, name)

        def spy(surface, center, *args, _real=real, _key=key, **kwargs):
            calls[_key].append(tuple(center))
            return _real(surface, center, *args, **kwargs)
        monkeypatch.setattr(sprites, name, spy)
    return calls


def _audio():
    return SimpleNamespace(play=lambda *a, **k: None, start_loop=lambda *a, **k: None,
                           stop_loop=lambda *a, **k: None, toggle_mute=lambda: None)


def _scene():
    manager = SceneManager(_audio())
    manager.session.level_id = THREE.id
    manager.session.fx_text, manager.session.fy_text = "5", "0"
    scene = GameScene(manager)
    manager.switch(scene)
    return scene


def _surface():
    return pygame.Surface((config.WINDOW_W, config.WINDOW_H))


def _reach_checkpoint(scene):
    scene._try_launch()
    for _ in range(400):
        scene.update(0.05)
        if scene.state != game_module.FLIGHT:
            break
    assert scene.state == PANNING


def _near(points, expected, tol=1.0):
    return any(math.dist(p, expected) <= tol for p in points)


# --- the checkpoint renderer ------------------------------------------------------
CHECKPOINT_PATH = image_assets.IMAGES_DIR / image_assets.get_spec("target.checkpoint").path


@pytest.fixture
def no_picture(monkeypatch):
    image_assets.clear_cache()
    monkeypatch.setitem(image_assets._SPECS, "target.checkpoint",
                        image_assets.AssetSpec("target.checkpoint", image_assets.Path("targets/missing.png")))
    yield
    image_assets.clear_cache()


def test_checkpoint_picture_is_a_small_square_png():
    assert CHECKPOINT_PATH.exists()
    assert CHECKPOINT_PATH.stat().st_size <= 100 * 1024
    img = pygame.image.load(str(CHECKPOINT_PATH)).convert_alpha()
    assert img.get_size() == (512, 512)
    assert img.get_at((0, 0)).a == 0                        # see-through corners


def test_checkpoint_uses_the_picture_when_it_exists():
    image_assets.clear_cache()
    surface = pygame.Surface((200, 200), pygame.SRCALPHA)

    sprites.draw_checkpoint(surface, (100, 100), 48, 0.0, SHIPS["ship01"])

    box = surface.get_bounding_rect()
    assert 80 <= box.width <= 97 and 80 <= box.height <= 97   # the picture at 2 x radius
    assert surface.get_at((100 - 36 + 3, 100 - 36 + 3))[:3] != sprites.CHECKPOINT_FILL


def test_checkpoint_draws_without_a_window_or_a_picture(no_picture):
    surface = pygame.Surface((200, 200), pygame.SRCALPHA)

    sprites.draw_checkpoint(surface, (100, 100), 48, 0.0, SHIPS["ship01"])

    corner = (100 - 0.75 * 48, 100 - 0.75 * 48)          # inside the square, outside the ship
    assert surface.get_at((round(corner[0]) + 3, round(corner[1]) + 3))[:3] == sprites.CHECKPOINT_FILL
    assert surface.get_at((5, 5)).a == 0                    # nothing outside the square


def test_checkpoint_draws_without_a_ship_and_ignores_bad_numbers():
    surface = pygame.Surface((100, 100), pygame.SRCALPHA)
    sprites.draw_checkpoint(surface, (50, 50), 30, 0.0)
    for center, radius in (((math.nan, 0), 30), ((0, 0), math.inf), (None, 30), ((1e9, 1e9), 30),
                           ((50, 50), 0)):
        sprites.draw_checkpoint(surface, center, radius, 0.0, SHIPS["ship01"])


def test_checkpoint_renderer_is_replaceable(no_picture, monkeypatch):
    seen = []
    monkeypatch.setitem(sprites.CHECKPOINT_RENDERERS, "test",
                        lambda surface, center, radius, t, ship: seen.append((center, radius, ship)))
    sprites.draw_checkpoint(pygame.Surface((80, 80)), (40, 40), 20, 0.0, SHIPS["ship02"], kind="test")
    assert seen == [((40.0, 40.0), 20.0, SHIPS["ship02"])]


# --- pan offsets ------------------------------------------------------------------
@pytest.mark.parametrize("shift", [(14.0, 0.0), (14.0, 3.0), (0.0, 11.0), (-14.0, -5.0)])
def test_pan_offsets_at_the_start_and_the_end(shift):
    old, new = pan_offsets(shift, 0.0)
    assert old == (0.0, 0.0) and new == shift              # next section waits one pan away
    old, new = pan_offsets(shift, 1.0)
    assert old == (-shift[0], -shift[1]) and new == (0.0, 0.0)


def test_pan_offsets_keep_the_checkpoint_aligned():
    shift = (14.0, 3.0)
    here, there = THREE.sections[0].target_center, THREE.sections[1].start
    for p in (0.0, 0.3, 0.5, 1.0):
        old, new = pan_offsets(shift, p)
        assert (here[0] + old[0], here[1] + old[1]) == pytest.approx(
            (there[0] + new[0], there[1] + new[1]))


# --- what is drawn ----------------------------------------------------------------
def test_first_section_shows_a_checkpoint_not_a_planet(drawn):
    scene = _scene()
    scene.draw(_surface())
    vp = scene.viewport
    assert drawn["checkpoint"] == [vp.to_screen(7.0, 0.0)]
    assert drawn["target"] == []
    assert drawn["start"] == [vp.to_screen(-7.0, 0.0)]


def test_both_sections_are_drawn_while_panning(drawn):
    scene = _scene()
    _reach_checkpoint(scene)
    vp = scene.viewport
    for key in drawn:
        drawn[key].clear()

    scene.draw(_surface())                                  # progress 0: camera still on section 1

    assert scene.pan.progress == 0.0
    # The shared checkpoint where section 1's target was ...
    assert _near(drawn["checkpoint"], vp.to_screen(7.0, 0.0))
    # ... section 2's target one pan (14, 3) away, off to the right ...
    assert _near(drawn["checkpoint"], vp.to_screen(7.0 + 14.0, -3.0 + 3.0))
    # ... and section 1's rock and start pad where they were.
    assert _near(drawn["obstacle"], vp.to_screen(*ROCK.center))
    assert _near(drawn["start"], vp.to_screen(-7.0, 0.0))
    assert drawn["target"] == []


def test_after_the_pan_the_next_section_sits_in_place(drawn):
    scene = _scene()
    _reach_checkpoint(scene)
    scene.update(config.CHECKPOINT_PAN_DURATION)
    assert scene.state == SETUP
    vp = scene.viewport
    for key in drawn:
        drawn[key].clear()

    scene.draw(_surface())

    # Section 2: a checkpoint on its start (no start pad) and on its target.
    assert sorted(drawn["checkpoint"]) == sorted([vp.to_screen(-7.0, -3.0), vp.to_screen(7.0, -3.0)])
    assert drawn["start"] == []
    assert drawn["obstacle"] == []                          # section 1's rock is gone
    assert drawn["target"] == []


def test_the_last_section_shows_the_planet(drawn):
    scene = _scene()
    for _ in range(2):
        _reach_checkpoint(scene)
        scene.update(config.CHECKPOINT_PAN_DURATION)
    vp = scene.viewport
    for key in drawn:
        drawn[key].clear()

    scene.draw(_surface())

    assert drawn["target"] == [vp.to_screen(7.0, 2.0)]
    assert drawn["checkpoint"] == [vp.to_screen(-7.0, 2.0)]


def test_mid_pan_frames_draw_without_errors(drawn):
    scene = _scene()
    _reach_checkpoint(scene)
    surface = _surface()
    while scene.state == PANNING:
        scene.draw(surface)
        scene.update(0.1)
    scene.draw(surface)
    assert drawn["checkpoint"]


def test_a_timeout_resume_after_the_checkpoint_shows_the_pad_too(drawn):
    scene = _scene()
    _reach_checkpoint(scene)
    scene.update(config.CHECKPOINT_PAN_DURATION)
    scene.launch_pos = (-3.0, -3.0)
    vp = scene.viewport
    for key in drawn:
        drawn[key].clear()

    scene.draw(_surface())

    assert drawn["start"] == [vp.to_screen(-3.0, -3.0)]
    assert _near(drawn["checkpoint"], vp.to_screen(-7.0, -3.0))
