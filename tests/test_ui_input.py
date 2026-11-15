"""Tests for the single-line text field used by the search bar."""

import pygame
import pytest

from vector_drift import config
from vector_drift.ui import TextInput

pytestmark = pytest.mark.usefixtures("pygame_display")


def _field(**kwargs):
    return TextInput((10, 10, 200, 30), "hint", **kwargs)


def _click(widget, pos=None):
    widget.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1,
                                           pos=pos or widget.rect.center))


def _text(widget, value):
    return widget.handle_event(pygame.event.Event(pygame.TEXTINPUT, text=value))


def _key(widget, key, mod=0, unicode=""):
    return widget.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key, mod=mod,
                                                   unicode=unicode))


def test_a_new_field_is_empty_and_inactive():
    widget = _field()
    assert widget.text == ""
    assert not widget.active


def test_typing_goes_into_the_focused_field():
    widget = _field()
    _text(widget, "a")
    assert widget.text == ""            # not focused yet
    _click(widget)
    assert widget.active
    _text(widget, "a")
    assert widget.text == "a"


def test_clicking_elsewhere_drops_the_focus():
    widget = _field()
    _click(widget)
    assert widget.active
    _click(widget, pos=(500, 500))
    assert not widget.active


def test_backspace_and_delete():
    widget = _field()
    _click(widget)
    _text(widget, "abc")
    _key(widget, pygame.K_BACKSPACE)
    assert widget.text == "ab"
    widget.cursor = 0
    _key(widget, pygame.K_DELETE)
    assert widget.text == "b"


def test_the_cursor_moves_with_the_arrow_keys():
    widget = _field()
    _click(widget)
    _text(widget, "abc")
    _key(widget, pygame.K_HOME)
    assert widget.cursor == 0
    _key(widget, pygame.K_END)
    assert widget.cursor == 3
    _key(widget, pygame.K_LEFT)
    assert widget.cursor == 2
    _key(widget, pygame.K_RIGHT)
    assert widget.cursor == 3


def test_a_numeric_field_only_accepts_digits():
    widget = _field(numeric=True)
    _click(widget)
    _text(widget, "1a2b3")
    assert widget.text == "123"


def test_the_text_is_limited_to_max_length():
    widget = _field(max_length=3)
    _click(widget)
    _text(widget, "abcdef")
    assert widget.text == "abc"


def test_the_listener_is_called_when_the_text_changes():
    seen = []
    widget = TextInput((0, 0, 100, 30), on_change=seen.append)
    _click(widget)
    _text(widget, "x")
    assert seen == ["x"]


def test_a_broken_listener_does_not_break_typing():
    def boom(_text):
        raise RuntimeError("boom")

    widget = TextInput((0, 0, 100, 30), on_change=boom)
    _click(widget)
    _text(widget, "x")
    assert widget.text == "x"


def test_set_text_and_clear_notify_the_owner():
    seen = []
    widget = TextInput((0, 0, 100, 30), on_change=seen.append)
    widget.text = "hello"
    assert widget.text == "hello"
    widget.clear()
    assert widget.text == ""
    assert seen == ["hello", ""]


def test_the_same_character_is_not_inserted_twice():
    widget = _field()
    _click(widget)
    # A KEYDOWN with a printable character, then the matching TEXTINPUT.
    _key(widget, pygame.K_a, unicode="a")
    _text(widget, "a")
    assert widget.text == "a"


def test_the_field_draws():
    widget = _field()
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    widget.draw(surface)
    _click(widget)
    _text(widget, "hello")
    widget.draw(surface)
