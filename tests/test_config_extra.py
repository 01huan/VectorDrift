import os
import sys

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


def test_screen_info_non_windows(monkeypatch):
    # Linux and macOS have no Win32 API to ask: the desktop size comes from
    # SDL, so the layout scales there as well.
    monkeypatch.setattr(config, "HEADLESS", False)
    monkeypatch.setattr(config, "_desktop_screen_info", lambda: (1.0, 1920, 1080))
    monkeypatch.setattr(sys, "platform", "linux")
    assert config._screen_info() == (1.0, 1920, 1080)


def test_screen_info_headless(monkeypatch):
    # A headless run has no display to ask about.
    monkeypatch.setattr(config, "HEADLESS", True)
    monkeypatch.setattr(sys, "platform", "linux")
    assert config._screen_info() == (1.0, None, None)


def test_desktop_screen_info_uses_sdl(monkeypatch):
    import pygame
    monkeypatch.setattr(pygame.display, "get_init", lambda: True)
    monkeypatch.setattr(pygame.display, "get_desktop_sizes", lambda: [(1920, 1080)])
    assert config._desktop_screen_info() == (1.0, 1920, 1080)


def test_desktop_screen_info_survives_a_missing_display(monkeypatch):
    import pygame

    def _no_display():
        raise pygame.error("video system not initialized")

    monkeypatch.setattr(pygame.display, "get_init", lambda: True)
    monkeypatch.setattr(pygame.display, "get_desktop_sizes", _no_display)
    assert config._desktop_screen_info() == (1.0, None, None)
