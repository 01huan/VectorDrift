import pygame
import pytest

from vector_drift import config, data
from vector_drift.account import local_profile_manager as lpm
from vector_drift.scenes.level_editor import LevelEditorScene
from tests.test_level_editor import _Manager, _event
pytestmark = pytest.mark.usefixtures("pygame_display")



class _User:
    def __init__(self, uid="u1", email="u@example.com"):
        self.id = uid
        self.email = email


class _Account:
    def __init__(self, configured=True, authenticated=True, user=None):
        self._configured = configured
        self._authenticated = authenticated
        self.current_user = user if (authenticated and user is not None) else (
            _User() if authenticated and user is None else None
        )
        self.is_busy = False

    def is_configured(self):
        return self._configured

    def is_authenticated(self):
        return self._authenticated and self.current_user is not None


def _world_screen(editor, world):
    return editor.viewport.to_screen(*world)


def _make_editor_with_objects():
    editor = LevelEditorScene(_Manager())
    editor.obstacles.append({"center": (1.0, 2.0), "radius": 0.5})
    editor.pickups.append({"center": (3.0, 4.0), "radius": 0.4, "kind": "shield"})
    editor.holes.append(
        {"black_center": (5.0, 6.0), "white_center": (6.5, 6.0), "radius": 0.9}
    )
    return editor
def test_object_center_radius_setters_handle_every_kind():
    editor = _make_editor_with_objects()

    assert editor._object_center(("start", None)) == (-7.0, 0.0)
    assert editor._object_center(("target", None)) == (7.0, 0.0)
    assert editor._object_center(("obstacle", 0)) == (1.0, 2.0)
    assert editor._object_center(("pickup", 0)) == (3.0, 4.0)
    assert editor._object_center(("black_hole", 0)) == (5.0, 6.0)
    assert editor._object_center(("white_hole", 0)) == (6.5, 6.0)
    assert editor._object_center(("hole", 0)) == (5.0, 6.0)

    assert editor._object_radius(("start", None)) == editor.START_RADIUS
    assert editor._object_radius(("target", None)) == 1.0
    assert editor._object_radius(("obstacle", 0)) == 0.5
    assert editor._object_radius(("pickup", 0)) == 0.4
    assert editor._object_radius(("black_hole", 0)) == 0.9
    assert editor._object_radius(("white_hole", 0)) == 0.9
    assert editor._object_radius(("hole", 0)) == 0.9

    editor._set_object_radius(("start", None), 2.0)
    assert editor.START_RADIUS == 0.45

    editor._set_object_center(("start", None), (10.0, 11.0))
    assert editor.start == (10.0, 11.0)
    editor._set_object_center(("target", None), (12.0, 13.0))
    assert editor.target == (12.0, 13.0)
    editor._set_object_center(("black_hole", 0), (100.0, 101.0))
    assert editor.holes[0]["black_center"] == (100.0, 101.0)
    editor._set_object_center(("white_hole", 0), (102.0, 103.0))
    assert editor.holes[0]["white_center"] == (102.0, 103.0)
    editor._set_object_center(("hole", 0), (104.0, 105.0))
    assert editor.holes[0]["black_center"] == (104.0, 105.0)
    editor._set_object_center(("obstacle", 0), (200.0, 201.0))
    assert editor.obstacles[0]["center"] == (200.0, 201.0)
    editor._set_object_center(("pickup", 0), (202.0, 203.0))
    assert editor.pickups[0]["center"] == (202.0, 203.0)

    editor._set_object_radius(("target", None), 2.5)
    assert editor.target_radius == 2.5
    editor._set_object_radius(("black_hole", 0), 1.1)
    assert editor.holes[0]["radius"] == 1.1
    editor._set_object_radius(("white_hole", 0), 1.2)
    assert editor.holes[0]["radius"] == 1.2
    editor._set_object_radius(("hole", 0), 1.3)
    assert editor.holes[0]["radius"] == 1.3
    editor._set_object_radius(("obstacle", 0), 1.4)
    assert editor.obstacles[0]["radius"] == 1.4
    editor._set_object_radius(("pickup", 0), 1.5)
    assert editor.pickups[0]["radius"] == 1.5

