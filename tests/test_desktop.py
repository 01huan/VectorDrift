import sys

import pygame
import pytest

from vector_drift import desktop


def test_set_cursor_noop_when_same():
    desktop._current_cursor = "arrow"
    desktop.set_cursor("arrow")
    assert desktop._current_cursor == "arrow"


def test_set_cursor_switches_and_handles_pygame_error(monkeypatch):
    desktop._current_cursor = None

    def _raise(*a, **k):
        raise pygame.error("no display")

    monkeypatch.setattr(pygame.mouse, "set_cursor", _raise)
    desktop.set_cursor("text")  # should not raise
    assert desktop._current_cursor == "text"


def test_disable_ime_non_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    # should return immediately without touching pygame
    desktop.disable_ime()


def test_disable_ime_no_window(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")

    class FakeDisplay:
        def get_wm_info(self):
            return {}

    monkeypatch.setattr(pygame, "display", FakeDisplay())
    desktop.disable_ime()  # hwnd falsy -> return


def test_disable_ime_get_wm_info_raises(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")

    class FakeDisplay:
        def get_wm_info(self):
            raise AttributeError("no info")

    monkeypatch.setattr(pygame, "display", FakeDisplay())
    desktop.disable_ime()  # exception swallowed
