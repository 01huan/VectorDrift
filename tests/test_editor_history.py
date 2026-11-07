"""Undo / redo in the Fx / Fy editor, and how game flows touch the history."""

from types import SimpleNamespace

import pygame
import pytest

from vector_drift import config
from vector_drift.hints import get_hint
from vector_drift.scenes.base import SceneManager
from vector_drift.scenes.fail import FailScene
from vector_drift.scenes.game import FLIGHT, SETUP, GameScene
from vector_drift.scenes.levels import LevelSelectScene
from vector_drift.ui import CodeEditor

pytestmark = pytest.mark.usefixtures("pygame_display")

CTRL, SHIFT = pygame.KMOD_LCTRL, pygame.KMOD_LSHIFT


@pytest.fixture
def ed():
    editor = CodeEditor((0, 0), 280)
    editor.set_lines(["", ""], record=False)
    return editor


def key(ed, k, mod=0):
    return ed.handle_event(pygame.event.Event(pygame.KEYDOWN, key=k, mod=mod, unicode="", scancode=0))


def type_text(ed, text):
    for ch in text:
        ed.handle_event(pygame.event.Event(pygame.TEXTINPUT, text=ch))


def undo(ed):
    return key(ed, pygame.K_z, CTRL)


def redo(ed, mod=CTRL | SHIFT, k=pygame.K_z):
    return key(ed, k, mod)


# --- grouping ---------------------------------------------------------------------

def test_a_typed_run_undoes_in_one_step(ed):
    type_text(ed, "abc")
    undo(ed)
    assert ed.lines[0] == ""


def test_operators_and_spaces_end_a_step(ed):
    type_text(ed, "2x+3y - 1")
    states = []
    while ed.lines[0]:
        undo(ed)
        states.append(ed.lines[0])
    assert states == ["2x+3y - ", "2x+3y -", "2x+3y ", "2x+", ""]


def test_moving_the_cursor_ends_a_step(ed):
    type_text(ed, "ab")
    key(ed, pygame.K_LEFT)
    key(ed, pygame.K_RIGHT)
    type_text(ed, "cd")
    undo(ed)
    assert ed.lines[0] == "ab"
    undo(ed)
    assert ed.lines[0] == ""


def test_switching_between_typing_and_deleting_ends_a_step(ed):
    type_text(ed, "abcd")
    key(ed, pygame.K_BACKSPACE)
    key(ed, pygame.K_BACKSPACE)
    type_text(ed, "xy")
    assert ed.lines[0] == "abxy"
    undo(ed)
    assert ed.lines[0] == "ab"                     # both backspaces were one step
    undo(ed)
    assert ed.lines[0] == "abcd"
    undo(ed)
    assert ed.lines[0] == ""


def test_paste_cut_and_deleting_a_selection_are_single_steps(ed, monkeypatch):
    from vector_drift import ui
    clip = {"text": "+9"}
    monkeypatch.setattr(ui, "clipboard_get", lambda: clip["text"])
    monkeypatch.setattr(ui, "clipboard_put", lambda text: clip.update(text=text))
    type_text(ed, "x")
    key(ed, pygame.K_v, CTRL)
    key(ed, pygame.K_v, CTRL)
    assert ed.lines[0] == "x+9+9"
    undo(ed)
    assert ed.lines[0] == "x+9"

    key(ed, pygame.K_HOME)
    key(ed, pygame.K_RIGHT, SHIFT)
    key(ed, pygame.K_x, CTRL)
    key(ed, pygame.K_END, SHIFT)
    key(ed, pygame.K_BACKSPACE)
    assert ed.lines[0] == ""
    undo(ed)
    assert ed.lines[0] == "+9"
    undo(ed)
    assert ed.lines[0] == "x+9"


# --- undo / redo ------------------------------------------------------------------