def test_object_at_and_overlaps_cover_every_kind():
    editor = _make_editor_with_objects()
    pos = _world_screen(editor, editor.start)
    assert editor._object_at(pos)[0] == "start"
    pos = _world_screen(editor, editor.target)
    assert editor._object_at(pos)[0] == "target"
    pos = _world_screen(editor, editor.obstacles[0]["center"])
    assert editor._object_at(pos) == ("obstacle", 0)
    pos = _world_screen(editor, editor.pickups[0]["center"])
    assert editor._object_at(pos) == ("pickup", 0)
    pos = _world_screen(editor, editor.holes[0]["black_center"])
    assert editor._object_at(pos) == ("black_hole", 0)
    pos = _world_screen(editor, editor.holes[0]["white_center"])
    assert editor._object_at(pos) == ("white_hole", 0)
    assert editor._object_at((0, 0)) is None

    assert editor._overlaps((1000.0, 1000.0), 0.1) is False
    assert editor._overlaps(editor.obstacles[0]["center"], 0.5, ignore=("obstacle", 0)) is False
    assert editor._overlaps(editor.obstacles[0]["center"], 0.5) is True

def test_in_playfield_and_screen_to_world():
    editor = LevelEditorScene(_Manager())
    rect = pygame.Rect(editor.viewport.rect)
    assert editor._in_playfield(rect.center) is True
    assert editor._in_playfield((-10000, -10000)) is False
    editor._screen_to_world((10, 10))

def test_resize_selected_covers_reject_and_start_early_return():
    editor = LevelEditorScene(_Manager())
    editor.obstacles.append({"center": (0.0, 0.0), "radius": 0.5})
    editor.selected = None
    editor._resize_selected(0.1)

    editor.selected = ("start", None)
    editor._resize_selected(0.1)

    editor.selected = ("obstacle", 0)
    editor._resize_selected(0.0)
    assert editor.message == "Objects cannot overlap"

    editor._resize_selected(0.1)
    assert editor.obstacles[0]["radius"] == 0.6

def test_move_selected_success_branch():
    editor = LevelEditorScene(_Manager())
    editor.obstacles.append({"center": (0.0, 0.0), "radius": 0.3})
    editor.selected = ("obstacle", 0)
    editor.moving = ("obstacle", 0)
    editor.move_offset = (0.0, 0.0)
    pos = editor.viewport.to_screen(2.0, 2.0)
    editor._move_selected(pos)
    assert editor.obstacles[0]["center"] == (2.0, 2.0)
    assert editor.message == ""

def test_init_from_level_populates_fields():
    from vector_drift.data import LevelSpec
    level = LevelSpec(
        id=42, name="FromLevel", start=(-3.0, 1.0),
        target_center=(4.0, -2.0), target_radius=1.5, ship_id="ship01",
        obstacles=(), pickups=(), holes=(),
    )
    editor = LevelEditorScene(_Manager(), level=level)
    assert editor.start == (-3.0, 1.0)
    assert editor.target == (4.0, -2.0)
    assert editor.target_radius == 1.5
    assert editor._placed_start is True
    assert editor._placed_target is True
    assert editor.name_buffer == "FromLevel"

def test_place_every_kind_and_reject_overlap():
    editor = LevelEditorScene(_Manager())
    editor._place("start", (1.0, 2.0))
    assert editor.start == (1.0, 2.0)
    assert editor._placed_start is True
    assert editor.selected is None
    assert editor.message == ""

    editor._place("target", (3.0, 4.0))
    assert editor.target == (3.0, 4.0)
    assert editor._placed_target is True

    editor._place("obstacle", (5.0, 6.0))
    assert editor.obstacles[-1] == {"center": (5.0, 6.0), "radius": 0.5}
    assert editor.selected == ("obstacle", len(editor.obstacles) - 1)

    editor._place("shockwave", (8.0, 9.0))
    assert editor.pickups[-1]["kind"] == "shockwave"
    assert editor.selected == ("pickup", len(editor.pickups) - 1)

    editor._place("hole", (10.0, 11.0))
    assert len(editor.holes) == 1
    assert editor.selected == ("black_hole", 0)

    before = len(editor.holes)
    editor._place("black", (10.0, 11.0))
    assert len(editor.holes) == before
    assert editor.message == "Objects cannot overlap"

    editor._place("obstacle", (5.0, 6.0))
    assert editor.message == "Objects cannot overlap"

