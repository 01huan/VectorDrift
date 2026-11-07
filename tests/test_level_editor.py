import pygame

from vector_drift import config, data
from vector_drift.account import local_profile_manager as lpm
from vector_drift.account.integration import load_guest_profile_into_session
from vector_drift.scenes.base import Session
from vector_drift.scenes.level_editor import LevelEditorScene


class _Audio:
    def play(self, _sound):
        pass


class _Manager:
    def __init__(self):
        self.session = Session()
        self.audio = _Audio()
        self.account = None
        self.scene = None

    def switch(self, scene):
        self.scene = scene


def _event(event_type, **kwargs):
    return pygame.event.Event(event_type, kwargs)


def _screen_pos(world):
    # Use the editor's viewport for world-to-screen conversion
    editor = LevelEditorScene(_Manager())
    return editor.viewport.to_screen(*world)


def test_custom_level_saves_and_loads_for_guest(tmp_path, monkeypatch):
    monkeypatch.setattr(lpm, "_storage_path", lambda: tmp_path / "guest.json")
    monkeypatch.setattr(data, "LEVELS", list(data.LEVELS))
    monkeypatch.setattr(data, "CUSTOM_LEVELS", dict(data.CUSTOM_LEVELS))
    manager = _Manager()
    editor = LevelEditorScene(manager)
    editor.obstacles.append({"center": (0.0, 0.0), "radius": 0.7})

    assert editor._save("Persisted")

    restored = Session()
    assert load_guest_profile_into_session(restored)
    assert len(restored.custom_levels) == 1
    level = restored.custom_levels[0]
    assert level.name == "Persisted"
    assert level.obstacles[0].center == (0.0, 0.0)
    assert level.obstacles[0].radius == 0.7
    assert data.get_level(level.id) == level


def test_editor_resizes_and_rejects_overlapping_move():
    editor = LevelEditorScene(_Manager())
    editor.obstacles.append({"center": (0.0, 0.0), "radius": 0.5})
    editor.selected = ("obstacle", 0)

    editor.handle_event(_event(pygame.KEYDOWN, key=pygame.K_PLUS, unicode="+"))
    assert editor.obstacles[0]["radius"] == 0.6

    start = _screen_pos((0.0, 0.0))
    target = _screen_pos(editor.target)
    editor.handle_event(_event(pygame.MOUSEBUTTONDOWN, button=1, pos=start))
    editor.handle_event(_event(pygame.MOUSEMOTION, pos=target, rel=(0, 0), buttons=(1, 0, 0)))
    assert editor.obstacles[0]["center"] == (0.0, 0.0)
    assert editor.message == "Objects cannot overlap"


def test_right_click_context_menu_deletes_object():
    editor = LevelEditorScene(_Manager())
    editor.obstacles.append({"center": (0.0, 0.0), "radius": 0.5})
    center = _screen_pos((0.0, 0.0))
    editor.handle_event(_event(pygame.MOUSEBUTTONDOWN, button=3, pos=center))

    assert editor.context_menu is not None
    _, rect = editor.context_menu
    delete = (rect.centerx, rect.y + rect.height // 4)
    editor.handle_event(_event(pygame.MOUSEBUTTONDOWN, button=1, pos=delete))

    assert editor.obstacles == []
    assert editor.context_menu is None


def test_editing_custom_level_keeps_its_id(monkeypatch):
    monkeypatch.setattr(data, "LEVELS", list(data.LEVELS))
    monkeypatch.setattr(data, "CUSTOM_LEVELS", dict(data.CUSTOM_LEVELS))
    level = data.LevelSpec(
        id=987654, name="Before", start=(-7.0, 0.0), target_center=(7.0, 0.0),
        target_radius=1.0, ship_id="ship01",
    )
    manager = _Manager()
    manager.session.custom_levels = [level]
    manager.session.custom_level_ids = {level.id}
    editor = LevelEditorScene(manager, level=level)
    editor.target = (6.0, 0.0)

    assert editor._save("After")
    assert manager.session.custom_levels[0].id == level.id
    assert manager.session.custom_levels[0].name == "After"
