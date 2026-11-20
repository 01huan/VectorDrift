"""The daily challenge flies its own ship, Daybreak; every other level keeps its ship."""

from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pygame
import pytest

from vector_drift import config, daily_level, image_assets, sprites
from vector_drift.daily_level import DAILY_SHIP, daily_map, generate_daily
from vector_drift.data import SHIPS, default_ship_id, level_ship_id
from vector_drift.level_presets import RANDOM_LEVEL_ID
from vector_drift.replay import ReplayRecord, normalize_records
from vector_drift.scenes.base import SceneManager
from vector_drift.scenes.game import GameScene
from vector_drift.scenes.replay import ReplayScene

pytestmark = pytest.mark.usefixtures("pygame_display")

DAY = date(2026, 11, 19)


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    monkeypatch.setattr(daily_level, "daily_today", lambda now=None: DAY)


def _manager():
    audio = SimpleNamespace(play=lambda *a, **k: None, toggle_mute=lambda: None,
                            start_loop=lambda *a, **k: None, stop_loop=lambda *a, **k: None)
    return SceneManager(audio)


def _game(manager, level_id):
    manager.session.level_id = level_id
    manager.session.random_seed = 123 if level_id in (8, RANDOM_LEVEL_ID) else None
    if level_id == config.DAILY_LEVEL_ID:
        manager.session.daily_day = DAY
    return GameScene(manager)


# --- the ship ----------------------------------------------------------------------

def test_daybreak_is_registered_with_the_same_physics():
    ship = SHIPS["daybreak"]
    assert (ship.id, ship.name, ship.mass, ship.hull_radius) == ("daybreak", "Daybreak", 1.0, 0.2)
    assert ship.price == 0                          # never sold
    assert "ship00" not in SHIPS


def test_daybreak_has_its_picture():
    spec = image_assets.get_spec("ship.daybreak")
    assert spec is not None and spec.path == Path("ships/daybreak.png")
    path = image_assets.IMAGES_DIR / spec.path
    assert pygame.image.load(str(path)).get_size() == (512, 512)


def test_daybreak_without_its_picture_falls_back_to_the_code_drawn_ship(tmp_path, monkeypatch):
    monkeypatch.setattr(image_assets, "IMAGES_DIR", tmp_path)       # no ships/daybreak.png
    image_assets.clear_cache()
    try:
        surface = pygame.Surface((200, 200), pygame.SRCALPHA)
        sprites.draw_ship(surface, (100, 100), 0.3, 120, SHIPS["daybreak"])
        sprites.draw_ship(surface, (100, 100), 2.8, 120, SHIPS["daybreak"])   # heading left
        sprites.draw_ship_icon(surface, (40, 40), 18, SHIPS["daybreak"], alive=False)
        assert pygame.surfarray.pixels_alpha(surface).max() > 0
    finally:
        image_assets.clear_cache()


# --- the daily challenge flies it ------------------------------------------------

def test_the_daily_challenge_flies_daybreak():
    assert DAILY_SHIP is SHIPS["daybreak"]
    assert generate_daily(DAY).level.ship_id == "daybreak"
    assert level_ship_id(config.DAILY_LEVEL_ID) == "daybreak"


def test_the_daily_game_shows_daybreak_in_the_panel_and_lives(monkeypatch):
    scene = _game(_manager(), config.DAILY_LEVEL_ID)
    assert scene.ship.id == scene.flyable_ship.id == "daybreak"

    names, icons = [], []
    from vector_drift.scenes import game_render_hud
    real_text = game_render_hud.draw_text
    monkeypatch.setattr(game_render_hud, "draw_text",
                        lambda s, text, *a, **k: (names.append(text), real_text(s, text, *a, **k))[1])
    monkeypatch.setattr(sprites, "draw_ship_icon",
                        lambda surface, center, size, ship, alive=True: icons.append(ship.id))
    scene.draw(pygame.Surface((config.WINDOW_W, config.WINDOW_H)))
    assert "Daybreak" in names
    assert icons and set(icons) == {"daybreak"}


# --- nothing else changes ---------------------------------------------------------

@pytest.mark.parametrize("level_id, ship_id",
                         [(n, f"ship{n:02d}") for n in range(1, 12)] + [(RANDOM_LEVEL_ID, "ship12")])
def test_fixed_and_random_levels_keep_their_ship(level_id, ship_id):
    assert level_ship_id(level_id) == ship_id
    assert _game(_manager(), level_id).ship.id == ship_id


def test_custom_and_community_levels_still_fly_ship01(monkeypatch):
    from vector_drift import data
    monkeypatch.setitem(data.CUSTOM_LEVELS, 3, object())
    assert level_ship_id(3) == "ship01"
    monkeypatch.delitem(data.CUSTOM_LEVELS, 3)
    monkeypatch.setitem(data.COMMUNITY_LEVELS, 5, object())
    assert level_ship_id(5) == "ship01"


@pytest.mark.parametrize("level_id", [None, 0, 1, 11, 15, 16, 99, 900, RANDOM_LEVEL_ID,
                                      -3, "x", "daybreak", 2.5, True])
def test_default_ship_id_never_picks_daybreak(level_id):
    assert default_ship_id(level_id) != "daybreak"


# --- old daily replays -------------------------------------------------------------

def _daily_replay(ship_id):
    return ReplayRecord(level_id=config.DAILY_LEVEL_ID, ship_id=ship_id, created_at=1.0,
                        fx_text="0", fy_text="0", daily_day=DAY.isoformat(),
                        daily_version=config.DAILY_GENERATOR_VERSION).to_dict()


@pytest.mark.parametrize("ship_id, shown", [("ship01", "ship01"), ("daybreak", "Daybreak")])
def test_a_daily_replay_plays_with_the_ship_it_was_flown_with(ship_id, shown, monkeypatch):
    from vector_drift.scenes import replay as replay_scene
    manager = _manager()
    manager.session.replays = normalize_records([_daily_replay(ship_id)])
    scene = ReplayScene(manager)

    assert [r["ship_id"] for r in scene.records] == [ship_id]       # old data untouched
    assert scene._ship.id == ship_id
    assert scene._level == daily_map(DAY).level
    texts = []
    real_text = replay_scene.draw_text
    monkeypatch.setattr(replay_scene, "draw_text",
                        lambda s, text, *a, **k: (texts.append(text), real_text(s, text, *a, **k))[1])
    scene.draw(pygame.Surface((config.WINDOW_W, config.WINDOW_H)))
    assert shown in texts
