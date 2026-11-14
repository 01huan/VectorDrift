import os
import sys

import pytest

from vector_drift import config


def test_detect_ui_scale_override(monkeypatch):
    monkeypatch.setenv("VECTOR_DRIFT_SCALE", "1.5")
    assert config._detect_ui_scale(1.0, 1920, 1080) == 1.5


def test_detect_ui_scale_no_screen():
    assert config._detect_ui_scale(1.0, None, None) == 1.0


def test_detect_ui_scale_fullscreen(monkeypatch):
    monkeypatch.delenv("VECTOR_DRIFT_SCALE", raising=False)
    monkeypatch.setattr(config, "FULLSCREEN", True)
    assert config._detect_ui_scale(1.0, 1920, 1080) == 1920 / 1280


def test_detect_ui_scale_windowed(monkeypatch):
    monkeypatch.delenv("VECTOR_DRIFT_SCALE", raising=False)
    monkeypatch.setattr(config, "FULLSCREEN", False)
    val = config._detect_ui_scale(2.0, 1920, 1080)
    assert val >= 1.0


def test_detect_screen_is_empty_without_a_display(monkeypatch):
    monkeypatch.setattr(config, "HEADLESS", True)
    assert config.detect_screen() == (None, None, 1.0)


def test_detect_screen_uses_the_win32_api_on_windows(monkeypatch):
    monkeypatch.setattr(config, "HEADLESS", False)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(config, "_win_screen_size", lambda: (1920, 1080))
    monkeypatch.setattr(config, "_win_dpi_scale", lambda: 1.25)
    assert config.detect_screen() == (1920, 1080, 1.25)


def test_detect_screen_uses_sdl_everywhere_else(monkeypatch):
    monkeypatch.setattr(config, "HEADLESS", False)
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(config, "_sdl_screen_size", lambda: (1920, 1080))
    assert config.detect_screen() == (1920, 1080, 1.0)


def test_win_screen_size_reports_the_primary_display(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    class _User32:
        @staticmethod
        def GetSystemMetrics(index):
            return {0: 1920, 1: 1080}[index]
    import ctypes
    monkeypatch.setattr(ctypes, "windll", type("W", (), {"user32": _User32})())
    assert config._win_screen_size() == (1920, 1080)


def test_sdl_screen_size_uses_sdl(monkeypatch):
    import pygame
    monkeypatch.setattr(pygame.display, "get_init", lambda: True)
    monkeypatch.setattr(pygame.display, "get_desktop_sizes", lambda: [(1920, 1080), (800, 600)])
    assert config._sdl_screen_size() == (1920, 1080)


def test_sdl_screen_size_survives_a_missing_display(monkeypatch):
    import pygame

    def _no_display():
        raise pygame.error("video system not initialized")

    monkeypatch.setattr(pygame.display, "get_init", lambda: True)
    monkeypatch.setattr(pygame.display, "get_desktop_sizes", _no_display)
    with pytest.warns(RuntimeWarning):
        assert config._sdl_screen_size() == (None, None)


def test_sdl_screen_size_ignores_an_empty_display_list(monkeypatch):
    import pygame
    monkeypatch.setattr(pygame.display, "get_init", lambda: True)
    monkeypatch.setattr(pygame.display, "get_desktop_sizes", lambda: [])
    assert config._sdl_screen_size() == (None, None)


def test_sdl_screen_size_ignores_a_broken_display_list(monkeypatch):
    import pygame
    monkeypatch.setattr(pygame.display, "get_init", lambda: True)
    monkeypatch.setattr(pygame.display, "get_desktop_sizes", lambda: [(0, 0)])
    assert config._sdl_screen_size() == (None, None)


def test_the_screen_size_is_measured_once():
    # One source of truth: the window and the canvas are built from the same
    # numbers, so the canvas can never be bigger than the window.
    assert config.SCREEN_SIZE == (config.SCREEN_W, config.SCREEN_H)


def test_the_layout_matches_the_measured_screen():
    # The canvas is built from the screen size, so it always fits.
    if config.SCREEN_W and config.FULLSCREEN:
        assert config.WINDOW_W <= config.SCREEN_W
        assert config.WINDOW_H <= config.SCREEN_H