def test_undo_then_redo_restores(ed):
    type_text(ed, "x+1")
    undo(ed)
    assert ed.lines[0] == "x+"
    redo(ed)
    assert ed.lines[0] == "x+1"


def test_new_edit_after_undo_clears_redo(ed):
    type_text(ed, "x+1")
    undo(ed)
    type_text(ed, "2")
    redo(ed)
    assert ed.lines[0] == "x+2"


@pytest.mark.parametrize("k, mod", [(pygame.K_z, CTRL | SHIFT), (pygame.K_y, CTRL),
                                    (pygame.K_z, pygame.KMOD_RCTRL | pygame.KMOD_RSHIFT)])
def test_both_redo_shortcuts(ed, k, mod):
    type_text(ed, "x+1")
    undo(ed)
    assert redo(ed, mod, k)
    assert ed.lines[0] == "x+1"


def test_ctrl_shift_z_never_undoes(ed):
    type_text(ed, "x+1")
    redo(ed)
    assert ed.lines[0] == "x+1"


def test_undo_and_redo_restore_cursor_and_selection(ed):
    type_text(ed, "abc+def")
    key(ed, pygame.K_HOME)
    key(ed, pygame.K_RIGHT, SHIFT)
    key(ed, pygame.K_RIGHT, SHIFT)                  # "ab" selected, cursor at 2
    key(ed, pygame.K_DELETE)
    assert ed.lines[0] == "c+def" and ed.col == 0

    undo(ed)
    assert ed.lines[0] == "abc+def"
    assert ed.selection() == (0, 2) and ed.col == 2
    redo(ed)
    assert ed.lines[0] == "c+def"
    assert ed.selection() is None and ed.col == 0


def test_history_keeps_the_last_100_steps(ed):
    for _ in range(150):
        type_text(ed, "+")                          # each operator is its own step
    for _ in range(200):
        undo(ed)
    assert ed.lines[0] == "+" * 50


def test_empty_history_is_harmless(ed):
    assert undo(ed) and redo(ed) and redo(ed, CTRL, pygame.K_y)
    assert ed.lines == ["", ""]


def test_fx_and_fy_have_separate_histories(ed):
    type_text(ed, "x")
    key(ed, pygame.K_DOWN)
    type_text(ed, "y")
    undo(ed)
    assert ed.lines == ["x", ""]
    undo(ed)                                        # Fy has nothing more to undo
    assert ed.lines == ["x", ""]
    key(ed, pygame.K_UP)
    undo(ed)
    assert ed.lines == ["", ""]


def test_disabled_editor_ignores_undo_but_keeps_history(ed):
    type_text(ed, "x+1")
    ed.enabled = False
    undo(ed)
    redo(ed)
    assert ed.lines[0] == "x+1"
    ed.enabled = True
    undo(ed)
    assert ed.lines[0] == "x+"


def test_program_writes_are_one_undoable_step(ed):
    type_text(ed, "x")
    ed.set_lines(["7-x", "-y"])
    undo(ed)
    assert ed.lines == ["x", "-y"]                  # only the line with the cursor
    key(ed, pygame.K_DOWN)
    undo(ed)
    assert ed.lines == ["x", ""]


def test_undo_notifies_the_owner(ed):
    seen = []
    ed.on_change = lambda e: seen.append(list(e.lines))
    type_text(ed, "x")
    undo(ed)
    assert seen[-1] == ["", ""]


# --- game flows -------------------------------------------------------------------

def _manager():
    audio = SimpleNamespace(play=lambda *a, **k: None, start_loop=lambda *a, **k: None,
                            stop_loop=lambda *a, **k: None)
    manager = SceneManager(audio)
    return manager


def _enter(manager, level_id):
    """Start a level from level select, as the player does."""
    select = LevelSelectScene(manager)
    manager.switch(select)
    select._start(level_id)
    return manager.scene


