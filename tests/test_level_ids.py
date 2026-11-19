"""Level ids versus level numbers.

A level's id is its identity in saves (best times, clear rewards,
achievements, replays) and never changes once given. Its number is only its
place on the level select. The random level keeps id RANDOM_LEVEL_ID (999)
and is shown right after the last fixed level, so adding a fixed level moves
its number, never its id, and the new level cannot inherit its save data.

The tests add a made-up fixed level to the shared LEVELS list for one test
only (the ``next_fixed_level`` fixture); data_levels.py is not changed.
"""

from contextlib import contextmanager
from types import SimpleNamespace

import pygame
import pytest

from vector_drift import achievements as ach
from vector_drift import config, data
from vector_drift.data import SHIPS, LevelSpec, all_levels, default_ship_id, get_level, level_number
from vector_drift.level_presets import RANDOM_LEVEL_ID, is_dynamic_level

RANDOM_BEST = 3.21


def _fixed_levels():
    # Read data.LEVELS when used, not at import: other tests may swap the list.
    return data.LEVELS


def _last_fixed_id():
    return max(level.id for level in _fixed_levels())


@contextmanager
def _one_more_fixed_level():
    """A fixed level added after the last one, the way a new campaign level is."""
    levels = _fixed_levels()
    level = LevelSpec(id=_last_fixed_id() + 1, name="Next Campaign Level", start=(-7.0, 0.0),
                      target_center=(7.0, 0.0), target_radius=1.0, ship_id="ship01")
    levels.append(level)
    try:
        yield level
    finally:
        levels.remove(level)


@pytest.fixture
def next_fixed_level():
    with _one_more_fixed_level() as level:
        yield level


def _audio():
    return SimpleNamespace(play=lambda *a, **k: None, start_loop=lambda *a, **k: None,
                           stop_loop=lambda *a, **k: None)


def _manager():
    from vector_drift.scenes.base import SceneManager
    return SceneManager(_audio())


# --- ids and numbers --------------------------------------------------------------
def test_fixed_ids_start_at_one_and_have_no_gaps():
    ids = sorted(level.id for level in _fixed_levels())
    assert ids == list(range(1, len(ids) + 1))
    assert all(level_id < RANDOM_LEVEL_ID for level_id in ids)


def test_the_random_level_has_a_fixed_id_and_is_numbered_after_the_campaign():
    assert RANDOM_LEVEL_ID == 999 and is_dynamic_level(RANDOM_LEVEL_ID)
    assert level_number(RANDOM_LEVEL_ID) == _last_fixed_id() + 1 == 11
    # Level number N flies shipNN when that ship is made, else ship01.
    expected = "ship11" if "ship11" in SHIPS else "ship01"
    assert default_ship_id(RANDOM_LEVEL_ID) == expected
    assert [level_number(level.id) for level in all_levels()] == list(range(1, 12))


def test_a_fixed_level_is_numbered_by_its_id():
    for level in _fixed_levels():
        assert level_number(level.id) == level.id
        assert default_ship_id(level.id) == f"ship{level.id:02d}"


def test_adding_a_fixed_level_moves_the_random_number_not_its_id(next_fixed_level):
    new_id = next_fixed_level.id
    assert RANDOM_LEVEL_ID == 999 and is_dynamic_level(RANDOM_LEVEL_ID)
    assert not is_dynamic_level(new_id)
    assert get_level(new_id) is next_fixed_level
    assert level_number(new_id) == new_id
    assert level_number(RANDOM_LEVEL_ID) == new_id + 1


# --- the save data of the random level stays its own ----------------------------------
def _card_texts(monkeypatch, scene, level_id):
    """Every text drawn on the level-select card of ``level_id``."""
    from vector_drift.scenes import levels as levels_module

    texts = []
    monkeypatch.setattr(levels_module, "draw_text",
                        lambda surface, text, *a, **k: texts.append(str(text)))
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    while level_id not in [lid for lid, _ in scene.cards]:
        assert scene._next_page(), f"no card for level {level_id}"
    rect = dict(scene.cards)[level_id]
    scene._draw_card(surface, level_id, rect)
    return texts


@pytest.mark.usefixtures("pygame_display")
def test_a_new_fixed_level_does_not_show_the_random_levels_best_time(monkeypatch, next_fixed_level):
    from vector_drift.scenes.levels import LevelSelectScene

    manager = _manager()
    manager.session.records[RANDOM_LEVEL_ID] = RANDOM_BEST
    new_card = _card_texts(monkeypatch, LevelSelectScene(manager), next_fixed_level.id)
    assert "Not cleared yet" in new_card
    assert not any("Best" in text for text in new_card)
    assert str(next_fixed_level.id) in new_card

    random_card = _card_texts(monkeypatch, LevelSelectScene(manager), RANDOM_LEVEL_ID)
    assert f"Best {RANDOM_BEST:.2f} s" in random_card
    assert str(next_fixed_level.id + 1) in random_card      # shown after the new level
    assert str(RANDOM_LEVEL_ID) not in random_card


@pytest.mark.usefixtures("pygame_display")
def test_the_level_select_lists_every_number_once_in_order(next_fixed_level):
    from vector_drift.scenes.levels import LevelSelectScene

    scene = LevelSelectScene(_manager())
    shown = [scene.level_numbers[lid] for lid in scene.level_ids]
    assert shown == list(range(1, len(shown) + 1))
    assert len(shown) == config.PLANNED_LEVELS
    assert scene.level_ids[next_fixed_level.id - 1] == next_fixed_level.id
    assert scene.level_ids[next_fixed_level.id] == RANDOM_LEVEL_ID


