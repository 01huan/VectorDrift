"""Tests for the search / sort bar of the Public Levels page."""

from types import SimpleNamespace

import pygame
import pytest

from vector_drift import config
from vector_drift.account import community as community_module
from vector_drift.community_browse import (
    SORT_CLEARERS,
    SORT_CLEARS,
    SORT_NEWEST,
    SORT_PLAYS,
)
from vector_drift.scenes.base import SceneManager
from vector_drift.scenes.community_levels import CommunityLevelsScene

pytestmark = pytest.mark.usefixtures("pygame_display")


ROWS = [
    {"id": "r1", "user_id": "u2", "uploader_name": "Alice", "level_name": "Meteor Maze",
     "created_at": "2024-05-01T10:00:00Z",
     "level_data": {"id": 7001, "name": "Meteor Maze", "start": [-7.0, 0.0],
                    "target_center": [7.0, 0.0], "target_radius": 1.0, "time_limit": 10.0,
                    "obstacles": [{"center": [0.0, 0.0], "radius": 0.5}],
                    "pickups": [{"center": [1.0, 0.0], "radius": 0.4, "kind": "money"}]},
     "play_count": 10, "clear_count": 3, "clear_players": ["a", "b"]},
    {"id": "r2", "user_id": "u3", "uploader_name": "Bob", "level_name": "Orbit Run",
     "created_at": "2024-06-01T10:00:00Z",
     "level_data": {"id": 7002, "name": "Orbit Run", "start": [-7.0, 0.0],
                    "target_center": [7.0, 0.0], "target_radius": 1.0, "time_limit": 20.0,
                    "obstacles": [], "pickups": []},
     "play_count": 2, "clear_count": 0, "clear_players": []},
    {"id": "r3", "user_id": "u4", "uploader_name": "Carol", "level_name": "Meteor",
     "created_at": "2024-04-01T10:00:00Z",
     "level_data": {"id": 7003, "name": "Meteor", "start": [-7.0, 0.0],
                    "target_center": [7.0, 0.0], "target_radius": 1.0, "time_limit": 5.0,
                    "obstacles": [], "pickups": []},
     "play_count": 50, "clear_count": 20, "clear_players": ["a", "b", "c"]},
]


def _manager(account=None):
    audio = SimpleNamespace(
        play=lambda *a, **k: None,
        start_loop=lambda *a, **k: None,
        stop_loop=lambda *a, **k: None,
        set_music=lambda *a, **k: None,
        toggle_mute=lambda *a, **k: None,
        update=lambda *a, **k: None,
    )
    return SceneManager(audio, account_manager=account)


def _scene(monkeypatch, rows=None):
    def fetch(on_success=None, on_error=None):
        if on_success is not None:
            on_success(list(rows if rows is not None else ROWS))
    monkeypatch.setattr(community_module, "fetch_community_levels", fetch)
    return CommunityLevelsScene(_manager())


def _type(scene, widget, text):
    """Type ``text`` into ``widget`` (the field has to be focused first)."""
    scene.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1,
                                          pos=widget.rect.center))
    for char in text:
        scene.handle_event(pygame.event.Event(pygame.TEXTINPUT, text=char))


def _click(scene, button):
    button.handle_event = lambda event: "click"
    scene.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(0, 0)))


def _names(scene):
    scene._rebuild()
    return [info.name for _row, info in scene._filtered]


# --- searching -------------------------------------------------------------

def test_the_name_search_filters_the_cards(monkeypatch):
    scene = _scene(monkeypatch)
    _type(scene, scene.name_input, "meteor")
    assert set(_names(scene)) == {"Meteor Maze", "Meteor"}


def test_the_name_search_puts_the_closest_match_first(monkeypatch):
    scene = _scene(monkeypatch)
    _type(scene, scene.name_input, "meteor")
    assert _names(scene)[0] == "Meteor"


def test_the_uploader_search_filters_the_cards(monkeypatch):
    scene = _scene(monkeypatch)
    _type(scene, scene.uploader_input, "bob")
    assert _names(scene) == ["Orbit Run"]