def test_hint_answer_can_be_undone_and_keeps_solution_used():
    manager = _manager()
    scene = _enter(manager, 1)
    type_text(scene.editor, "9")
    scene._open_hint()
    popup = scene.hint_popup
    while not popup.on_answer_page:                # Enter = next step, then confirm
        scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN, mod=0,
                                              unicode="", scancode=0))
    assert scene.solution_used
    answer = get_hint(1).answers[0]
    pos = popup.apply_buttons[0].rect.center
    scene.handle_event(pygame.event.Event(pygame.MOUSEMOTION, pos=pos, rel=(0, 0), buttons=(0, 0, 0)))
    scene.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=pos, button=1))
    assert scene.editor.lines == [answer.fx, answer.fy]

    assert answer.fx != "9"
    scene.editor.line = 0
    undo(scene.editor)
    assert scene.editor.lines[0] == "9"
    assert scene.solution_used
    assert manager.session.fx_text == "9"


def test_undo_reruns_the_problem_check():
    scene = _enter(_manager(), 1)
    type_text(scene.editor, "x+")
    assert not scene.valid
    key(scene.editor, pygame.K_BACKSPACE)
    assert scene.valid
    undo(scene.editor)
    assert scene.editor.lines[0] == "x+" and not scene.valid


def test_flight_locks_undo_and_history_survives_it():
    scene = _enter(_manager(), 1)
    type_text(scene.editor, "1+2")
    scene._try_launch()
    assert scene.state == FLIGHT
    undo(scene.editor)
    assert scene.editor.lines[0] == "1+2"
    scene._abort()
    assert scene.state == SETUP
    undo(scene.editor)
    assert scene.editor.lines[0] == "1+"


def test_entering_from_level_select_starts_a_new_history():
    manager = _manager()
    scene = _enter(manager, 1)
    type_text(scene.editor, "x")
    again = _enter(manager, 1)
    undo(again.editor)
    assert again.editor.lines == ["", ""]


def test_retry_keeps_formulas_and_their_history():
    manager = _manager()
    scene = _enter(manager, 1)
    type_text(scene.editor, "x+1")
    fail = FailScene(manager)
    manager.switch(fail)
    fail.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN, mod=0, unicode="", scancode=0))
    retry = manager.scene
    assert isinstance(retry, GameScene) and retry is not scene
    assert retry.editor.lines[0] == "x+1"
    undo(retry.editor)
    assert retry.editor.lines[0] == "x+"


def test_replay_after_a_win_starts_a_new_history():
    from vector_drift.scenes.win import WinScene
    manager = _manager()
    scene = _enter(manager, 1)
    type_text(scene.editor, "x")
    manager.session.stats = {"time": 1.0, "total_time": 1.0, "attempts": 1, "lives_left": 5,
                             "max_lives": 5, "fx": "x", "fy": "0", "solution_used": False}
    win = WinScene(manager)
    manager.switch(win)
    win.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN, mod=0, unicode="", scancode=0))
    replay = manager.scene
    assert isinstance(replay, GameScene) and replay.editor.lines == ["", ""]
    undo(replay.editor)
    assert replay.editor.lines == ["", ""]


# --- wrapping a selection in parentheses --------------------------------------------

def _select(ed, start, end):
    key(ed, pygame.K_HOME)
    for _ in range(start):
        key(ed, pygame.K_RIGHT)
    for _ in range(end - start):
        key(ed, pygame.K_RIGHT, SHIFT)


def test_open_paren_wraps_the_selection_and_keeps_it_selected(ed):
    type_text(ed, "2*x+1")
    _select(ed, 2, 5)
    type_text(ed, "(")
    assert ed.lines[0] == "2*(x+1)"
    assert ed.selected_text() == "x+1"


def test_two_open_parens_wrap_twice(ed):
    type_text(ed, "x+1")
    _select(ed, 0, 3)
    type_text(ed, "((")
    assert ed.lines[0] == "((x+1))"
    assert ed.selected_text() == "x+1"


