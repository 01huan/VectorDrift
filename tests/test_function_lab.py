"""The Function Lab: writing, naming, saving and importing a force function."""

import pygame
import pytest

from types import SimpleNamespace

from vector_drift import config
from vector_drift.function_library import (
    SavedFunction,
    clean_name,
    find_function,
    library_from_rows,
    library_to_rows,
    make_function,
)
from vector_drift.scenes.base import SceneManager
from vector_drift.scenes.function_lab import FunctionLabScene
from vector_drift.scenes.game import GameScene
from vector_drift.scenes.levels import LevelSelectScene

pytestmark = pytest.mark.usefixtures("pygame_display")


def _manager():
    audio = SimpleNamespace(play=lambda *a, **k: None, toggle_mute=lambda: None,
                            start_loop=lambda *a, **k: None, stop_loop=lambda *a, **k: None)
    return SceneManager(audio)


def _click(scene, rect):
    scene.handle_event(pygame.event.Event(pygame.MOUSEMOTION, pos=rect.center))
    scene.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=rect.center))


def _type(scene, text):
    for char in text:
        scene.editor.handle_event(pygame.event.Event(pygame.TEXTINPUT, text=char))


# --- the data model -------------------------------------------------------------

def test_clean_name_never_returns_an_empty_name():
    assert clean_name("  ") == "Untitled"
    assert clean_name(None) == "Untitled"
    assert clean_name("  my  field ") == "my field"
    assert len(clean_name("x" * 100)) == 40


def test_library_rows_round_trip():
    function = make_function("vortex", "-y", "x")
    rows = library_to_rows([function])
    assert rows == [{"id": function.id, "name": "vortex", "fx": "-y", "fy": "x"}]
    restored = library_from_rows(rows)
    assert restored == [function]
    assert find_function(restored, function.id) == function
    assert find_function(restored, "nope") is None


def test_broken_library_rows_are_skipped():
    rows = [{"name": "no formulas"}, {"fx": "x"}, "not a row", {"fx": "x", "fy": "y"}]
    restored = library_from_rows(rows)
    assert len(restored) == 1
    assert (restored[0].fx, restored[0].fy) == ("x", "y")


def test_duplicate_ids_get_a_new_one():
    restored = library_from_rows([{"id": "a", "fx": "x", "fy": "y"},
                                  {"id": "a", "fx": "z", "fy": "w"}])
    assert len({function.id for function in restored}) == 2


# --- the level select ------------------------------------------------------------

def test_level_select_has_a_function_lab_button():
    manager = _manager()
    scene = LevelSelectScene(manager)
    manager.switch(scene)
    assert scene.lab_button.label == "Function Lab"
    _click(scene, scene.lab_button.rect)
    assert isinstance(manager.scene, FunctionLabScene)


# --- the lab ---------------------------------------------------------------------

def test_saving_stores_the_function_in_the_library():
    manager = _manager()
    scene = FunctionLabScene(manager)
    manager.switch(scene)
    _type(scene, "x")
    scene.editor.set_lines(["-y", "x"])
    scene.name_input.set_text("vortex")
    _click(scene, scene.save_button.rect)
    library = manager.session.function_library
    assert len(library) == 1
    assert (library[0].name, library[0].fx, library[0].fy) == ("vortex", "-y", "x")


def test_an_invalid_formula_is_not_saved():
    manager = _manager()
    scene = FunctionLabScene(manager)
    manager.switch(scene)
    scene.editor.set_lines(["x +", "y"])
    assert not scene.valid
    _click(scene, scene.save_button.rect)
    assert manager.session.function_library == []
    assert "fix the formulas" in scene.message.lower()


def test_importing_marks_the_function_for_the_levels():
    manager = _manager()
    scene = FunctionLabScene(manager)
    manager.switch(scene)
    scene.editor.set_lines(["-y", "x"])
    scene.name_input.set_text("vortex")
    _click(scene, scene.save_button.rect)
    _click(scene, scene.rows[0][2]["import"].rect)
    assert manager.session.imported_function_id == manager.session.function_library[0].id
    assert manager.session.imported_function.name == "vortex"


def test_deleting_the_imported_function_clears_the_import():
    manager = _manager()
    scene = FunctionLabScene(manager)
    manager.switch(scene)
    scene.editor.set_lines(["-y", "x"])
    scene.name_input.set_text("vortex")
    _click(scene, scene.save_button.rect)
    _click(scene, scene.rows[0][2]["import"].rect)
    _click(scene, scene.rows[0][2]["delete"].rect)
    assert manager.session.function_library == []
    assert manager.session.imported_function_id is None


def test_loading_a_function_puts_it_into_the_editor():
    manager = _manager()
    scene = FunctionLabScene(manager)
    manager.switch(scene)
    scene.editor.set_lines(["-y", "x"])
    scene.name_input.set_text("vortex")
    _click(scene, scene.save_button.rect)
    scene.editor.set_lines(["", ""])
    _click(scene, scene.rows[0][2]["load"].rect)
    assert scene.editor.lines == ["-y", "x"]
    assert scene.name_input.text == "vortex"


def test_saving_twice_updates_the_same_function():
    manager = _manager()
    scene = FunctionLabScene(manager)
    manager.switch(scene)
    scene.editor.set_lines(["-y", "x"])
    scene.name_input.set_text("vortex")
    _click(scene, scene.save_button.rect)
    scene.editor.set_lines(["y", "-x"])
    _click(scene, scene.save_button.rect)
    assert len(manager.session.function_library) == 1
    assert manager.session.function_library[0].fx == "y"


def test_the_lab_draws_without_a_display():
    manager = _manager()
    scene = FunctionLabScene(manager)
    manager.switch(scene)
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    scene.editor.set_lines(["x", "y"])
    scene.draw(surface)
    scene.update(0.016)


