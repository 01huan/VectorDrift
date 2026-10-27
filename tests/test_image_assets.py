"""image_assets.load_image: every requested size gets its own cached surface."""
from pathlib import Path

import pygame
import pytest

from vector_drift import image_assets
from vector_drift.config import px
from vector_drift.image_assets import AssetSpec, load_image

pytestmark = pytest.mark.usefixtures("pygame_display")


@pytest.fixture
def images(tmp_path, monkeypatch):
    """A temporary images dir holding one 64x64 PNG, registered as "test.ship".

    Nothing here depends on the real files in assets/; the cache starts and
    ends empty for every test.
    """
    (tmp_path / "ships").mkdir()
    surf = pygame.Surface((64, 64), pygame.SRCALPHA)
    surf.fill((200, 60, 60, 255))
    pygame.image.save(surf, str(tmp_path / "ships" / "test.png"))
    monkeypatch.setattr(image_assets, "IMAGES_DIR", tmp_path)
    monkeypatch.setitem(image_assets._SPECS, "test.ship",
                        AssetSpec("test.ship", Path("ships/test.png"), display_w=30, display_h=30))
    image_assets.clear_cache()
    yield tmp_path
    image_assets.clear_cache()


@pytest.fixture
def disk_reads(monkeypatch):
    """Count calls to pygame.image.load made by image_assets."""
    calls = []
    real_load = pygame.image.load

    def counting_load(*args, **kwargs):
        calls.append(args)
        return real_load(*args, **kwargs)

    monkeypatch.setattr(image_assets.pygame.image, "load", counting_load)
    return calls


def test_same_key_at_two_sizes_returns_each_requested_size(images):
    big = load_image("test.ship", size_px=(64, 64))
    small = load_image("test.ship", size_px=(18, 18))
    assert big.get_size() == (64, 64)
    assert small.get_size() == (18, 18)
    assert load_image("test.ship", size_px=(64, 64)).get_size() == (64, 64)


def test_each_size_is_scaled_once_and_reused(images):
    first = load_image("test.ship", size_px=(18, 18))
    assert load_image("test.ship", size_px=(18, 18)) is first


def test_default_size_comes_from_the_spec(images):
    assert load_image("test.ship").get_size() == (px(30), px(30))


def test_png_is_read_from_disk_once_for_all_sizes(images, disk_reads):
    load_image("test.ship", size_px=(64, 64))
    load_image("test.ship", size_px=(18, 18))
    load_image("test.ship")
    assert len(disk_reads) == 1


def test_missing_file_is_cached_as_none(images, monkeypatch):
    monkeypatch.setitem(image_assets._SPECS, "test.missing",
                        AssetSpec("test.missing", Path("ships/nope.png")))
    assert load_image("test.missing", size_px=(18, 18)) is None
    # Even if the file shows up later, it is not looked for again.
    (images / "ships" / "test.png").replace(images / "ships" / "nope.png")
    assert load_image("test.missing", size_px=(64, 64)) is None


def test_unreadable_file_is_cached_as_none(images, monkeypatch, disk_reads):
    (images / "ships" / "broken.png").write_bytes(b"not a png")
    monkeypatch.setitem(image_assets._SPECS, "test.broken",
                        AssetSpec("test.broken", Path("ships/broken.png")))
    assert load_image("test.broken", size_px=(18, 18)) is None
    assert load_image("test.broken", size_px=(64, 64)) is None
    assert len(disk_reads) == 1


# --- lives counter: a used life is the same picture in grey --------------------

def _rgb_alpha(surface):
    import numpy as np
    return (np.array(pygame.surfarray.pixels3d(surface)),
            np.array(pygame.surfarray.pixels_alpha(surface)))


def test_used_life_icon_is_the_ship_picture_in_grey(images, monkeypatch):
    from types import SimpleNamespace
    from vector_drift import sprites
    monkeypatch.setitem(image_assets._SPECS, "ship.test",
                        AssetSpec("ship.test", Path("ships/test.png")))
    ship = SimpleNamespace(id="test")
    alive = sprites.ship_icon_surface(ship, 18, alive=True)
    used = sprites.ship_icon_surface(ship, 18, alive=False)

    assert used.get_size() == alive.get_size()
    rgb, alpha = _rgb_alpha(used)
    assert (rgb[..., 0] == rgb[..., 1]).all() and (rgb[..., 1] == rgb[..., 2]).all()
    opaque = alpha > 128
    assert opaque.any()
    assert abs(rgb[..., 0][opaque].mean() - sprites.USED_LIFE_BRIGHTNESS) < 4
    assert sprites.ship_icon_surface(ship, 18, alive=False) is used    # cached


def test_used_life_icon_without_a_png_is_still_the_code_drawn_rocket(images, monkeypatch):
    from vector_drift import sprites
    from vector_drift.data import SHIPS
    # images points IMAGES_DIR at a folder without ships/ship01.png.
    used = sprites.ship_icon_surface(SHIPS["ship01"], 18, alive=False)
    rgb, alpha = _rgb_alpha(used)
    opaque = alpha > 128
    r, b = rgb[..., 0][opaque].mean(), rgb[..., 2][opaque].mean()
    assert b > r + 10        # the blue-grey code-drawn rocket, not a grey picture


def test_every_ship_has_its_own_512px_image():
    # Uses the real assets/ on purpose: each skin in SHIPS must ship a picture.
    from vector_drift.data import SHIPS
    image_assets.clear_cache()
    try:
        for ship_id in SHIPS:
            spec = image_assets.get_spec(f"ship.{ship_id}")
            assert spec is not None, ship_id
            path = image_assets.IMAGES_DIR / spec.path
            assert path.name == f"{ship_id}.png"
            assert pygame.image.load(str(path)).get_size() == (512, 512)
    finally:
        image_assets.clear_cache()


def test_planet_has_a_512px_image():
    # Real assets/ on purpose: the target must ship its picture.
    spec = image_assets.get_spec("target.planet")
    path = image_assets.IMAGES_DIR / spec.path
    assert pygame.image.load(str(path)).get_size() == (512, 512)


@pytest.mark.parametrize("kind", ["bomb", "add_time", "penetrate"])
def test_every_pickup_has_a_256px_image(kind):
    # Real assets/ on purpose: each pickup kind ships its icon.
    path = image_assets.IMAGES_DIR / image_assets.get_spec(f"pickup.{kind}").path
    assert pygame.image.load(str(path)).get_size() == (256, 256)
