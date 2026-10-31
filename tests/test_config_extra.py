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
    monkeypatch.setattr(sys, "platform", "linux")
    assert config._screen_info() == (1.0, None, None)
