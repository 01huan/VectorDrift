"""Replay scene drawing: field, section, ship, trail, and telemetry."""

import math
import sys

import pygame

from .. import config, sprites
from ..config import px
from . import ability_effects as afx
from .replay_data import START_MARKER_RADIUS_M, trail_strokes


def _rm():
    return sys.modules["vector_drift.scenes.replay"]


def draw_text(*a, **k):
    """Late-bound so tests can monkeypatch ``scenes.replay.draw_text``."""
    return _rm().draw_text(*a, **k)


class ReplayRenderMixin:

    def _current_frame(self):
        frames = self.player.record.frames if self.player.record else []
        if not frames:
            return None
        index = max(0, min(len(frames) - 1, self.player.index))
        if index >= len(frames) - 1:
            return frames[index].to_dict()

        first, second = frames[index], frames[index + 1]
        first_time, second_time = self._frame_times[index:index + 2]
        if second_time <= first_time:
            return first.to_dict()
        fraction = (self._playback_time - first_time) / (second_time - first_time)
        if second.warp and fraction < 1.0:
            return first.to_dict()
        fraction = max(0.0, min(1.0, fraction))
        frame = {
            key: float(getattr(first, key)) +
                 (float(getattr(second, key)) - float(getattr(first, key))) * fraction
            for key in ("t", "x", "y", "vx", "vy", "fx", "fy")
        }
        if second.warp and fraction >= 1.0:
            frame["warp"] = True
        return frame

    @staticmethod
    def _frame_xy(frame):
        if hasattr(frame, "x"):
            return float(frame.x), float(frame.y)
        return float(frame.get("x", 0.0)), float(frame.get("y", 0.0))

    @staticmethod
    def _frame_val(frame, key, default=0.0):
        if hasattr(frame, key):
            try:
                return float(getattr(frame, key))
            except (TypeError, ValueError):
                return default
        return float(frame.get(key, default) if isinstance(frame, dict) else default)

    def _checkpoint_taken(self):
        """The launch reached its checkpoint and playback is at that moment."""
        if "REACHED" not in str(self.records[self.index].get("outcome", "")):
            return False
        frames = self.player.record.frames if self.player.record else []
        return bool(frames) and self.player.index >= len(frames) - 1

    def _level_label(self, rec):
        """'9 · section 2/2' on multi-section levels, just the level number otherwise."""
        label = str(rec.get("level_id"))
        if self._section_total > 1:
            label += f" · section {self._section_index + 1}/{self._section_total}"
        return label

    def _draw_ability_fx(self, surface, frame):
        """The flashes of the abilities that were used, at the playback spot.

        The effects are rebuilt from the recorded events every frame, so the
        playback shows exactly the flashes that belong to its position (and
        seeking back and forth shows them again).
        """
        events = getattr(self, "_ability_events", None)
        if not events:
            return
        try:
            now = float(frame.get("t", 0.0)) if isinstance(frame, dict) else 0.0
        except (TypeError, ValueError):
            now = 0.0
        effects = afx.effects_at(events, now)
        if not effects:
            return
        try:
            afx.draw_effects(surface, effects, self._viewport.to_screen,
                             self._viewport.length, self._t)
        except (pygame.error, TypeError, ValueError, OverflowError, MemoryError):
            pass

    def draw(self, surface):
        surface.fill(config.BG)
        if not self.records or self._viewport is None:
            draw_text(surface, "REPLAYS", (config.WINDOW_W // 2, px(40)), 34, config.TEXT, kind="bold", anchor="center")
            draw_text(surface, "No launch records saved yet.", (config.WINDOW_W // 2, config.WINDOW_H // 2), 20, config.TEXT_DIM, anchor="center")
            self.back_button.draw(surface)
            return

        plot = pygame.Rect(self._viewport.rect)
        surface.blit(self._bg, plot.topleft)
        if self._field_layer is not None:
            surface.blit(self._field_layer, plot.topleft)
        surface.blit(self._labels, plot.topleft)

        prev_clip = surface.get_clip()
        try:
            surface.set_clip(plot)
        except pygame.error:
            prev_clip = None

        # Same look as the game: from section 2 on the start is the checkpoint
        # just reached; every target but the last section's is a checkpoint.
        launch = self._viewport.to_screen(*self._start)
        if self._section_index > 0:
            sprites.draw_checkpoint(surface, launch, self._viewport.length(self._start_checkpoint_radius),
                                    self._t, self._ship)
        else:
            sprites.draw_start_marker(surface, launch, self._viewport.length(START_MARKER_RADIUS_M), self._t)
        target = self._viewport.to_screen(*self._target_center)
        target_r = self._viewport.length(self._target_radius)
        if self._section_index < self._section_total - 1:
            sprites.draw_checkpoint(surface, target, target_r, self._t, self._ship)
            if not self._checkpoint_taken():
                sprites.draw_checkpoint_life(surface, target, target_r, self._t, self._ship)
        else:
            sprites.draw_target(surface, target, target_r, self._t)

        self._sync_pickups_to_current()

        for obstacle in self._obstacles:
            sprites.draw_obstacle(surface, self._viewport.to_screen(*obstacle.center),
                                  self._viewport.length(obstacle.radius), self._t,
                                  kind=getattr(obstacle, "kind", "bumper"),
                                  seed=(obstacle.center, obstacle.radius))

        for pickup in self._pickups:
            if getattr(pickup, "consumed", False):
                continue
            sprites.draw_pickup(surface, self._viewport.to_screen(*pickup.center),
                                self._viewport.length(pickup.radius), self._t,
                                kind=pickup.kind)

        for i, hole in enumerate(self._holes, start=1):
            try:
                bc = hole.black_center if hasattr(hole, "black_center") else hole[0]
                wc = hole.white_center if hasattr(hole, "white_center") else hole[1]
                r = getattr(hole, "radius", 0.5)
                sprites.draw_hole(surface, self._viewport.to_screen(*bc), self._viewport.length(r),
                                  self._t, kind="black", pair_index=i)
                sprites.draw_hole(surface, self._viewport.to_screen(*wc), self._viewport.length(r),
                                  self._t, kind="white", pair_index=i)
                for center, color in ((bc, config.TEXT), (wc, config.OUTLINE)):
                    sp = self._viewport.to_screen(*center)
                    draw_text(surface, str(i), sp, 12, color, kind="bold", anchor="center")
            except Exception:
                pass

        frames = self.player.record.frames if self.player.record else []
        end = max(0, min(self.player.index + 1, len(frames)))
        trail = list(frames[:end])
        cur = self._current_frame() or {}
        if (cur and self.player.index < len(frames) - 1
                and self._playback_time > self._frame_times[self.player.index]
                and not (frames[self.player.index + 1].warp
                         and cur.get("x") == frames[self.player.index].x
                         and cur.get("y") == frames[self.player.index].y)):
            trail.append(cur)
        for stroke in trail_strokes(trail):
            if len(stroke) < 2:
                continue
            pts = [self._viewport.to_screen(*self._frame_xy(f)) for f in stroke]
            try:
                pygame.draw.lines(surface, config.TRAIL, False, pts, max(1, px(2)))
            except pygame.error:
                pass

        if cur:
            x, y = cur.get("x", 0.0), cur.get("y", 0.0)
            vx, vy = cur.get("vx", 0.0), cur.get("vy", 0.0)
            fx, fy = cur.get("fx", 0.0), cur.get("fy", 0.0)
            ship_pos = self._viewport.to_screen(x, y)
            if math.hypot(vx, vy) > 1e-6:
                heading = math.atan2(vy, vx)
            elif math.hypot(fx, fy) > 1e-9:
                heading = math.atan2(fy, fx)
            else:
                heading = 0.0
            try:
                sprites.draw_vector(surface, ship_pos, (vx, vy), config.VELOCITY_VEC)
                sprites.draw_vector(surface, ship_pos, (fx, fy), config.FORCE_VEC)
            except pygame.error:
                pass
            sprites.draw_ship(surface, ship_pos, heading, self._viewport.length(self._ship.length), self._ship)
            self._draw_ability_fx(surface, cur)

        if prev_clip is not None:
            try:
                surface.set_clip(prev_clip)
            except pygame.error:
                pass

        draw_text(surface, "REPLAY", (config.WINDOW_W // 2, px(26)), 30, config.TEXT, kind="bold", anchor="center")
        rec = self.records[self.index]
        info = [
            ("Record", f"{self.index + 1} / {len(self.records)}"),
            ("Level", self._level_label(rec)),
            ("Ship", str(rec.get("ship_id"))),
            ("Outcome", str(rec.get("outcome"))),
            ("Speed", f"{self.player.speed:.1f}x"),
        ]
        y = px(70)
        for label, value in info:
            draw_text(surface, label, (px(40), y), 16, config.TEXT_DIM, anchor="midleft")
            draw_text(surface, value, (px(220), y), 16, config.TEXT, anchor="midleft")
            y += px(26)

        ty = y + px(18)
        draw_text(surface, "Time", (px(40), ty), 16, config.TEXT_DIM, anchor="midleft")
        draw_text(surface, f"{cur.get('t', 0):.2f}s", (px(220), ty), 16, config.TEXT, anchor="midleft")
        draw_text(surface, "Position", (px(40), ty + px(24)), 16, config.TEXT_DIM, anchor="midleft")
        draw_text(surface, f"({cur.get('x', 0):.2f}, {cur.get('y', 0):.2f}) m", (px(220), ty + px(24)), 16, config.TEXT, anchor="midleft")
        draw_text(surface, "Velocity", (px(40), ty + px(48)), 16, config.TEXT_DIM, anchor="midleft")
        draw_text(surface, f"({cur.get('vx', 0):.2f}, {cur.get('vy', 0):.2f}) m/s", (px(220), ty + px(48)), 16, config.TEXT, anchor="midleft")
        draw_text(surface, "Force formula", (px(40), ty + px(72)), 16, config.TEXT_DIM, anchor="midleft")
        fx_text = rec.get("fx_text", "")
        fy_text = rec.get("fy_text", "")
        if fx_text or fy_text:
            draw_text(surface, f"({fx_text}, {fy_text})", (px(220), ty + px(72)), 16, config.TEXT, anchor="midleft")
        draw_text(surface, "Force", (px(40), ty + px(96)), 16, config.TEXT_DIM, anchor="midleft")
        draw_text(surface, f"({cur.get('fx', 0):.2f}, {cur.get('fy', 0):.2f}) N", (px(220), ty + px(96)), 16, config.TEXT, anchor="midleft")

        draw_text(surface, "Space: play/pause   Left/Right: step   Play resumes from current position",
                  (config.WINDOW_W // 2, config.WINDOW_H - px(30)), 14, config.TEXT_FAINT, anchor="center")

        # Bottom timeline: track + playhead + time labels.
        self._draw_timeline(surface)

        self.back_button.draw(surface)
        self.prev_button.draw(surface)
        self.next_button.draw(surface)
        self.play_button.draw(surface)
        self.pause_button.draw(surface)
        self.speed_btn_decrease.draw(surface)
        self.speed_btn_increase.draw(surface)
