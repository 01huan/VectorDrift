"""Black and white holes show their pictures; every pair shares the 01 picture."""
import pygame
import pytest

from vector_drift import image_assets, sprites

pytestmark = pytest.mark.usefixtures("pygame_display")

HOLE_KEYS = ("black_hole.black_hole01", "white_hole.white_hole01")


def _drawn(kind, pair_index):
    surface = pygame.Surface((200, 200), pygame.SRCALPHA)
    sprites.draw_hole(surface, (100, 100), 60, 0.0, kind=kind, pair_index=pair_index)
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
