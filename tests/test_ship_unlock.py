"""Each level flies its own ship: level N flies shipNN, else ship01; no picking."""
import math

import pygame
import pytest

from vector_drift import data_models
from vector_drift.data import SHIPS, ShipSpec, default_ship_id, level_ship_id
from vector_drift.level_presets import RANDOM_LEVEL_ID
from vector_drift.scenes.base import SceneManager

pytestmark = pytest.mark.usefixtures("pygame_display")


def test_ships_01_to_15_and_daybreak_share_the_same_physics():
    # ship01-15 for the levels, daybreak for the daily challenge (test_daily_ship).
    assert list(SHIPS) == [f"ship{n:02d}" for n in range(1, 16)] + ["daybreak"]
    for sid, ship in SHIPS.items():
        name = "Daybreak" if sid == "daybreak" else sid
        assert (ship.id, ship.name, ship.mass, ship.hull_radius) == (sid, name, 1.0, 0.2)


def test_level_n_flies_ship_n():
    for n in range(1, 12):
        assert level_ship_id(n) == f"ship{n:02d}"
    assert level_ship_id(RANDOM_LEVEL_ID) == "ship12"   # the random level is numbered 12


def test_levels_whose_ship_is_not_made_yet_fly_ship01():
    for n in (16, 24):                           # ship16+ are not in SHIPS (yet)
        assert f"ship{n:02d}" not in SHIPS
        assert level_ship_id(n) == "ship01"
    for odd in (None, 0, -3, "x", 2.5, True):
        assert default_ship_id(odd) == "ship01"


def test_a_new_ship_in_ships_is_flown_by_its_level(monkeypatch):
    ships = dict(SHIPS)
    ships["ship16"] = ShipSpec(id="ship16", name="ship16", mass=1.0, hull_radius=0.2)
    monkeypatch.setattr(data_models, "SHIPS", ships)
    assert level_ship_id(16) == "ship16"


def test_custom_and_community_levels_fly_ship01(monkeypatch):
    from vector_drift import data

    monkeypatch.setitem(data.CUSTOM_LEVELS, 3, object())       # even with a campaign-like id
    assert level_ship_id(3) == "ship01"
    monkeypatch.delitem(data.CUSTOM_LEVELS, 3)
    monkeypatch.setitem(data.COMMUNITY_LEVELS, 5, object())
    assert level_ship_id(5) == "ship01"


class Quiet:
    def __getattr__(self, name):
        return lambda *a, **k: None


def game_on(manager, level_id):
    from vector_drift.scenes.game import GameScene
    manager.session.level_id = level_id
    if level_id in (8, RANDOM_LEVEL_ID):
        manager.session.random_seed = 123
    return GameScene(manager)


@pytest.mark.parametrize("level_id, ship_id",
                         [(n, f"ship{n:02d}") for n in range(1, 12)] + [(RANDOM_LEVEL_ID, "ship12")])
def test_game_flies_the_levels_ship_with_no_arrows(level_id, ship_id):
    scene = game_on(SceneManager(Quiet()), level_id)
    assert scene.ship.id == ship_id
    assert scene.flyable_ship.id == ship_id
    assert not hasattr(scene, "prev_ship") and not hasattr(scene, "next_ship")
    assert not hasattr(scene, "_switch_ship")


def test_a_saved_ship_pick_and_old_owned_ships_are_ignored():
    manager = SceneManager(Quiet())
    manager.session.ship_id = "ship05"                     # an old pick
    manager.session.owned_ships = {"ship01", "ship05"}     # an old save's purchases
    scene = game_on(manager, 2)
    assert scene.ship.id == "ship02"
    scene.editor.set_lines(["1", "0"])
    scene._on_text_change(scene.editor)
    scene._try_launch()
    assert scene.flight is not None          # the old pick never blocks the launch
    assert scene.ship.id == "ship02"


def test_lives_show_the_levels_ship(monkeypatch):
    from vector_drift import sprites
    scene = game_on(SceneManager(Quiet()), 3)
    drawn = []
    monkeypatch.setattr(sprites, "draw_ship_icon",
                        lambda surface, center, size, ship, alive=True: drawn.append(ship.id))
    scene.draw(pygame.Surface((1280, 720)))
    assert drawn and set(drawn) == {"ship03"}


def test_retry_and_level_select_keep_the_levels_ship():
    from vector_drift.scenes.game import GameScene
    from vector_drift.scenes.levels import LevelSelectScene
    manager = SceneManager(Quiet())
    game_on(manager, 4)
    assert GameScene(manager).ship.id == "ship04"            # Retry / Replay
    LevelSelectScene(manager)._start(4)                      # back in from level select
    assert manager.scene.ship.id == "ship04"


def test_grey_ship_drawing_still_works():
    import numpy as np
    from vector_drift import sprites
    surface = pygame.Surface((200, 200), pygame.SRCALPHA)
    sprites.draw_ship(surface, (100, 100), math.pi / 4, 150, SHIPS["ship03"], grey=True)
    rgb = np.array(pygame.surfarray.pixels3d(surface))
    opaque = np.array(pygame.surfarray.pixels_alpha(surface)) > 128
    assert opaque.any()
    assert (rgb[..., 0][opaque] == rgb[..., 1][opaque]).all()
    assert (rgb[..., 1][opaque] == rgb[..., 2][opaque]).all()
