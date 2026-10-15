import pygame
import pytest

from vector_drift.ui import CodeEditor


@pytest.fixture(scope="module", autouse=True)
def _pygame():
    pygame.init()
    yield
    pygame.quit()


@pytest.fixture
def editor():
    ed = CodeEditor((0, 0), 280)
    ed.set_lines(["2x - 0.5y + 1", "y"])
    return ed


def key(ed, k, mod=0):
    return ed.handle_event(pygame.event.Event(pygame.KEYDOWN, key=k, mod=mod, unicode="", scancode=0))


def type_text(ed, text):
    for ch in text:
        ed.handle_event(pygame.event.Event(pygame.TEXTINPUT, text=ch))


def char_x(ed, line, col):
    """Screen x of the boundary before `col` on `line`."""
    return ed.text_area(line).x + ed.font.size(ed.lines[line][:col])[0]


def test_shift_home_selects_to_line_start_and_typing_replaces(editor):
    assert editor.col == len(editor.lines[0])
    key(editor, pygame.K_HOME, pygame.KMOD_LSHIFT)
    assert editor.selected_text() == "2x - 0.5y + 1"
    type_text(editor, "3")
    assert editor.lines[0] == "3" and editor.selection() is None


def test_shift_arrows_and_collapse(editor):
    key(editor, pygame.K_HOME)
    key(editor, pygame.K_RIGHT, pygame.KMOD_LSHIFT)
    key(editor, pygame.K_RIGHT, pygame.KMOD_LSHIFT)
    assert editor.selected_text() == "2x"
    key(editor, pygame.K_LEFT)                     # collapses to the selection start
    assert editor.selection() is None and editor.col == 0


def test_backspace_deletes_selection(editor):
    key(editor, pygame.K_END)
    for _ in range(4):
        key(editor, pygame.K_LEFT, pygame.KMOD_LSHIFT)
    assert editor.selected_text() == " + 1"
    key(editor, pygame.K_BACKSPACE)
    assert editor.lines[0] == "2x - 0.5y"


def test_ctrl_a_selects_current_line_and_ctrl_x_cuts(editor):
    key(editor, pygame.K_DOWN)
    key(editor, pygame.K_a, pygame.KMOD_LCTRL)
    assert editor.line == 1 and editor.selected_text() == "y"
    key(editor, pygame.K_x, pygame.KMOD_LCTRL)
    assert editor.lines == ["2x - 0.5y + 1", ""]


def test_mouse_drag_selects(editor):
    y = editor.line_rect(0).centery
    editor.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=(char_x(editor, 0, 5), y), button=1))
    editor.handle_event(pygame.event.Event(pygame.MOUSEMOTION, pos=(char_x(editor, 0, 9), y), rel=(1, 0),
                                           buttons=(1, 0, 0)))
    editor.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=(char_x(editor, 0, 9), y), button=1))
    assert editor.selected_text() == "0.5y"
    # moving after release does not change the selection
    editor.handle_event(pygame.event.Event(pygame.MOUSEMOTION, pos=(char_x(editor, 0, 13), y), rel=(1, 0),
                                           buttons=(0, 0, 0)))
    assert editor.selected_text() == "0.5y"


def test_click_then_type_keeps_every_character(editor):
    pos = (char_x(editor, 1, 0), editor.line_rect(1).centery)
    editor.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=pos, button=1))
    editor.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=pos, button=1))
    type_text(editor, "3*")
    assert editor.lines[1] == "3*y"
    key(editor, pygame.K_BACKSPACE)
    assert editor.lines[1] == "3y"


def test_double_click_selects_word(editor):
    y = editor.line_rect(0).centery
    pos = (char_x(editor, 0, 6) + 1, y)            # inside "0.5y"
    for _ in range(2):
        editor.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=pos, button=1))
        editor.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=pos, button=1))
    assert editor.selected_text() == "0.5y"


def test_text_cursor_area(editor):
    assert editor.is_text_area(editor.line_rect(1).center)
    assert not editor.is_text_area(editor.header_rect.center)
    editor.enabled = False
    assert not editor.is_text_area(editor.line_rect(1).center)
