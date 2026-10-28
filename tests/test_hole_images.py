"""Black and white holes show their pictures; every pair shares the 01 picture.

The pictures turn slowly: black holes clockwise (arms drawn inward),
white holes counter-clockwise (arms pushed outward)."""
import pygame
import pytest

from vector_drift import image_assets, sprites

pytestmark = pytest.mark.usefixtures("pygame_display")

HOLE_KEYS = ("black_hole.black_hole01", "white_hole.white_hole01")


def _drawn(kind, pair_index, t=0.0):
    surface = pygame.Surface((200, 200), pygame.SRCALPHA)
    sprites.draw_hole(surface, (100, 100), 60, t, kind=kind, pair_index=pair_index)
    return surface


def test_both_holes_ship_a_256px_image():
    # Real assets/ on purpose: the 01 pictures are what every pair shows.
    for key in HOLE_KEYS:
        path = image_assets.IMAGES_DIR / image_assets.get_spec(key).path
        assert pygame.image.load(str(path)).get_size() == (256, 256)


@pytest.mark.parametrize("kind", ["black", "white"])
def test_hole_picture_is_drawn_instead_of_the_plain_circle(kind):
    image_assets.clear_cache()
    plain = (10, 10, 20) if kind == "black" else (240, 240, 255)
    pixels = {tuple(_drawn(kind, 1).get_at((x, 100)))[:3] for x in range(45, 156, 5)}
    assert pixels != {plain}


@pytest.mark.parametrize("kind", ["black", "white"])
@pytest.mark.parametrize("pair_index", [2, 5, 10, 11])
def test_later_pairs_reuse_the_first_picture(kind, pair_index):
    image_assets.clear_cache()
    first = pygame.image.tostring(_drawn(kind, 1), "RGBA")
    assert pygame.image.tostring(_drawn(kind, pair_index), "RGBA") == first


@pytest.mark.parametrize("kind", ["black", "white"])
def test_without_hole_pictures_the_code_drawn_hole_is_used(kind, tmp_path, monkeypatch):
    monkeypatch.setattr(image_assets, "IMAGES_DIR", tmp_path)
    image_assets.clear_cache()
    try:
        assert _drawn(kind, 2).get_at((100, 100)).a == 255
    finally:
        image_assets.clear_cache()


def test_pair_number_stands_out_on_both_holes():
    # The white-hole picture is white in the middle, so its number must be dark.
    from types import SimpleNamespace
    from vector_drift import config
    from vector_drift.scenes.base import SceneManager
    from vector_drift.scenes.game import GameScene

    image_assets.clear_cache()
    manager = SceneManager(SimpleNamespace(play=lambda *a: None, start_loop=lambda *a: None,
                                           stop_loop=lambda *a: None))
    manager.session.level_id = 4
    scene = GameScene(manager)
    manager.switch(scene)
    screen = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    scene.draw(screen)
    black_center, white_center, _ = scene.holes[0]
    for center, wanted in ((white_center, "dark"), (black_center, "light")):
        x, y = scene.viewport.to_screen(*center)
        half = config.px(5)
        lums = [sum(screen.get_at((int(x) + dx, int(y) + dy))[:3]) / 3
                for dx in range(-half, half + 1) for dy in range(-half, half + 1)]
        if wanted == "dark":
            assert min(lums) < 100
        else:
            assert max(lums) > 150


def test_black_holes_turn_clockwise_and_white_holes_counter_clockwise():
    # pygame angles: positive = counter-clockwise on screen.
    assert sprites._hole_spin_angle("black", 0.0) == 0.0
    assert sprites._hole_spin_angle("white", 0.0) == 0.0
    assert -180.0 < sprites._hole_spin_angle("black", 1.0) < 0.0
    assert 0.0 < sprites._hole_spin_angle("white", 1.0) < 180.0
    assert sprites._hole_spin_angle("black", 1.0) == -sprites._hole_spin_angle("white", 1.0)


def test_holes_turn_slowly():
    # One full turn every HOLE_SPIN_PERIOD_S seconds, slow enough not to distract.
    assert sprites.HOLE_SPIN_PERIOD_S >= 6.0
    period = sprites.HOLE_SPIN_PERIOD_S
    for kind in ("black", "white"):
        assert abs(sprites._hole_spin_angle(kind, period)) == pytest.approx(360.0)


@pytest.mark.parametrize("kind", ["black", "white"])
def test_hole_picture_turns_with_time_and_stays_centred(kind):
    image_assets.clear_cache()
    still = pygame.image.tostring(_drawn(kind, 1, t=1.5), "RGBA")
    assert pygame.image.tostring(_drawn(kind, 1, t=1.5), "RGBA") == still
    turned = _drawn(kind, 1, t=2.5)
    assert pygame.image.tostring(turned, "RGBA") != still
    box = turned.get_bounding_rect(min_alpha=16)
    assert abs(box.centerx - 100) <= 2 and abs(box.centery - 100) <= 2
    assert box.width <= 124 and box.height <= 124


@pytest.mark.parametrize("kind", ["black", "white"])
def test_code_drawn_hole_does_not_need_to_turn(kind, tmp_path, monkeypatch):
    monkeypatch.setattr(image_assets, "IMAGES_DIR", tmp_path)
    image_assets.clear_cache()
    try:
        first = pygame.image.tostring(_drawn(kind, 1, t=0.0), "RGBA")
        assert pygame.image.tostring(_drawn(kind, 1, t=2.5), "RGBA") == first
    finally:
        image_assets.clear_cache()