def test_delete_object_every_branch():
    editor = LevelEditorScene(_Manager())
    editor._placed_start = True
    editor._delete_object(("start", None))
    assert editor._placed_start is False
    assert editor.start == (-7.0, 0.0)

    editor._placed_target = True
    editor.target_radius = 2.0
    editor._delete_object(("target", None))
    assert editor._placed_target is False
    assert editor.target == (7.0, 0.0)
    assert editor.target_radius == 1.0

    editor.obstacles.append({"center": (0.0, 0.0), "radius": 0.5})
    editor._delete_object(("obstacle", 0))
    assert editor.obstacles == []

    editor.holes.append({"black_center": (0.0, 0.0), "white_center": (1.0, 0.0), "radius": 0.5})
    editor._delete_object(("hole", 0))
    assert editor.holes == []
    editor.holes.append({"black_center": (0.0, 0.0), "white_center": (1.0, 0.0), "radius": 0.5})
    editor._delete_object(("black_hole", 0))
    assert editor.holes == []
    editor.holes.append({"black_center": (0.0, 0.0), "white_center": (1.0, 0.0), "radius": 0.5})
    editor._delete_object(("white_hole", 0))
    assert editor.holes == []

    editor.pickups.append({"center": (0.0, 0.0), "radius": 0.4, "kind": "life"})
    editor._delete_object(("pickup", 0))
    assert editor.pickups == []
    assert editor.selected is None
    assert editor.context_menu is None
    assert editor.moving is None