def test_a_search_that_matches_nothing_shows_no_card(monkeypatch):
    scene = _scene(monkeypatch)
    _type(scene, scene.name_input, "zzzz-nothing")
    assert _names(scene) == []
    assert scene.cards == []


def test_the_minimum_filters_use_the_statistics(monkeypatch):
    scene = _scene(monkeypatch)
    _type(scene, scene.min_plays_input, "10")
    assert set(_names(scene)) == {"Meteor Maze", "Meteor"}
    scene = _scene(monkeypatch)
    _type(scene, scene.min_clearers_input, "3")
    assert _names(scene) == ["Meteor"]


def test_the_minimum_fields_only_take_digits(monkeypatch):
    scene = _scene(monkeypatch)
    _type(scene, scene.min_plays_input, "1a2")
    assert scene.min_plays_input.text == "12"


def test_clearing_the_search_shows_every_level_again(monkeypatch):
    scene = _scene(monkeypatch)
    _type(scene, scene.name_input, "meteor")
    assert len(_names(scene)) == 2
    scene.name_input.clear()
    assert len(_names(scene)) == 3


# --- sorting ---------------------------------------------------------------

def test_the_sort_dropdown_opens_and_picks_an_order(monkeypatch):
    scene = _scene(monkeypatch)
    assert scene.sort_key == SORT_NEWEST
    # clicking the button face opens the list
    ev = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=scene.sort_button.rect.center)
    scene.handle_event(ev)
    assert scene.sort_menu.open
    # picking "Plays" applies that order
    target = None
    for rect, (value, _label) in zip(scene.sort_menu.item_rects(), scene.sort_menu.items):
        if value == SORT_PLAYS:
            target = rect
            break
    assert target is not None
    ev = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=target.center)
    scene.handle_event(ev)
    assert scene.sort_key == SORT_PLAYS
    assert scene.descending is True
    assert not scene.sort_menu.open


def test_the_sort_dropdown_offers_every_order(monkeypatch):
    scene = _scene(monkeypatch)
    keys = {key for key, _label in scene.sort_menu.items}
    assert SORT_PLAYS in keys
    assert SORT_CLEARS in keys
    assert SORT_CLEARERS in keys


def test_the_direction_button_toggles(monkeypatch):
    scene = _scene(monkeypatch)
    before = scene.descending
    _click(scene, scene.sort_dir_button)
    assert scene.descending is not before


def test_sorting_by_plays_puts_the_most_played_first(monkeypatch):
    scene = _scene(monkeypatch)
    scene.sort_key = SORT_PLAYS
    scene.descending = True
    assert _names(scene)[0] == "Meteor"


def test_the_pickup_button_cycles_the_pickup_kind(monkeypatch):
    scene = _scene(monkeypatch)
    before = scene.pickup_kind
    _click(scene, scene.pickup_button)
    assert scene.pickup_kind != before


def test_the_reset_button_clears_everything(monkeypatch):
    scene = _scene(monkeypatch)
    _type(scene, scene.name_input, "meteor")
    _type(scene, scene.min_plays_input, "5")
    scene.sort_key = SORT_PLAYS
    _click(scene, scene.reset_button)
    assert scene.name_input.text == ""
    assert scene.min_plays_input.text == ""
    assert scene.sort_key == SORT_NEWEST
    assert len(_names(scene)) == 3


# --- drawing ---------------------------------------------------------------

def test_the_page_draws_with_the_search_bar(monkeypatch):
    scene = _scene(monkeypatch)
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    scene.draw(surface)


def test_the_page_draws_with_a_result(monkeypatch):
    scene = _scene(monkeypatch)
    _type(scene, scene.name_input, "meteor")
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    scene.draw(surface)
    assert scene.cards


def test_the_page_draws_without_any_level(monkeypatch):
    scene = _scene(monkeypatch, rows=[])
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    scene.draw(surface)
    assert scene.cards == []


