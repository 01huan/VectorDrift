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
