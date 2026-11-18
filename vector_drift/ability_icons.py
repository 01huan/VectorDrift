"""Ability icons: the ability's picture, or a letter avatar until it has one.

Every ability has an image slot ``ability.<id without "ability_">``
(``assets/images/abilities/<that>.png``, e.g. ``ability.boost`` ->
``abilities/boost.png``). Abilities without a picture show a letter avatar
instead: a rounded square with one capital letter, like a name's initial
used as a profile picture. Adding the PNG later switches that ability to the
picture with no code change; the shop cards and the game panel both draw
through :func:`draw_ability_icon`.
"""

from __future__ import annotations

import pygame

from . import config
from .abilities import ABILITIES

ID_PREFIX = "ability_"

# Avatar backgrounds, picked per ability from its id (stable between runs).
AVATAR_COLORS = (
    (64, 112, 196),     # blue
    (46, 150, 120),     # teal
    (156, 92, 196),     # violet
    (196, 120, 52),     # amber
    (188, 72, 96),      # rose
    (84, 140, 64),      # green
    (60, 150, 180),     # cyan
)
AVATAR_TEXT = (255, 255, 255)

_avatar_cache: dict[tuple, pygame.Surface] = {}


def short_id(ability_id: str) -> str:
    """``ability_boost`` -> ``boost`` (the picture's file name without .png)."""
    return ability_id[len(ID_PREFIX):] if ability_id.startswith(ID_PREFIX) else ability_id


def image_key(ability_id: str) -> str:
    """The image slot of an ability: ``ability.boost`` for ``ability_boost``."""
    return f"ability.{short_id(ability_id)}"


def avatar_letters(abilities=None) -> dict[str, str]:
    """ability id -> its avatar letter, all different.

    In registry order (the shop's order), each ability takes the first letter
    of its name that no earlier ability took, moving on through the name's
    letters while they are used up. Abilities with a picture take a letter
    too, so removing a picture never makes two avatars alike.
    """
    if abilities is None:
        abilities = list(ABILITIES.values())
    taken: set[str] = set()
    letters: dict[str, str] = {}
    for ability in abilities:
        name = getattr(ability, "name", "") or ""
        pool = [c.upper() for c in name if c.isalpha()]
        pool += [c.upper() for c in short_id(ability.id) if c.isalpha()]
        pool += [chr(c) for c in range(ord("A"), ord("Z") + 1)]
        letter = next((c for c in pool if c not in taken), "?")
        taken.add(letter)
        letters[ability.id] = letter
    return letters


def avatar_letter(ability_id: str) -> str:
    return avatar_letters().get(ability_id, "?")


def avatar_color(ability_id: str) -> tuple[int, int, int]:
    return AVATAR_COLORS[sum(map(ord, ability_id)) % len(AVATAR_COLORS)]


def has_picture(ability_id: str) -> bool:
    from .image_assets import source_size

    return source_size(image_key(ability_id)) is not None


def _avatar(ability_id: str, side: int) -> pygame.Surface:
    key = (ability_id, avatar_letter(ability_id), side)
    surf = _avatar_cache.get(key)
    if surf is None:
        from .ui_fonts import get_font

        surf = pygame.Surface((side, side), pygame.SRCALPHA)
        pygame.draw.rect(surf, avatar_color(ability_id), surf.get_rect(),
                         border_radius=max(2, round(side * 0.22)))
        size = max(6, round(side / config.UI_SCALE * 0.6))
        text = get_font(size, "bold").render(avatar_letter(ability_id), True, AVATAR_TEXT)
        surf.blit(text, text.get_rect(center=(side / 2, side / 2 + 1)))
        _avatar_cache[key] = surf
    return surf


def ability_icon(ability_id: str, side: int) -> pygame.Surface:
    """The ability's picture at ``side`` x ``side`` real px, else its letter avatar."""
    from .image_assets import load_image

    side = max(1, int(side))
    img = load_image(image_key(ability_id), size_px=(side, side))
    return img if img is not None else _avatar(ability_id, side)


def draw_ability_icon(surface, ability_id: str, center, side: int, alpha: int = 255):
    """Draw the ability's icon centred at ``center``; ``alpha`` < 255 fades it."""
    icon = ability_icon(ability_id, side)
    if alpha < 255:
        icon = icon.copy()
        icon.set_alpha(alpha)
    rect = icon.get_rect(center=(round(center[0]), round(center[1])))
    surface.blit(icon, rect)
    return rect


__all__ = [
    "AVATAR_COLORS", "ability_icon", "avatar_color", "avatar_letter", "avatar_letters",
    "draw_ability_icon", "has_picture", "image_key", "short_id",
]
