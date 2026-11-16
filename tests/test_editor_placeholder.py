"""Grey placeholders on empty editor lines: tutorial only, never filled in."""

import pygame
import pytest

from vector_drift.ui import CodeEditor


@pytest.fixture(scope="module", autouse=True)
def _pygame():
    pygame.init()
    yield
    pygame.quit()


def type_text(ed, text):
    for ch in text:
        ed.handle_event(pygame.event.Event(pygame.TEXTINPUT, text=ch))


def key(ed, k):
    return ed.handle_event(pygame.event.Event(pygame.KEYDOWN, key=k, mod=0, unicode="", scancode=0))


def rendered_texts(ed, monkeypatch):
    """Every string the editor's code font renders in one draw."""
    seen = []
    real = ed.font

    class Spy:
        def render(self, text, *a, **k):
            seen.append(text)
            return real.render(text, *a, **k)

        def size(self, text):
            return real.size(text)

    monkeypatch.setattr(ed, "font", Spy())
    ed.draw(pygame.Surface((400, 400)))
    return seen


def test_placeholder_shows_only_while_the_line_is_empty():
    ed = CodeEditor((0, 0), 280, placeholders=("5", "0"))
    assert ed.placeholder(0) == "5" and ed.placeholder(1) == "0"
    type_text(ed, "3")
    assert ed.placeholder(0) is None                 # any text hides it
    key(ed, pygame.K_BACKSPACE)
    assert ed.lines[0] == "" and ed.placeholder(0) == "5"   # cleared: back again


def test_placeholder_is_drawn_on_the_current_empty_line(monkeypatch):
    ed = CodeEditor((0, 0), 280, placeholders=("5", "0"))
    texts = rendered_texts(ed, monkeypatch)
    assert "5" in texts and "0" in texts


def test_placeholder_is_never_filled_in():
    ed = CodeEditor((0, 0), 280, placeholders=("5", "0"))
    for k in (pygame.K_TAB, pygame.K_RETURN, pygame.K_RIGHT, pygame.K_END):
        key(ed, k)
    assert ed.lines == ["", ""]


def test_placeholder_is_not_part_of_the_formula():
    """The text the formulas are read from stays empty: the placeholder is never used."""
    ed = CodeEditor((0, 0), 280, placeholders=("5", "0"))
    plain = CodeEditor((0, 0), 280)
    assert ed.lines == plain.lines == ["", ""]
    assert ed.selected_text() == plain.selected_text()


def test_ordinary_editor_has_no_placeholder(monkeypatch):
    """Levels, custom / community levels and Function Lab: no grey hint text."""
    ed = CodeEditor((0, 0), 280)
    assert ed.placeholders == ()
    assert ed.placeholder(0) is None and ed.placeholder(1) is None
    # The current empty line draws no text at all; the other empty line keeps
    # the editor's existing dim "0" (unchanged behaviour), nothing else.
    texts = rendered_texts(ed, monkeypatch)
    assert [t for t in texts if t not in ("Fx", "Fy", " = ")] == ["0"]


def test_game_level_editor_has_no_placeholder(pygame_display):
    from types import SimpleNamespace
    from vector_drift.scenes.base import SceneManager
    from vector_drift.scenes.game import GameScene
    audio = SimpleNamespace(play=lambda *a, **k: None, start_loop=lambda *a, **k: None,
                            stop_loop=lambda *a, **k: None)
    manager = SceneManager(audio)
    manager.session.level_id = 1
    scene = GameScene(manager)
    assert scene.editor.lines == ["", ""]
    assert scene.editor.placeholders == ()