def test_wrapping_is_one_undo_step(ed):
    type_text(ed, "x+1")
    _select(ed, 0, 3)
    type_text(ed, "(")
    type_text(ed, "(")
    undo(ed)
    assert ed.lines[0] == "(x+1)" and ed.selected_text() == "x+1"
    undo(ed)
    assert ed.lines[0] == "x+1" and ed.selected_text() == "x+1"
    redo(ed)
    assert ed.lines[0] == "(x+1)" and ed.selected_text() == "x+1"


def test_open_paren_before_other_text_only_inserts_it(ed):
    type_text(ed, "x+1")
    key(ed, pygame.K_HOME)
    type_text(ed, "(")
    assert ed.lines[0] == "(x+1" and ed.col == 1


def test_close_paren_still_replaces_the_selection(ed):
    type_text(ed, "x+1")
    _select(ed, 0, 3)
    type_text(ed, ")")
    assert ed.lines[0] == ")"


def test_wrapping_respects_the_length_limit(ed):
    ed.max_len = 4
    type_text(ed, "x+1")
    _select(ed, 0, 3)
    type_text(ed, "(")
    assert ed.lines[0] == "x+1"


# --- auto-closing parentheses ------------------------------------------------------

def _cursor_at(ed, text, col):
    ed.set_lines([text, ""], record=False)
    key(ed, pygame.K_HOME)
    for _ in range(col):
        key(ed, pygame.K_RIGHT)


def test_open_paren_at_the_line_end_adds_the_close_paren(ed):
    type_text(ed, "sin(")
    assert ed.lines[0] == "sin()" and ed.col == 4


def test_open_paren_before_a_space_adds_the_close_paren(ed):
    _cursor_at(ed, "2 + y", 1)
    type_text(ed, "(")
    assert ed.lines[0] == "2() + y" and ed.col == 2


def test_open_paren_before_a_close_paren_only_inserts_it(ed):
    _cursor_at(ed, "sin()", 4)
    type_text(ed, "(")
    assert ed.lines[0] == "sin(()" and ed.col == 5


def test_typing_a_whole_call_does_not_double_the_close_parens(ed):
    type_text(ed, "sin(cos(x))")
    assert ed.lines[0] == "sin(cos(x))" and ed.col == 11


def test_close_paren_steps_over_the_next_close_paren(ed):
    _cursor_at(ed, "sin()", 4)
    type_text(ed, "x)")
    assert ed.lines[0] == "sin(x)" and ed.col == 6


def test_close_paren_steps_over_only_when_the_parens_are_balanced(ed):
    _cursor_at(ed, "((x)", 3)
    type_text(ed, ")")
    assert ed.lines[0] == "((x))" and ed.col == 4


def test_backspace_in_empty_parens_removes_both(ed):
    type_text(ed, "sin(")
    key(ed, pygame.K_BACKSPACE)
    assert ed.lines[0] == "sin" and ed.col == 3


def test_backspace_between_typed_parens_removes_both(ed):
    _cursor_at(ed, "sin()", 4)
    key(ed, pygame.K_BACKSPACE)
    assert ed.lines[0] == "sin" and ed.col == 3


def test_backspace_after_an_open_paren_with_text_removes_only_it(ed):
    _cursor_at(ed, "(x)", 1)
    key(ed, pygame.K_BACKSPACE)
    assert ed.lines[0] == "x)" and ed.col == 0


def test_undo_removes_the_auto_closed_pair_together(ed):
    type_text(ed, "x+")
    type_text(ed, "(")
    undo(ed)
    assert ed.lines[0] == "x+" and ed.col == 2
    redo(ed)
    assert ed.lines[0] == "x+()" and ed.col == 3


def test_auto_close_needs_room_for_both_parens(ed):
    ed.max_len = 4
    type_text(ed, "sin(")
    assert ed.lines[0] == "sin(" and ed.col == 4
