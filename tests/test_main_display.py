"""The display helpers in main.py."""

import pygame

import main
from vector_drift import config


def test_desktop_size_returns_the_primary_display(monkeypatch):
    monkeypatch.setattr(pygame.display, "get_desktop_sizes", lambda: [(1920, 1080), (800, 600)])
    assert main.desktop_size(pygame) == (1920, 1080)


def test_desktop_size_is_none_without_a_display(monkeypatch):
    def _no_display():
        raise pygame.error("video system not initialized")

    monkeypatch.setattr(pygame.display, "get_desktop_sizes", _no_display)
    assert main.desktop_size(pygame) is None


def test_desktop_size_is_none_for_an_empty_list(monkeypatch):
    monkeypatch.setattr(pygame.display, "get_desktop_sizes", lambda: [])
    assert main.desktop_size(pygame) is None


def test_open_display_falls_back_to_a_window_without_a_desktop(monkeypatch):
    # No desktop size (no video driver): the game still opens a window
    # instead of crashing on the fullscreen path.
    monkeypatch.setattr(config, "FULLSCREEN", True)
    monkeypatch.setattr(main, "desktop_size", lambda pygame: None)

    display, canvas, offset = main.open_display()

    assert offset == (0, 0)
    assert display.get_size() == (config.WINDOW_W, config.WINDOW_H)
    assert canvas.get_size() == (config.WINDOW_W, config.WINDOW_H)
