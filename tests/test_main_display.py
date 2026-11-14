"""The display helpers in main.py."""

import pygame
import pytest

import main
from vector_drift import config


@pytest.fixture(autouse=True)
def _display():
    """pygame with a display, so set_mode() really opens a surface."""
    pygame.display.init()
    yield


def test_open_display_uses_the_measured_screen(monkeypatch):
    # config.SCREEN_SIZE is the only source of truth: the window and the
    # canvas are built from the same numbers.
    monkeypatch.setattr(config, "FULLSCREEN", True)
    monkeypatch.setattr(config, "SCREEN_SIZE", (1920, 1080))
    monkeypatch.setattr(config, "WINDOW_W", 1920)
    monkeypatch.setattr(config, "WINDOW_H", 1080)

    display, canvas, offset = main.open_display()

    assert display.get_size() == (1920, 1080)
    assert canvas.get_size() == (1920, 1080)
    assert offset == (0, 0)


def test_open_display_letterboxes_other_aspect_ratios(monkeypatch):
    monkeypatch.setattr(config, "FULLSCREEN", True)
    monkeypatch.setattr(config, "SCREEN_SIZE", (2560, 1080))
    monkeypatch.setattr(config, "WINDOW_W", 1280)
    monkeypatch.setattr(config, "WINDOW_H", 720)

    display, canvas, offset = main.open_display()

    assert canvas.get_size() == (1280, 720)
    assert offset == (640, 180)
    assert main.margin_rects(display, canvas, offset)      # strips on both sides


def test_the_canvas_never_leaves_the_window(monkeypatch):
    # A canvas bigger than the window would cut the game off instead of
    # scaling it down - the screen size and the layout must agree.
    monkeypatch.setattr(config, "FULLSCREEN", True)
    monkeypatch.setattr(config, "SCREEN_SIZE", (1920, 1080))
    monkeypatch.setattr(config, "WINDOW_W", 2560)
    monkeypatch.setattr(config, "WINDOW_H", 1440)

    display, canvas, offset = main.open_display()

    assert canvas.get_size() == (1920, 1080)
    assert canvas.get_width() <= display.get_width()
    assert canvas.get_height() <= display.get_height()


def test_open_display_falls_back_to_a_window_without_a_screen(monkeypatch):
    # No desktop size (no video driver): the game still opens a window
    # instead of crashing on the fullscreen path.
    monkeypatch.setattr(config, "FULLSCREEN", True)
    monkeypatch.setattr(config, "SCREEN_SIZE", (None, None))

    display, canvas, offset = main.open_display()

    assert offset == (0, 0)
    assert display.get_size() == (config.WINDOW_W, config.WINDOW_H)
    assert canvas.get_size() == (config.WINDOW_W, config.WINDOW_H)


def test_open_display_reports_a_window_that_cannot_be_opened(monkeypatch):
    def _no_display(size, flags=0):
        raise pygame.error("No available video device")

    monkeypatch.setattr(pygame.display, "set_mode", _no_display)

    with pytest.raises(RuntimeError, match="cannot open"):
        main.open_display()


def test_margin_rects_are_the_empty_strips_around_the_canvas(monkeypatch):
    monkeypatch.setattr(config, "FULLSCREEN", True)
    monkeypatch.setattr(config, "SCREEN_SIZE", (2560, 1080))
    monkeypatch.setattr(config, "WINDOW_W", 1280)
    monkeypatch.setattr(config, "WINDOW_H", 720)

    display, canvas, offset = main.open_display()
    rects = main.margin_rects(display, canvas, offset)

    assert rects == [(0, 0, 2560, 180), (0, 900, 2560, 180),
                     (0, 180, 640, 720), (1920, 180, 640, 720)]
