"""Replay timeline: frame-time lookup, seeking, and the scrubber drawing."""

import sys
from bisect import bisect_right

import pygame

from .. import config
from ..config import px


def _rm():
    return sys.modules["vector_drift.scenes.replay"]


def draw_text(*a, **k):
    """Late-bound so tests can monkeypatch ``scenes.replay.draw_text``."""
    return _rm().draw_text(*a, **k)


class ReplayTimelineMixin:

    @staticmethod
    def _make_frame_times(frames):
        times = [float(frame.t) for frame in frames]
        if all(later > earlier for earlier, later in zip(times, times[1:])):
            return times
        start = times[0] if times else 0.0
        return [start + i / config.FPS for i in range(len(frames))]

    def _seek_index(self, index):
        frame = self.player.seek(index)
        if frame is not None and self._frame_times:
            self._playback_time = self._frame_times[self.player.index]
        return frame

    def _sync_index_to_time(self):
        if not self._frame_times:
            return
        self._playback_time = max(self._frame_times[0],
                                  min(self._frame_times[-1], self._playback_time))
        index = bisect_right(self._frame_times, self._playback_time) - 1
        self.player.seek(max(0, index))

    def _seek_time(self, fraction):
        """Seek playback to a 0..1 position along the timeline."""
        if not self._frame_times:
            return
        fraction = max(0.0, min(1.0, float(fraction)))
        start = self._frame_times[0]
        end = self._frame_times[-1]
        self._playback_time = start + (end - start) * fraction
        self._sync_index_to_time()
        self._sync_pickups_to_current()
        self.paused = True
        try:
            self.player.pause()
        except Exception:
            pass

    def seek_time(self, fraction):
        return self._seek_time(fraction)

    def seek_to(self, fraction):
        return self._seek_time(fraction)

    def _timeline_fraction(self):
        if not self._frame_times:
            return 0.0
        start = self._frame_times[0]
        end = self._frame_times[-1]
        if end <= start:
            return 0.0
        return (self._playback_time - start) / (end - start)

    def _timeline_hit(self, pos):
        rect = getattr(self, "timeline_rect", None)
        if rect is None:
            return False
        # Generous hit area around the bar.
        hit = rect.inflate(0, px(20))
        return hit.collidepoint(pos)

    def _draw_timeline(self, surface):
        rect = self.timeline_rect
        if not self._frame_times:
            # Empty track when there is nothing to seek.
            pygame.draw.rect(surface, config.PANEL_BG, rect, border_radius=px(3))
            return
        # Track background.
        pygame.draw.rect(surface, config.TEXT_DIM, rect, border_radius=px(3))
        # Filled portion up to the playhead.
        frac = max(0.0, min(1.0, self._timeline_fraction()))
        fill_w = max(1, int(rect.w * frac))
        fill_rect = pygame.Rect(rect.x, rect.y, fill_w, rect.h)
        pygame.draw.rect(surface, config.TRAIL, fill_rect, border_radius=px(3))
        # Playhead marker (a small circle slightly taller than the track).
        ph_x = rect.x + fill_w
        ph_y = rect.centery
        ph_r = max(px(5), rect.h * 1.6)
        pygame.draw.circle(surface, config.TEXT, (ph_x, ph_y), ph_r)
        pygame.draw.circle(surface, config.BG, (ph_x, ph_y), max(1, ph_r - px(2)))
        # Time labels at both ends.
        start_t = self._frame_times[0]
        end_t = self._frame_times[-1]
        draw_text(surface, f"{start_t:.1f}s", (rect.x, rect.bottom + px(4)), 12, config.TEXT_DIM, anchor="midleft")
        draw_text(surface, f"{end_t:.1f}s", (rect.right, rect.bottom + px(4)), 12, config.TEXT_DIM, anchor="midright")
        cur_t = self._playback_time
        draw_text(surface, f"{cur_t:.1f}s", (ph_x, rect.bottom + px(18)), 12, config.TEXT, anchor="center")
