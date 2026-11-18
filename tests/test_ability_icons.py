"""Ability icons: pictures for some abilities, distinct letter avatars for the rest."""
from pathlib import Path

import pygame
import pytest

from vector_drift import ability_icons, image_assets
from vector_drift.abilities import ABILITIES, Ability
from vector_drift.ability_icons import (ability_icon, avatar_letters, draw_ability_icon,
                                        has_picture, image_key, short_id)

pytestmark = pytest.mark.usefixtures("pygame_display")

IMAGES = Path(image_assets.IMAGES_DIR)
WITH_PICTURE = tuple(ABILITIES)      # every ability has its picture now


@pytest.fixture(autouse=True)
def fresh_cache():
    image_assets.clear_cache()
    yield
    image_assets.clear_cache()


def test_image_key_and_file_drop_the_ability_prefix():
    assert short_id("ability_boost") == "boost"
    assert image_key("ability_brake") == "ability.brake"
    for aid in ABILITIES:
        spec = image_assets.get_spec(image_key(aid))
        assert spec is not None, aid
        assert spec.path == Path("abilities") / f"{short_id(aid)}.png"


@pytest.mark.parametrize("aid", WITH_PICTURE)
def test_every_ability_ships_a_256_px_palette_picture(aid):
    path = IMAGES / "abilities" / f"{short_id(aid)}.png"
    surf = pygame.image.load(str(path))
    assert surf.get_size() == (256, 256)
    assert path.read_bytes()[25] == 3       # PNG colour type 3: 256-colour palette, like the pickups
    assert path.stat().st_size < 40_000
    assert has_picture(aid)


def test_avatar_letters_are_the_agreed_ones_and_all_different():
    letters = avatar_letters()
    assert letters["ability_shield_pulse"] == "S"
    assert letters["ability_magnet"] == "M"
    assert letters["ability_time_freeze"] == "T"
    assert letters["ability_phase"] == "P"
    # Abilities with a picture take a letter too (Blink moves on to L).
    assert letters["ability_boost"] == "B"
    assert letters["ability_brake"] == "R"
    assert letters["ability_blink"] == "L"
    assert len(set(letters.values())) == len(ABILITIES)


def test_a_used_first_letter_moves_on_through_the_name():
    def make(aid, name):
        return Ability(id=aid, name=name, key="", key_code=0, description="", price=1)

    letters = avatar_letters([make("a1", "Bolt"), make("a2", "Bob"), make("a3", "Boo")])
    assert letters == {"a1": "B", "a2": "O", "a3": "A"}   # "Boo" has no unused letter left


def test_missing_picture_draws_the_letter_avatar(monkeypatch, tmp_path):
    monkeypatch.setattr(image_assets, "IMAGES_DIR", tmp_path)
    assert not has_picture("ability_boost")
    icon = ability_icon("ability_boost", 40)
    assert icon.get_size() == (40, 40)
    # The avatar's rounded square in its colour, the corner left clear.
    assert icon.get_at((20, 6))[:3] == ability_icons.avatar_color("ability_boost")
    assert icon.get_at((0, 0)).a == 0


def test_adding_the_png_switches_an_ability_to_its_picture(monkeypatch, tmp_path):
    monkeypatch.setattr(image_assets, "IMAGES_DIR", tmp_path)
    assert not has_picture("ability_magnet")
    (tmp_path / "abilities").mkdir()
    pic = pygame.Surface((256, 256), pygame.SRCALPHA)
    pic.fill((10, 200, 30, 255))
    pygame.image.save(pic, str(tmp_path / "abilities" / "magnet.png"))
    image_assets.clear_cache()
    assert has_picture("ability_magnet")
    r, g, b, _a = ability_icon("ability_magnet", 30).get_at((15, 15))
    assert max(abs(r - 10), abs(g - 200), abs(b - 30)) < 5


def test_draw_ability_icon_fades_with_alpha():
    surface = pygame.Surface((60, 60))
    surface.fill((0, 0, 0))
    rect = draw_ability_icon(surface, "ability_magnet", (30, 30), 40, alpha=60)
    assert rect.center == (30, 30)
    faded = surface.get_at((30, 12))[:3]
    full = ability_icons.avatar_color("ability_magnet")
    assert sum(faded) < sum(full)