def test_a_broken_row_does_not_break_the_list(monkeypatch):
    rows = list(ROWS) + [{"id": "bad", "level_data": "not a dict"}, "not a row"]
    scene = _scene(monkeypatch, rows=rows)
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    scene.draw(surface)
    # The broken row is still listed (with empty numbers), the row that is
    # not even a dict is skipped.
    assert len(scene._filtered) == 4
    broken = [info for _row, info in scene._filtered if info.row_id == "bad"]
    assert broken and broken[0].obstacle_count == 0


def test_the_cards_are_only_rebuilt_when_something_changed(monkeypatch):
    scene = _scene(monkeypatch)
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    scene.draw(surface)
    cards = list(scene.cards)
    scene.draw(surface)
    assert scene.cards is cards or scene.cards == cards   # same list, not rebuilt


def test_opening_a_level_from_a_searched_list_still_works(monkeypatch):
    import vector_drift.scenes.game as game_module

    class FakeGame:
        music = None

        def __init__(self, m):
            self.m = m

    monkeypatch.setattr(game_module, "GameScene", FakeGame)
    scene = _scene(monkeypatch)
    _type(scene, scene.name_input, "meteor")
    scene._rebuild()
    rect = scene.cards[0][1]
    event = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=rect.center)
    scene.handle_event(event)
    assert isinstance(scene.manager.scene, FakeGame)


# --- paging ----------------------------------------------------------------

def _many_rows(count=30):
    rows = []
    for index in range(count):
        row = dict(ROWS[0])
        row["id"] = f"many-{index}"
        row["level_name"] = f"Level {index}"
        row["level_data"] = dict(ROWS[0]["level_data"])
        row["level_data"]["name"] = f"Level {index}"
        rows.append(row)
    return rows


def test_only_the_cards_that_fit_are_drawn(monkeypatch):
    scene = _scene(monkeypatch, rows=_many_rows(30))
    scene._rebuild()
    assert len(scene.cards) == 12
    assert scene.page_count() == 3


def test_the_next_button_turns_the_page(monkeypatch):
    scene = _scene(monkeypatch, rows=_many_rows(30))
    scene._rebuild()
    assert scene.page == 0
    assert not scene.prev_page_button.enabled
    assert scene.next_page_button.enabled
    _click(scene, scene.next_page_button)
    scene._rebuild()
    assert scene.page == 1
    assert scene.prev_page_button.enabled
    assert scene.cards[0][0]["id"] == "many-12"


def test_the_cards_show_their_own_level_on_every_page(monkeypatch):
    scene = _scene(monkeypatch, rows=_many_rows(30))
    for _ in range(2):
        _click(scene, scene.next_page_button)
        scene._rebuild()
        for (lvl, _rect), (_row, info) in zip(scene.cards, scene._page_entries):
            assert lvl["id"] == info.row_id
            assert lvl["level_name"] == info.name


def test_the_page_stops_at_the_last_page(monkeypatch):
    scene = _scene(monkeypatch, rows=_many_rows(30))
    scene._rebuild()
    for _ in range(5):
        _click(scene, scene.next_page_button)
    scene._rebuild()
    assert scene.page == 2
    assert not scene.next_page_button.enabled


def test_the_mouse_wheel_turns_the_page(monkeypatch):
    scene = _scene(monkeypatch, rows=_many_rows(30))
    scene._rebuild()
    scene.handle_event(pygame.event.Event(pygame.MOUSEWHEEL, x=0, y=-1))
    scene._rebuild()
    assert scene.page == 1
    # A second gesture (not the same flick) turns the page back.
    scene._last_wheel = None
    scene.handle_event(pygame.event.Event(pygame.MOUSEWHEEL, x=0, y=1))
    scene._rebuild()
    assert scene.page == 0


def test_a_search_that_fits_on_one_page_has_no_paging(monkeypatch):
    scene = _scene(monkeypatch, rows=_many_rows(30))
    _type(scene, scene.name_input, "29")
    scene._rebuild()
    assert len(scene._filtered) == 1
    assert scene.page_count() == 1
    assert not scene.next_page_button.enabled