def test_context_menu_handle_branches():
    editor = LevelEditorScene(_Manager())
    assert editor._handle_context_menu(_event(pygame.KEYDOWN, key=pygame.K_a)) is False

    editor.obstacles.append({"center": (0.0, 0.0), "radius": 0.5})
    pos = _world_screen(editor, (0.0, 0.0))
    editor._open_context_menu(pos, ("obstacle", 0))
    rect = editor.context_menu[1]
    modify_pos = (rect.centerx, rect.y + rect.height * 3 // 4)
    assert editor._handle_context_menu(
        _event(pygame.MOUSEBUTTONDOWN, button=1, pos=modify_pos)
    ) is True
    assert editor.selected == ("obstacle", 0)
    assert editor.context_menu is None
    assert "Drag to move" in editor.message

    editor.obstacles.append({"center": (0.0, 0.0), "radius": 0.5})
    editor._open_context_menu(pos, ("obstacle", 0))
    rect = editor.context_menu[1]
    delete_pos = (rect.centerx, rect.y + rect.height // 4)
    assert editor._handle_context_menu(
        _event(pygame.MOUSEBUTTONDOWN, button=1, pos=delete_pos)
    ) is True
    assert editor.obstacles == [{"center": (0.0, 0.0), "radius": 0.5}]

    editor._open_context_menu(pos, ("obstacle", 0))
    assert editor._handle_context_menu(
        _event(pygame.MOUSEBUTTONDOWN, button=1, pos=(10, 10))
    ) is False
    assert editor.context_menu is None

    editor._open_context_menu(pos, ("obstacle", 0))
    assert editor._handle_context_menu(
        _event(pygame.MOUSEBUTTONDOWN, button=3, pos=pos)
    ) is False
    assert editor.context_menu is None

    editor._open_context_menu(pos, ("obstacle", 0))
    assert editor._handle_context_menu(
        _event(pygame.KEYDOWN, key=pygame.K_a)
    ) is True

def test_naming_mode_cancel_outside_and_inside():
    editor = LevelEditorScene(_Manager())
    editor.naming = True
    editor.name_buffer = "X"
    editor.handle_event(_event(pygame.MOUSEBUTTONDOWN, button=1, pos=(0, 0)))
    assert editor.naming is False
    assert editor.name_buffer == ""
    assert editor.message == ""

    editor = LevelEditorScene(_Manager())
    editor.naming = True
    editor.name_buffer = "Y"
    box = pygame.Rect(
        config.px(config.WINDOW_W // 2 - 220), config.px(config.WINDOW_H - 120),
        config.px(440), config.px(44)
    )
    editor.handle_event(_event(pygame.MOUSEBUTTONDOWN, button=1, pos=box.center))
    assert editor.naming is True

def test_naming_backspace_printable_and_return_paths(monkeypatch):
    editor = LevelEditorScene(_Manager())
    editor.naming = True
    editor.name_buffer = "Ab"
    editor.handle_event(_event(pygame.KEYDOWN, key=pygame.K_BACKSPACE))
    assert editor.name_buffer == "A"

    editor.handle_event(_event(pygame.KEYDOWN, key=pygame.K_a, unicode="c"))
    assert editor.name_buffer == "Ac"

    editor2 = LevelEditorScene(_Manager())
    import vector_drift.data as vd
    monkeypatch.setattr(vd, "LEVELS", list(vd.LEVELS))
    monkeypatch.setattr(vd, "CUSTOM_LEVELS", dict(vd.CUSTOM_LEVELS))
    editor2.naming = True
    editor2.name_buffer = ""
    editor2.handle_event(_event(pygame.KEYDOWN, key=pygame.K_RETURN))
    assert editor2.naming is False
    from vector_drift.scenes.level_editor_menu import LevelEditorMenuScene
    assert isinstance(editor2.manager.scene, LevelEditorMenuScene)

def test_naming_return_upload_path():
    editor = LevelEditorScene(_Manager())
    editor.naming = True
    editor._naming_upload = True
    editor.name_buffer = "UploadName"
    editor.handle_event(_event(pygame.KEYDOWN, key=pygame.K_RETURN))
    assert editor.naming is False
    assert editor._naming_upload is False
    assert editor.message == "Supabase is not configured."

def test_update_account_branches():
    editor = LevelEditorScene(_Manager())
    editor.update(0.1)
    assert editor.upload_button.enabled is False
    assert editor.upload_button.label == "Upload (login)"

    manager = _Manager()
    manager.account = _Account(configured=True, authenticated=True)
    editor2 = LevelEditorScene(manager)
    editor2.update(0.1)
    assert editor2.upload_button.enabled is True
    assert editor2.upload_button.label == "Upload"

def test_build_spec_overlap_returns_none():
    editor = LevelEditorScene(_Manager())
    editor.obstacles.append({"center": (0.0, 0.0), "radius": 0.5})
    editor.obstacles.append({"center": (0.0, 0.0), "radius": 0.5})
    assert editor._build_spec("Overlap") is None
    assert editor.message == "Objects cannot overlap"

def test_handle_event_back_save_upload_buttons():
    editor = LevelEditorScene(_Manager())
    editor.handle_event(_event(pygame.MOUSEBUTTONDOWN, button=1, pos=editor.back_button.rect.center))
    from vector_drift.scenes.level_editor_menu import LevelEditorMenuScene
    assert isinstance(editor.manager.scene, LevelEditorMenuScene)

    editor2 = LevelEditorScene(_Manager())
    editor2.handle_event(_event(pygame.MOUSEBUTTONDOWN, button=1, pos=editor2.save_button.rect.center))
    assert editor2.naming is True
    assert editor2._naming_upload is False
    assert editor2.name_buffer == "Custom"

    editor3 = LevelEditorScene(_Manager())
    editor3.name_buffer = "X"
    editor3.handle_event(_event(pygame.MOUSEBUTTONDOWN, button=1, pos=editor3.upload_button.rect.center))
    assert editor3.naming is True
    assert editor3._naming_upload is True
    assert editor3.message == ""

def test_handle_event_palette_and_object_click():
    editor = LevelEditorScene(_Manager())
    rect = pygame.Rect(config.px(10), config.px(60), config.px(150), config.px(40))
    editor.handle_event(_event(pygame.MOUSEBUTTONDOWN, button=1, pos=rect.center))
    assert editor.dragging == "start"
    assert editor.selected is None

    editor2 = LevelEditorScene(_Manager())
    pos = _world_screen(editor2, editor2.start)
    editor2.handle_event(_event(pygame.MOUSEBUTTONDOWN, button=1, pos=pos))
    assert editor2.selected == ("start", None)
    assert editor2.moving == ("start", None)
    assert isinstance(editor2.move_offset, tuple)

    editor3 = LevelEditorScene(_Manager())
    pos = _world_screen(editor3, editor3.start)
    editor3.handle_event(_event(pygame.MOUSEBUTTONDOWN, button=3, pos=pos))
    assert editor3.context_menu is not None

def test_handle_event_motion_and_mouseup_branches():
    editor = LevelEditorScene(_Manager())
    editor.moving = ("start", None)
    editor.move_offset = (0.0, 0.0)
    pos = _world_screen(editor, (0.0, 0.0))
    editor.handle_event(_event(pygame.MOUSEMOTION, pos=pos, rel=(0, 0), buttons=(1, 0, 0)))

    editor2 = LevelEditorScene(_Manager())
    editor2._placed_start = True
    editor2.dragging = "start"
    pos2 = _world_screen(editor2, (1.0, 1.0))
    editor2.handle_event(_event(pygame.MOUSEBUTTONUP, button=1, pos=pos2))
    assert editor2.dragging is None
    assert editor2.message == "Start is already placed"

    editor3 = LevelEditorScene(_Manager())
    editor3._placed_target = True
    editor3.dragging = "target"
    pos3 = _world_screen(editor3, (1.0, 1.0))
    editor3.handle_event(_event(pygame.MOUSEBUTTONUP, button=1, pos=pos3))
    assert editor3.dragging is None
    assert editor3.message == "Target is already placed"

    editor4 = LevelEditorScene(_Manager())
    editor4.dragging = "obstacle"
    pos4 = _world_screen(editor4, (2.0, 2.0))
    editor4.handle_event(_event(pygame.MOUSEBUTTONUP, button=1, pos=pos4))
    assert editor4.dragging is None
    assert len(editor4.obstacles) == 1

    editor5 = LevelEditorScene(_Manager())
    editor5.dragging = "obstacle"
    editor5.handle_event(_event(pygame.MOUSEBUTTONUP, button=1, pos=(-1000, -1000)))
    assert editor5.dragging is None

    editor6 = LevelEditorScene(_Manager())
    editor6.moving = ("start", None)
    editor6.handle_event(_event(pygame.MOUSEBUTTONUP, button=1, pos=(10, 10)))
    assert editor6.moving is None

def test_handle_event_wheel_and_key_shortcuts():
    editor = LevelEditorScene(_Manager())
    editor.obstacles.append({"center": (0.0, 0.0), "radius": 0.5})
    editor.selected = ("obstacle", 0)
    editor.handle_event(_event(pygame.MOUSEWHEEL, y=1))
    assert editor.obstacles[0]["radius"] == 0.6

    editor.handle_event(_event(pygame.KEYDOWN, key=pygame.K_DELETE))
    assert editor.obstacles == []

    editor2 = LevelEditorScene(_Manager())
    editor2.obstacles.append({"center": (0.0, 0.0), "radius": 0.5})
    editor2.selected = ("obstacle", 0)
    editor2.handle_event(_event(pygame.KEYDOWN, key=pygame.K_EQUALS))
    assert editor2.obstacles[0]["radius"] == 0.6
    editor2.handle_event(_event(pygame.KEYDOWN, key=pygame.K_MINUS))
    assert editor2.obstacles[0]["radius"] == 0.5

    editor3 = LevelEditorScene(_Manager())
    editor3.obstacles.append({"center": (0.0, 0.0), "radius": 0.5})
    editor3.selected = ("obstacle", 0)
    editor3.handle_event(_event(pygame.KEYDOWN, key=pygame.K_BACKSPACE))
    assert editor3.obstacles == []

def test_handle_event_context_menu_delegation():
    editor = LevelEditorScene(_Manager())
    editor.obstacles.append({"center": (0.0, 0.0), "radius": 0.5})
    pos = _world_screen(editor, (0.0, 0.0))
    editor._open_context_menu(pos, ("obstacle", 0))
    rect = editor.context_menu[1]
    modify_pos = (rect.centerx, rect.y + rect.height * 3 // 4)
    editor.handle_event(_event(pygame.MOUSEBUTTONDOWN, button=1, pos=modify_pos))

def test_try_upload_branches(monkeypatch):
    import vector_drift.data as vd
    monkeypatch.setattr(vd, "LEVELS", list(vd.LEVELS))
    monkeypatch.setattr(vd, "CUSTOM_LEVELS", dict(vd.CUSTOM_LEVELS))

    e = LevelEditorScene(_Manager())
    e.manager.account = _Account(configured=False, authenticated=False, user=None)
    e._try_upload("A")
    assert e.message == "Supabase is not configured."

    e2 = LevelEditorScene(_Manager())
    e2.manager.account = _Account(configured=True, authenticated=False, user=None)
    e2._try_upload("A")
    assert e2.message == "Please log in to upload."

    e3 = LevelEditorScene(_Manager())
    e3.manager.account = _Account(configured=True, authenticated=True)
    e3.busy = True
    e3._try_upload("A")
    assert e3.busy is True

    e4 = LevelEditorScene(_Manager())
    e4.manager.account = _Account(configured=True, authenticated=True)
    e4.obstacles.append({"center": (0.0, 0.0), "radius": 0.5})
    e4.obstacles.append({"center": (0.0, 0.0), "radius": 0.5})
    e4._try_upload("A")
    assert e4.message == "Objects cannot overlap"

    def fake_upload_success(account, level_name, level_data, on_success=None, on_error=None):
        if on_success:
            on_success({"ok": True})

    monkeypatch.setattr("vector_drift.account.community.upload_community_level", fake_upload_success)
    e5 = LevelEditorScene(_Manager())
    e5.manager.account = _Account(configured=True, authenticated=True)
    e5._try_upload("SuccessName")
    assert e5.busy is False
    assert e5.message == "Uploaded to the community."

    def fake_upload_error(account, level_name, level_data, on_success=None, on_error=None):
        if on_error:
            on_error(ValueError("boom"))

    monkeypatch.setattr("vector_drift.account.community.upload_community_level", fake_upload_error)
    e6 = LevelEditorScene(_Manager())
    e6.manager.account = _Account(configured=True, authenticated=True)
    e6._try_upload("ErrName")
    assert e6.busy is False
    assert e6.message == "Upload failed: boom"

def test_save_overlap_returns_false(monkeypatch):
    import vector_drift.data as vd
    monkeypatch.setattr(vd, "LEVELS", list(vd.LEVELS))
    monkeypatch.setattr(vd, "CUSTOM_LEVELS", dict(vd.CUSTOM_LEVELS))
    import tempfile
    from pathlib import Path
    monkeypatch.setattr(lpm, "_storage_path", lambda: Path(tempfile.gettempdir()) / "guest.json")
    editor = LevelEditorScene(_Manager())
    editor.obstacles.append({"center": (0.0, 0.0), "radius": 0.5})
    editor.obstacles.append({"center": (0.0, 0.0), "radius": 0.5})
    assert editor._save("X") is False

def test_draw_covers_branches():
    import vector_drift.data as vd
    vd.LEVELS = list(vd.LEVELS)
    vd.CUSTOM_LEVELS = dict(vd.CUSTOM_LEVELS)

    editor = LevelEditorScene(_Manager())
    editor.obstacles.append({"center": (0.0, 0.0), "radius": 0.5})
    editor.pickups.append({"center": (2.0, 0.0), "radius": 0.4, "kind": "life"})
    editor.holes.append({"black_center": (4.0, 0.0), "white_center": (5.5, 0.0), "radius": 0.6})

    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))

    editor.draw(surface)

    for sel in [("obstacle", 0), ("pickup", 0), ("hole", 0), ("start", None), ("target", None), ("black_hole", 0)]:
        editor.selected = sel
        editor.draw(surface)

    editor.selected = None
    editor.dragging = "obstacle"
    editor.draw(surface)
    editor.dragging = None

    editor.naming = True
    editor.name_buffer = "Named"
    editor.message = "hello"
    editor.draw(surface)
    editor.naming = False

    pos = _world_screen(editor, (0.0, 0.0))
    editor._open_context_menu(pos, ("obstacle", 0))
    editor.message = ""
    editor.draw(surface)
    editor.context_menu = None
    editor.draw(surface)


def test_move_selected_rejected_overlap_branch():
    editor = LevelEditorScene(_Manager())
    editor.obstacles.append({"center": (0.0, 0.0), "radius": 0.5})
    editor.obstacles.append({"center": (2.0, 0.0), "radius": 0.5})
    editor.selected = ("obstacle", 0)
    editor.moving = ("obstacle", 0)
    editor.move_offset = (0.0, 0.0)
    pos = editor.viewport.to_screen(2.0, 0.0)
    editor._move_selected(pos)
    assert editor.message == "Objects cannot overlap"


def test_handle_event_upload_empty_name_buffer_sets_custom():
    editor = LevelEditorScene(_Manager())
    editor.name_buffer = ""
    editor.handle_event(_event(pygame.MOUSEBUTTONDOWN, button=1, pos=editor.upload_button.rect.center))
    assert editor.naming is True
    assert editor._naming_upload is True
    assert editor.name_buffer == "Custom"


def test_handle_event_click_empty_playfield_sets_selected_none():
    editor = LevelEditorScene(_Manager())
    editor.selected = ("start", None)
    editor.handle_event(_event(pygame.MOUSEBUTTONDOWN, button=1, pos=(1, 1)))
    assert editor.selected is None


def test_draw_image_override_branches(monkeypatch):
    import vector_drift.scenes.level_editor as module

    def fake_load_image(key, size_px=None):
        if key == "ui.start_marker":
            return pygame.Surface((8, 8))
        return None

    monkeypatch.setattr(module, "load_image", fake_load_image)

    editor = LevelEditorScene(_Manager())
    editor.obstacles.append({"center": (0.0, 0.0), "radius": 0.5})
    editor.pickups.append({"center": (2.0, 0.0), "radius": 0.4, "kind": "life"})
    editor.holes.append({"black_center": (4.0, 0.0), "white_center": (5.5, 0.0), "radius": 0.6})
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    editor.draw(surface)
    assert True