def test_typing_in_the_name_field_stays_out_of_the_editor():
    manager = _manager()
    scene = FunctionLabScene(manager)
    manager.switch(scene)
    _click(scene, scene.name_input.rect)
    for char in "abc":
        scene.handle_event(pygame.event.Event(pygame.TEXTINPUT, text=char))
    assert scene.name_input.text == "abc"
    assert scene.editor.lines == ["", ""]


def test_typing_in_the_editor_stays_out_of_the_name_field():
    manager = _manager()
    scene = FunctionLabScene(manager)
    manager.switch(scene)
    _click(scene, scene.editor.text_area(0))
    for char in "xy":
        scene.handle_event(pygame.event.Event(pygame.TEXTINPUT, text=char))
    assert scene.editor.lines[0] == "xy"
    assert scene.name_input.text == ""


def test_the_new_button_empties_the_editor():
    manager = _manager()
    scene = FunctionLabScene(manager)
    manager.switch(scene)
    scene.editor.set_lines(["x", "y"])
    scene.name_input.set_text("vortex")
    _click(scene, scene.new_button.rect)
    assert scene.editor.lines == ["", ""]
    assert scene.name_input.text == ""


def test_a_long_library_is_paged():
    manager = _manager()
    manager.session.function_library = [make_function(f"f{i}", "x", "y") for i in range(10)]
    scene = FunctionLabScene(manager)
    manager.switch(scene)
    assert scene.page_count == 2
    assert len(scene.rows) == 7
    assert scene.prev_button.enabled is False
    assert scene.next_button.enabled is True
    _click(scene, scene.next_button.rect)
    assert scene.page == 1
    assert len(scene.rows) == 3
    assert scene.prev_button.enabled is True
    _click(scene, scene.prev_button.rect)
    assert scene.page == 0


def test_the_lab_previews_the_field():
    manager = _manager()
    scene = FunctionLabScene(manager)
    manager.switch(scene)
    scene.editor.set_lines(["-y", "x"])
    assert scene.valid
    assert scene.field_layer is not None
    assert scene.max_force > 0
    assert scene.probe                       # the probe moved


# --- using the function in a normal level ----------------------------------------

def test_the_imported_function_starts_the_level():
    manager = _manager()
    function = make_function("vortex", "-y", "x")
    manager.session.function_library = [function]
    manager.session.imported_function_id = function.id
    scene = LevelSelectScene(manager)
    manager.switch(scene)
    scene._start(1)
    assert manager.session.fx_text == "-y"
    assert manager.session.fy_text == "x"
    assert manager.scene.editor.lines == ["-y", "x"]


def test_without_an_imported_function_the_level_starts_empty():
    manager = _manager()
    scene = LevelSelectScene(manager)
    manager.switch(scene)
    scene._start(1)
    assert manager.session.fx_text == ""
    assert manager.session.fy_text == ""


def test_the_game_screens_lab_button_loads_a_function():
    manager = _manager()
    function = make_function("vortex", "-y", "x")
    manager.session.function_library = [function]
    manager.session.level_id = 1
    scene = GameScene(manager)
    manager.switch(scene)
    _click(scene, scene.lab_button.rect)
    assert scene.lab_popup
    assert len(scene.lab_rows) == 1
    _click(scene, scene.lab_rows[0][1])
    assert scene.editor.lines == ["-y", "x"]
    assert not scene.lab_popup
    assert manager.session.fx_text == "-y"


def test_the_lab_popup_closes_on_escape():
    manager = _manager()
    manager.session.function_library = [make_function("vortex", "-y", "x")]
    manager.session.level_id = 1
    scene = GameScene(manager)
    manager.switch(scene)
    _click(scene, scene.lab_button.rect)
    assert scene.lab_popup
    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, mod=0))
    assert not scene.lab_popup


def test_the_lab_popup_with_an_empty_library():
    manager = _manager()
    manager.session.level_id = 1
    scene = GameScene(manager)
    manager.switch(scene)
    _click(scene, scene.lab_button.rect)
    assert scene.lab_popup
    assert scene.lab_rows == []
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    scene.draw(surface)


# --- persistence ------------------------------------------------------------------

def test_the_library_is_saved_in_the_profile():
    from vector_drift.account.integration import (
        session_to_guest_profile,
        session_to_profile,
    )

    manager = _manager()
    function = make_function("vortex", "-y", "x")
    manager.session.function_library = [function]
    manager.session.imported_function_id = function.id
    profile = session_to_guest_profile(manager.session)
    assert profile.stats["function_library"] == library_to_rows([function])
    assert profile.stats["imported_function_id"] == function.id
    assert session_to_profile(manager.session, "guest").stats["function_library"]


def test_the_library_comes_back_with_the_profile():
    from vector_drift.account.integration import apply_profile_to_session, session_to_profile

    manager = _manager()
    function = make_function("vortex", "-y", "x")
    manager.session.function_library = [function]
    manager.session.imported_function_id = function.id
    profile = session_to_profile(manager.session, "guest")

    other = _manager()
    apply_profile_to_session(other.session, profile, "guest")
    assert other.session.function_library == [function]
    assert other.session.imported_function_id == function.id
    assert other.session.imported_function.name == "vortex"


def test_deleting_the_local_data_clears_the_library():
    from vector_drift.account.integration import reset_session_to_guest

    manager = _manager()
    manager.session.function_library = [make_function("vortex", "-y", "x")]
    manager.session.imported_function_id = "abc"
    reset_session_to_guest(manager.session)
    assert manager.session.function_library == []
    assert manager.session.imported_function_id is None
