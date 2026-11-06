"""Verify the replay timeline (scrubber) seeking works."""

import pygame
import pytest

from vector_drift.scenes.replay import ReplayScene
from vector_drift.scenes.base import SceneManager
from types import SimpleNamespace

pytestmark = pytest.mark.usefixtures("pygame_display")


def _manager():
    audio = SimpleNamespace(
        play=lambda *a, **k: None,
        start_loop=lambda *a, **k: None,
        stop_loop=lambda *a, **k: None,
        toggle_mute=lambda: None,
    )
    return SceneManager(audio)


def _make_scene():
    mgr = _manager()
    mgr.session.replays = [
        {
            "level_id": 1,
            "ship_id": "ship01",
            "fx_text": "0",
            "fy_text": "0",
            "outcome": "timeout",
            "frames": [
                {"t": i * 0.5, "x": i, "y": 0, "vx": 0, "vy": 0, "fx": 0, "fy": 0}
                for i in range(10)
            ],
        }
    ]
    scene = ReplayScene(mgr)
    return scene


def test_timeline_seeks_to_fraction():
    scene = _make_scene()
    assert scene._frame_times
    t0 = scene._frame_times[0]
    t1 = scene._frame_times[-1]

    rect = scene.timeline_rect
    # click at fraction 0.6
    pos = (rect.x + int(rect.w * 0.6), rect.centery)
    event = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=pos)
    scene.handle_event(event)

    expected = t0 + (t1 - t0) * 0.6
    assert abs(scene._playback_time - expected) < 1e-6, scene._playback_time
    # paused after seek
    assert scene.paused is True


def test_timeline_clamp_edges():
    scene = _make_scene()
    t0 = scene._frame_times[0]
    t1 = scene._frame_times[-1]
    rect = scene.timeline_rect

    # click before the track (fraction < 0 -> clamp to start)
    pos = (rect.x - 10, rect.centery)
    event = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=pos)
    scene.handle_event(event)
    assert abs(scene._playback_time - t0) < 1e-6

    # click at the far right edge inside the track -> clamps to end
    pos = (rect.right - 1, rect.centery)
    event = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=pos)
    scene.handle_event(event)
    assert abs(scene._playback_time - t1) < (t1 - t0) / max(1, rect.w) + 1e-6

    # click far outside the track horizontally -> ignored, no change
    pos = (rect.right + 100, rect.centery)
    event = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=pos)
    scene.handle_event(event)
    assert abs(scene._playback_time - t1) < (t1 - t0) / max(1, rect.w) + 1e-6


def test_timeline_no_frames_does_not_crash():
    mgr = _manager()
    mgr.session.replays = [{"level_id": 1, "ship_id": "ship01", "fx_text": "0", "fy_text": "0", "outcome": "timeout", "frames": []}]
    scene = ReplayScene(mgr)
    rect = scene.timeline_rect
    pos = (rect.x + rect.w // 2, rect.centery)
    event = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=pos)
    # should not raise
    scene.handle_event(event)
    assert scene.paused is True


def test_draw_timeline_no_frames():
    scene = _make_scene()
    # clear frames to hit empty branch
    scene._frame_times = []
    surf = pygame.Surface((1280, 720))
    scene._draw_timeline(surf)  # should not raise


def test_draw_timeline_with_frames():
    scene = _make_scene()
    surf = pygame.Surface((1280, 720))
    scene._draw_timeline(surf)  # should not raise


def test_seek_time_public_api():
    scene = _make_scene()
    t0 = scene._frame_times[0]
    t1 = scene._frame_times[-1]
    scene.seek_time(0.5)
    expected = t0 + (t1 - t0) * 0.5
    assert abs(scene._playback_time - expected) < 1e-6


def test_timeline_fraction():
    scene = _make_scene()
    assert scene._timeline_fraction() == 0.0
    scene.seek_time(0.5)
    assert abs(scene._timeline_fraction() - 0.5) < 1e-6


def test_timeline_hit():
    scene = _make_scene()
    rect = scene.timeline_rect
    assert scene._timeline_hit((rect.x + rect.w // 2, rect.centery)) is True
    assert scene._timeline_hit((rect.x + rect.w // 2, rect.y - 100)) is False


def test_timeline_rect_aliases_exist():
    scene = _make_scene()
    assert scene.timeline_rect is not None
    assert scene.slider_rect is scene.timeline_rect
    assert scene.seekbar_rect is scene.timeline_rect
    assert scene.scrubber_rect is scene.timeline_rect
    assert scene.time_slider_rect is scene.timeline_rect