def test_the_random_record_does_not_complete_the_campaign(next_fixed_level):
    manager = _manager()
    for level_id in ach.campaign_level_ids():
        if level_id != next_fixed_level.id:
            manager.session.records[level_id] = 5.0
    manager.session.records[RANDOM_LEVEL_ID] = RANDOM_BEST
    ach.check_state(manager)
    assert not ach.is_unlocked(manager.session, "home_sweet_home.4")     # tier IV: every level

    manager.session.records[next_fixed_level.id] = 6.0
    ach.check_state(manager)
    assert ach.is_unlocked(manager.session, "home_sweet_home.4")


@pytest.mark.usefixtures("pygame_display")
def test_a_new_fixed_level_pays_its_first_clear_reward(next_fixed_level):
    from vector_drift.scenes.game import GameScene

    manager = _manager()
    session = manager.session
    session.records[RANDOM_LEVEL_ID] = RANDOM_BEST
    session.clear_rewarded_maps.add((RANDOM_LEVEL_ID, 7))
    session.level_id = next_fixed_level.id
    scene = GameScene(manager)
    manager.switch(scene)
    before = int(session.money)

    scene._pay_clear_reward()
    assert scene._clear_reward == config.CLEAR_REWARD
    assert int(session.money) == before + config.CLEAR_REWARD
    assert next_fixed_level.id in session.clear_rewarded_levels


# --- other places a level's number is shown ---------------------------------------------
@pytest.mark.usefixtures("pygame_display")
def test_the_game_panel_shows_the_random_levels_number(monkeypatch):
    from vector_drift.scenes import game as game_module
    from vector_drift.scenes.game import GameScene

    manager = _manager()
    manager.session.level_id, manager.session.random_seed = RANDOM_LEVEL_ID, 7
    scene = GameScene(manager)
    manager.switch(scene)
    texts = []
    monkeypatch.setattr(game_module, "draw_text", lambda surface, text, *a, **k: texts.append(str(text)))
    scene.draw(pygame.Surface((config.WINDOW_W, config.WINDOW_H)))
    assert f"LV{level_number(RANDOM_LEVEL_ID)}" in texts
    assert f"LV{RANDOM_LEVEL_ID}" not in texts


@pytest.mark.usefixtures("pygame_display")
def test_the_replay_names_the_random_level_by_its_number(monkeypatch):
    from vector_drift.scenes import replay as replay_module
    from vector_drift.scenes.replay import ReplayScene

    manager = _manager()
    manager.session.replays = [{
        "level_id": RANDOM_LEVEL_ID, "seed": 7, "section_index": 0, "ship_id": "ship10",
        "fx_text": "0", "fy_text": "0", "outcome": "Outcome.TIMEOUT",
        "frames": [{"t": 0.0, "x": 0.0, "y": 0.0, "vx": 0.0, "vy": 0.0, "fx": 0.0, "fy": 0.0}]}]
    scene = ReplayScene(manager)
    manager.switch(scene)
    texts = []
    monkeypatch.setattr(replay_module, "draw_text", lambda surface, text, *a, **k: texts.append(str(text)))
    scene.draw(pygame.Surface((config.WINDOW_W, config.WINDOW_H)))
    number = str(level_number(RANDOM_LEVEL_ID))
    assert any(text == number or text.startswith(f"{number} · ") for text in texts)
    assert not any(text.startswith(str(RANDOM_LEVEL_ID)) for text in texts)


# --- replays ------------------------------------------------------------------------------
@pytest.mark.usefixtures("pygame_display")
def test_a_random_level_replay_rebuilds_its_map_after_a_new_fixed_level():
    """Saved as id 999 + seed, it replays the same map once another fixed level exists."""
    from vector_drift.account.integration import session_to_profile
    from vector_drift.account.models import PlayerProfile
    from vector_drift.scenes.game import FLIGHT, GameScene
    from vector_drift.scenes.replay import ReplayScene

    seed = 4321
    manager = _manager()
    session = manager.session
    session.level_id, session.random_seed = RANDOM_LEVEL_ID, seed
    session.fx_text, session.fy_text = "50", "0"
    game = GameScene(manager)
    manager.switch(game)
    flown = game.level
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    game._try_launch()
    while game.state == FLIGHT:
        game.update(0.05)
        game.draw(surface)

    record = session.replays[-1]
    assert (record["level_id"], record["seed"], record["section_index"]) == (RANDOM_LEVEL_ID, seed, 0)
    # Saved and loaded the way a profile is (local file or cloud row).
    saved = PlayerProfile.from_row(session_to_profile(session, "player").to_row(), "player").replays

    with _one_more_fixed_level() as new_level:
        assert get_level(new_level.id) is new_level
        later = _manager()
        later.session.replays = saved
        replay = ReplayScene(later)
        later.switch(replay)

        assert tuple(replay._start) == tuple(flown.start)
        assert tuple(replay._target_center) == tuple(flown.target_center)
        assert replay._target_radius == flown.target_radius
        assert tuple(replay._obstacles) == tuple(flown.obstacles)
        assert [(tuple(p.center), p.kind) for p in replay._pickups] == [
            (tuple(p.center), p.kind) for p in flown.pickups]
        replay.draw(surface)
