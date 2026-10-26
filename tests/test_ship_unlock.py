"""Ship skins unlock by clearing levels: fixed level N's style is unlocked only when level N is successfully completed; no cleared level means the default style. Random levels fly any ship."""
import math

import pygame
import pytest

from vector_drift.data import DEFAULT_SHIP, SHIPS, default_ship_id, ship_unlocked
from vector_drift.scenes.base import SceneManager

pytestmark = pytest.mark.usefixtures("pygame_display")


def usable(level_id, cleared):
    return [sid for sid, ship in SHIPS.items() if ship_unlocked(ship, level_id, cleared)]


def test_fixed_level_n_flies_own_style_only_after_clearing():
    assert usable(1, cleared={}) == []
    assert usable(1, cleared={1}) == ["ship01"]

    assert usable(2, cleared={1}) == ["ship01"]
    assert usable(2, cleared={2}) == ["ship02"]
    assert usable(2, cleared={1, 2}) == ["ship01", "ship02"]

    assert usable(3, cleared={1, 2}) == ["ship01", "ship02"]
    assert usable(3, cleared={3}) == ["ship03"]


def test_random_levels_fly_every_ship_even_without_clears():
    assert usable(7, cleared={}) == list(SHIPS)
    assert usable(8, cleared={}) == list(SHIPS)


def test_a_level_starts_on_its_newest_cleared_style():
    assert default_ship_id(1, cleared_levels={}) == DEFAULT_SHIP.id
    assert default_ship_id(1, cleared_levels={1}) == "ship01"
    assert default_ship_id(2, cleared_levels={2}) == "ship02"
    assert default_ship_id(2, cleared_levels={1, 2}) == "ship02"
    assert default_ship_id(7, cleared_levels={}) == DEFAULT_SHIP.id


class Quiet:
    def __getattr__(self, name):
        return lambda *a, **k: None


def game_on(manager, level_id):
    from vector_drift.scenes.game import GameScene
    manager.session.level_id = level_id
    if level_id >= 7:
        manager.session.random_seed = 123
    return GameScene(manager)


def test_level_2_browses_back_freely_and_forward_only_to_locked_ships():
    # Before any cleared level, the default style is used.
    scene = game_on(SceneManager(Quiet()), 2)
    assert scene.ship.id == DEFAULT_SHIP.id
    assert scene.run_button.enabled

    scene._switch_ship(-1)
    assert scene.ship.id == DEFAULT_SHIP.id            # no wrap-around past the default
    assert not scene.prev_ship.enabled

    scene._switch_ship(1)
    assert scene.ship.id == "ship01"                    # shown, but not unlocked yet
    assert not scene.run_button.enabled

    scene._switch_ship(1)
    assert scene.ship.id == "ship02"                    # shown, but locked on level 2

    scene._switch_ship(1)
    assert scene.ship.id == "ship03"                    # shown, but not unlocked
    assert not scene.run_button.enabled
    scene.editor.set_lines(["1", "0"])
    scene._try_launch()
    assert scene.flight is None

    for _ in range(5):
        scene._switch_ship(1)
    assert scene.ship.id == "ship06"
    assert not scene.next_ship.enabled                   # no wrap-around past the last ship


def test_lives_show_the_default_style_before_any_clear(monkeypatch):
    from vector_drift import sprites
    scene = game_on(SceneManager(Quiet()), 2)
    scene._switch_ship(1)                        # ship01, but not unlocked yet
    drawn = []
    monkeypatch.setattr(sprites, "draw_ship_icon",
                        lambda surface, center, size, ship, alive=True: drawn.append(ship.id))
    scene.draw(pygame.Surface((1280, 720)))
    assert drawn and set(drawn) == {"default"}


def test_retry_keeps_the_chosen_ship_and_level_select_resets_it():
    from vector_drift.scenes.game import GameScene
    from vector_drift.scenes.levels import LevelSelectScene
    manager = SceneManager(Quiet())
    scene = game_on(manager, 2)
    scene._switch_ship(-1)                       # pick the default ship
    assert GameScene(manager).ship.id == DEFAULT_SHIP.id            # Retry / Replay
    LevelSelectScene(manager)._start(2)                      # back in from level select
    assert manager.scene.ship.id == DEFAULT_SHIP.id


def test_random_level_starts_on_ship06_and_flies_any_ship():
    scene = game_on(SceneManager(Quiet()), 7)
    assert scene.ship.id == "ship06"
    for _ in range(5):
        scene._switch_ship(-1)
    assert scene.ship.id == "ship01"
    assert scene.run_button.enabled


def test_locked_ship_preview_is_grey():
    import numpy as np
    from vector_drift import sprites
    surface = pygame.Surface((200, 200), pygame.SRCALPHA)
    sprites.draw_ship(surface, (100, 100), math.pi / 4, 150, SHIPS["ship03"], grey=True)
    rgb = np.array(pygame.surfarray.pixels3d(surface))
    opaque = np.array(pygame.surfarray.pixels_alpha(surface)) > 128
    assert opaque.any()
    assert (rgb[..., 0][opaque] == rgb[..., 1][opaque]).all()
    assert (rgb[..., 1][opaque] == rgb[..., 2][opaque]).all()
