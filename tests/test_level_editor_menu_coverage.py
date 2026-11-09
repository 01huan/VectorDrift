import pygame
import pytest

import vector_drift.data as data
import vector_drift.scenes.level_editor as level_editor_module
import vector_drift.scenes.community_levels as community_levels_module
import vector_drift.scenes.game as game_module

from vector_drift import config
from vector_drift.scenes.level_editor_menu import LevelEditorMenuScene
from vector_drift.scenes.levels import LevelSelectScene

from tests.test_level_editor import _Manager, _event


pytestmark = pytest.mark.usefixtures("pygame_display")


class _FakeScene:
    def __init__(self, *args, **kwargs):
        pass


def _level(level_id=91001):
    return data.LevelSpec(
        id=level_id,
        name="Menu Custom",
        start=(-7.0, 0.0),
        target_center=(7.0, 0.0),
        target_radius=1.0,
        ship_id="ship01",
        obstacles=(data.ObstacleSpec(center=(0.0, 0.0), radius=0.5),),
        pickups=(data.PickupSpec(center=(2.0, 0.0), radius=0.3, kind="life"),),
        holes=(data.HoleSpec(black_center=(4.0, 0.0), white_center=(5.5, 0.0), radius=0.6),),
    )


def _make_scene(level_id=91001):
    mgr = _Manager()
    level = _level(level_id)
    mgr.session.custom_levels = [level]
    mgr.session.custom_level_ids = {level.id}
    scene = LevelEditorMenuScene(mgr)
    scene.update(0.0)
    return scene, mgr, level

def test_menu_init_empty():
    mgr = _Manager()
    scene = LevelEditorMenuScene(mgr)
    scene.update(0.0)
    assert scene.cards == []
    assert scene.delete_rects == []
    scene.update(0.1)
    assert scene.message == ""
    assert scene.message_timer <= 0.0


def test_rebuild_with_level():
    scene, mgr, level = _make_scene()
    assert len(scene.cards) == 1
    assert len(scene.delete_rects) == 1
    assert scene.cards[0][0] is level


def test_update_counts_down_message():
    scene, mgr, level = _make_scene()
    scene.message = "hello"
    scene.message_timer = 0.5
    scene.update(0.2)
    assert scene.message == "hello"
    assert scene.message_timer == pytest.approx(0.3)
    scene.update(0.4)
    assert scene.message_timer <= 0.0
    assert scene.message == ""


def test_back_button_switches_to_level_select(monkeypatch):
    scene, mgr, level = _make_scene()
    scene.back_button.handle_event = lambda ev: "click"
    scene.handle_event(_event(pygame.MOUSEBUTTONDOWN, button=1, pos=(0, 0)))
    assert isinstance(mgr.scene, LevelSelectScene)


def test_new_button_switches_to_editor(monkeypatch):
    monkeypatch.setattr(level_editor_module, "LevelEditorScene", _FakeScene)
    scene, mgr, level = _make_scene()
    scene.new_button.handle_event = lambda ev: "click"
    scene.handle_event(_event(pygame.MOUSEBUTTONDOWN, button=1, pos=(0, 0)))
    assert mgr.scene is not None


def test_community_button_switches(monkeypatch):
    monkeypatch.setattr(community_levels_module, "CommunityLevelsScene", _FakeScene)
    scene, mgr, level = _make_scene()
    scene.community_button.handle_event = lambda ev: "click"
    scene.handle_event(_event(pygame.MOUSEBUTTONDOWN, button=1, pos=(0, 0)))
    assert mgr.scene is not None


def test_delete_local_level_via_event(monkeypatch):
    monkeypatch.setattr(data, "LEVELS", list(data.LEVELS))
    monkeypatch.setattr(data, "CUSTOM_LEVELS", dict(data.CUSTOM_LEVELS))

    level = _level(92001)
    data.register_custom_level(level)

    mgr = _Manager()
    mgr.session.custom_levels = [level]
    mgr.session.custom_level_ids = {level.id}
    scene = LevelEditorMenuScene(mgr)
    scene.update(0.0)
    assert len(scene.delete_rects) == 1

    for btn in (scene.back_button, scene.new_button, scene.community_button):
        btn.handle_event = lambda ev: None

    pos = scene.delete_rects[0].center
    scene.handle_event(_event(pygame.MOUSEBUTTONDOWN, button=1, pos=pos))

    assert scene.message == "Deleted."
    assert scene.message_timer == 1.5
    assert level.id not in mgr.session.custom_level_ids
    assert mgr.session.custom_levels == []


def test_delete_local_level_direct(monkeypatch):
    monkeypatch.setattr(data, "LEVELS", list(data.LEVELS))
    monkeypatch.setattr(data, "CUSTOM_LEVELS", dict(data.CUSTOM_LEVELS))

    level = _level(92002)
    data.register_custom_level(level)

    mgr = _Manager()
    mgr.session.custom_levels = [level]
    mgr.session.custom_level_ids = {level.id}
    scene = LevelEditorMenuScene(mgr)
    scene.update(0.0)

    scene._delete_local_level(level)
    assert level.id not in data.CUSTOM_LEVELS
    assert all(lv.id != level.id for lv in data.LEVELS)
    assert scene.message == "Deleted."

def test_open_card_switches_to_game(monkeypatch):
    monkeypatch.setattr(game_module, "GameScene", _FakeScene)
    scene, mgr, level = _make_scene()
    for btn in (scene.back_button, scene.new_button, scene.community_button):
        btn.handle_event = lambda ev: None

    rect = scene.cards[0][1]
    scene.handle_event(_event(pygame.MOUSEBUTTONDOWN, button=1, pos=rect.center))
    assert mgr.scene is not None


def test_right_click_edits_level(monkeypatch):
    monkeypatch.setattr(level_editor_module, "LevelEditorScene", _FakeScene)
    scene, mgr, level = _make_scene()
    for btn in (scene.back_button, scene.new_button, scene.community_button):
        btn.handle_event = lambda ev: None

    rect = scene.cards[0][1]
    scene.handle_event(_event(pygame.MOUSEBUTTONDOWN, button=3, pos=rect.center))
    assert mgr.scene is not None


def test_draw_empty_with_message(monkeypatch):
    monkeypatch.setattr("vector_drift.scenes.level_editor_menu.load_image", lambda *a, **k: None)
    mgr = _Manager()
    scene = LevelEditorMenuScene(mgr)
    scene.update(0.0)
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    scene.message = "note"
    scene.message_timer = 0.5
    scene.draw(surface)


def test_draw_card_no_image(monkeypatch):
    monkeypatch.setattr("vector_drift.scenes.level_editor_menu.load_image", lambda *a, **k: None)
    scene, mgr, level = _make_scene()
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    pygame.mouse.get_pos = lambda: (-1, -1)
    scene.draw(surface)


def test_draw_card_with_image(monkeypatch):
    def fake_image(*a, **k):
        return pygame.Surface((8, 8))
    monkeypatch.setattr("vector_drift.scenes.level_editor_menu.load_image", fake_image)
    scene, mgr, level = _make_scene()
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    del_rect = scene.delete_rects[0]
    pygame.mouse.get_pos = lambda: del_rect.center
    scene.draw(surface)


def test_draw_preview_early_return(monkeypatch):
    monkeypatch.setattr("vector_drift.scenes.level_editor_menu.data.custom_level_to_snapshot", lambda lv: {})
    scene, mgr, level = _make_scene()
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    monkeypatch.setattr("vector_drift.scenes.level_editor_menu.load_image", lambda *a, **k: None)
    card = scene.cards[0]
    scene._draw_level_preview(surface, card[0], card[2])
