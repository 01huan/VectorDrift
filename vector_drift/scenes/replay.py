"""Replay viewer: fully re-renders a stored launch (ship, obstacles, pickups, field, trail)."""

import math
from bisect import bisect_right

import pygame

from .. import config, render, sprites
from ..config import px
from ..coords import Viewport
from ..data import (SHIPS, custom_level_from_snapshot, get_level, section_count,
                    section_level)
from ..physics import ForceField
from ..pickups import PickupState
from ..expr_parser import diagnose_expression
from ..ui import Button, draw_text
from .base import Scene
from ..replay import ReplayPlayer, section_index_from

START_MARKER_RADIUS_M = 0.45
# Records saved before frames carried "warp" still break the trail where the
# ship jumps much farther in one frame than its speed allows (a teleport).
JUMP_SLACK_M = 0.5


def _get(frame, key):
    if isinstance(frame, dict):
        return frame.get(key, 0.0)
    return getattr(frame, key, 0.0)


def _is_jump(a, b):
    """Did the ship get from frame a to frame b without flying there?"""
    try:
        dist = math.hypot(float(_get(b, "x")) - float(_get(a, "x")), float(_get(b, "y")) - float(_get(a, "y")))
        speed = max(math.hypot(float(_get(a, "vx")), float(_get(a, "vy"))),
                    math.hypot(float(_get(b, "vx")), float(_get(b, "vy"))))
        dt = max(float(_get(b, "t")) - float(_get(a, "t")), 1.0 / config.FPS)
    except (TypeError, ValueError, OverflowError):
        return False
    return dist > JUMP_SLACK_M + 3.0 * speed * dt


def trail_strokes(frames):
    """Split frames into trail strokes: a teleport (warp) starts a new one."""
    strokes = []
    for frame in frames:
        warp = frame.get("warp") is True if isinstance(frame, dict) else getattr(frame, "warp", False)
        if not strokes or warp or _is_jump(strokes[-1][-1], frame):
            strokes.append([frame])
        else:
            strokes[-1].append(frame)
    return strokes


class ReplayScene(Scene):
    music = "menu"

    def __init__(self, manager):
        super().__init__(manager)
        self.records = list(getattr(self.session, "replays", None) or [])
        self.index = 0 if self.records else -1
        self.player = ReplayPlayer(self.records[0] if self.records else None)
        self.paused = True
        self._frame_times = []
        self._playback_time = 0.0
        self._t = 0.0

        self._level = None
        self._viewport = None
        self._bg = None
        self._field_layer = None
        self._labels = None
        self._ship = None
        self._max_force = 0.0
        self._obstacles = ()
        self._pickups = ()
        self._holes = ()
        self._target_center = (0.0, 0.0)
        self._target_radius = 0.5
        self._start = (0.0, 0.0)
        self._section_index = 0         # which screen of the level the launch flew
        self._section_total = 1
        self._start_checkpoint_radius = 0.0

        # Unbound/camera zoom state (mirrors GameScene)
        self._unbound = False
        self._camera_ease_s = 0.1
        self._camera_margin_m = 1.0

        self.back_button = Button((px(40), px(10), px(120), px(40)), "Back", style="plain", font_size=16)
        button_w = px(100)
        button_h = px(40)
        gap_x = px(10)
        gap_y = px(10)
        start_x = px(40)
        start_y = config.WINDOW_H - px(200)
        self.prev_button = Button((start_x, start_y, button_w, button_h), "Prev", style="plain", font_size=16)
        self.next_button = Button((start_x + button_w + gap_x, start_y, button_w, button_h), "Next", style="plain", font_size=16)
        self.play_button = Button((start_x, start_y + button_h + gap_y, button_w, button_h), "Play", style="primary", font_size=16)
        self.pause_button = Button((start_x + button_w + gap_x, start_y + button_h + gap_y, button_w, button_h), "Pause", style="plain", font_size=16)
        self.speed_btn_decrease = Button((start_x, start_y - button_h - gap_y, button_w, button_h), "slow down", style="plain", font_size=16)
        self.speed_btn_increase = Button((start_x + button_w + gap_x, start_y - button_h - gap_y, button_w, button_h), "speed up", style="plain", font_size=16)

        # Bottom timeline (scrubber) for manually seeking the playback position.
        tl_x = px(40)
        tl_y = config.WINDOW_H - px(62)
        tl_w = config.WINDOW_W - px(80)
        tl_h = px(12)
        self.timeline_rect = pygame.Rect(tl_x, tl_y, tl_w, tl_h)
        self.slider_rect = self.timeline_rect
        self.seekbar_rect = self.timeline_rect
        self.scrubber_rect = self.timeline_rect
        self.time_slider_rect = self.timeline_rect
        self._dragging_timeline = False
        self._timeline_dragging = False

        self._load(self.index)

    def _load(self, idx):
        if not self.records:
            self.index = -1
            self.player = ReplayPlayer(None)
            self._clear_level()
            return
        self.index = max(0, min(len(self.records) - 1, idx))
        rec = self.records[self.index]
        self.player = ReplayPlayer(rec)
        self.player.seek(0)
        frames = self.player.record.frames if self.player.record else []
        self._frame_times = self._make_frame_times(frames)
        self._playback_time = self._frame_times[0] if self._frame_times else 0.0
        self.paused = True
        self._unbound = False  # Reset unbound state for new recording
        self._setup_level_from_record(rec)
        self._sync_pickups_to_current()

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

    def _clear_level(self):
        self._level = None
        self._viewport = Viewport()
        self._bg = render.make_plot_background(self._viewport)
        self._field_layer = None
        self._labels = render.make_plot_labels(self._viewport)
        self._ship = SHIPS.get("ship01")
        self._obstacles = ()
        self._pickups = ()
        self._holes = ()
        self._target_center = (0.0, 0.0)
        self._target_radius = 0.5
        self._start = (0.0, 0.0)
        self._section_index = 0
        self._section_total = 1
        self._start_checkpoint_radius = 0.0
        self._unbound = False

    def _setup_level_from_record(self, rec):
        level_id = int(rec.get("level_id", 1))
        seed = rec.get("seed")
        try:
            seed = int(seed) if seed is not None else None
        except (TypeError, ValueError):
            seed = None
        snapshot = rec.get("level_snapshot")
        if isinstance(snapshot, dict):
            full = custom_level_from_snapshot(snapshot)
        elif seed is not None:
            full = get_level(level_id, seed=seed)
        else:
            full = get_level(level_id)
        # Multi-section levels: rebuild the screen this launch flew. A missing,
        # bad or out-of-range index (old saves, edited levels) means section 1.
        self._section_total = section_count(full)
        index = section_index_from(rec.get("section_index"))
        self._section_index = index if index < self._section_total else 0
        self._level = section_level(full, self._section_index)
        self._start_checkpoint_radius = (full.sections[self._section_index - 1].target_radius
                                         if self._section_index > 0 else 0.0)

        self._viewport = Viewport()
        self._bg = render.make_plot_background(self._viewport)
        self._labels = render.make_plot_labels(self._viewport)

        fx_text = str(rec.get("fx_text", "") or "")
        fy_text = str(rec.get("fy_text", "") or "")
        fx, fx_err, _fx_pos = diagnose_expression(fx_text)
        fy, fy_err, _fy_pos = diagnose_expression(fy_text)
        self._field_layer = None
        self._max_force = 0.0
        if fx is not None and fy is not None:
            try:
                field = ForceField.from_exprs(fx, fy)
                self._field_layer, self._max_force = render.make_field_layer(self._viewport, field)
            except Exception:
                self._field_layer = None

        self._ship = SHIPS.get(rec.get("ship_id"), SHIPS["ship01"])
        raw_pickups = getattr(self._level, "pickups", ()) or ()
        self._pickups = []
        for p in raw_pickups:
            if isinstance(p, PickupState):
                self._pickups.append(p)
            else:
                try:
                    self._pickups.append(PickupState.from_spec(p))
                except Exception:
                    self._pickups.append(p)
        self._pickups = tuple(self._pickups)
        self._obstacles = getattr(self._level, "obstacles", ()) or ()
        self._holes = list(getattr(self._level, "holes", ()) or ())
        self._target_center = self._level.target_center
        self._target_radius = self._level.target_radius
        self._start = self._level.start

        # Reproduce the state the level was in when this launch happened:
        # pickups already consumed in previous runs and obstacles already
        # destroyed (e.g. by an earlier shockwave) must not reappear.
        self._apply_initial_state_from_record(rec)

        self._base_pickups = tuple(self._pickups)
        self._base_obstacles = tuple(self._obstacles)
    
        unbound_activated = self._apply_pickup_events_from_record(rec)
        if unbound_activated:
            self._unbound = True

    def _apply_pickup_events_from_record(self, rec):
        events = None
        if isinstance(rec, dict):
            events = rec.get("pickup_events")
        else:
            events = getattr(rec, "pickup_events", None)
        if not events:
            return False
        unbound_activated = False
        for ev in events:
            if not isinstance(ev, dict):
                continue
            kind = ev.get("kind")
            # Unbound: mark that unbound was activated during this flight.
            if kind == "unbound":
                unbound_activated = True
        return unbound_activated
        return unbound_activated

    def _apply_initial_state_from_record(self, rec):
        # Mark pickups that were already consumed before this launch (from
        # previous runs) so they do not render / re-trigger.
        consumed_centers = set()
        try:
            raw = rec.get("consumed_pickups") if isinstance(rec, dict) else getattr(rec, "consumed_pickups", None)
            if raw:
                consumed_centers = {tuple(c) for c in raw}
        except Exception:
            consumed_centers = set()
        pickups = list(self._pickups)
        for p in pickups:
            try:
                if tuple(getattr(p, "center", ())) in consumed_centers:
                    p.consumed = True
            except Exception:
                pass
        self._pickups = tuple(pickups)

        # Keep only obstacles that survived up to this launch (drop those
        # already destroyed by an earlier shockwave).
        try:
            raw = rec.get("obstacle_centers") if isinstance(rec, dict) else getattr(rec, "obstacle_centers", None)
        except Exception:
            raw = None
        if raw is not None:
            try:
                keep = {tuple(c) for c in raw}
                self._obstacles = tuple(o for o in self._obstacles
                                       if tuple(getattr(o, "center", ())) in keep)
            except Exception:
                pass

    def _sync_pickups_to_current(self):
        try:
            self._pickups = tuple(PickupState(p.center, p.radius, p.kind) for p in self._base_pickups)
            self._obstacles = tuple(self._base_obstacles)
        except Exception:
            pass
        # Restore pre-consumed / pre-destroyed state before replaying this flight.
        try:
            rec = self.records[self.index] if 0 <= self.index < len(self.records) else None
            self._apply_initial_state_from_record(rec)
        except Exception:
            pass
        frames = []
        if self.player is not None and self.player.record is not None:
            frames = self.player.record.frames or []
        end = 0
        try:
            end = max(0, min(self.player.index + 1, len(frames)))
        except Exception:
            end = 0
        prev = None
        for i in range(end):
            f = frames[i]
            try:
                x = f.x if hasattr(f, "x") else f.get("x", 0.0)
                y = f.y if hasattr(f, "y") else f.get("y", 0.0)
            except Exception:
                x, y = 0.0, 0.0
            xy = (float(x), float(y))
            if prev is not None:
                self._consume_segment(prev, xy)
            prev = xy
        # Re-apply recorded events (idempotent) for shockwave, unbound, etc.
        try:
            rec = self.records[self.index] if 0 <= self.index < len(self.records) else None
            unbound_activated = self._apply_pickup_events_from_record(rec)
            if unbound_activated:
                self._unbound = True
        except Exception:
            pass
        except Exception:
            pass

    def _consume_segment(self, p0, p1):
        try:
            from ..pickups import check_pickups_segment

            class _Ctx:
                def __init__(self, obstacles):
                    self.obstacle_specs = list(obstacles)
                    self.obstacles = tuple(obstacles)
                    self.hull_radius = 0.0

            ctx = _Ctx(self._obstacles)
            check_pickups_segment(self._pickups, p0, p1, 0.0, ctx=ctx)
            if getattr(ctx, "obstacle_specs", None) is not None:
                self._obstacles = tuple(ctx.obstacle_specs)
        except Exception:
            pass

    def handle_event(self, event):
        if self.back_button.handle_event(event) == "click":
            self.audio.play("click")
            from .menu import MenuScene
            self.manager.switch(MenuScene(self.manager))
            return
        if self.prev_button.handle_event(event) == "click":
            self.player.pause()
            self.paused = True
            self._load(self.index - 1)
        if self.next_button.handle_event(event) == "click":
            self.player.pause()
            self.paused = True
            self._load(self.index + 1)
        if self.play_button.handle_event(event) == "click":
            self.audio.play("click")
            if self.records:
                frames = self.player.record.frames if self.player.record else []
                if frames and self.player.index >= len(frames) - 1:
                    self._seek_index(0)
                self.paused = False
        if self.pause_button.handle_event(event) == "click":
            self.audio.play("click")
            self.player.pause()
            self.paused = True
        if self.speed_btn_decrease.handle_event(event) == "click":
            self.audio.play("click")
            self.player.decrease_speed()
        if self.speed_btn_increase.handle_event(event) == "click":
            self.audio.play("click")
            self.player.increase_speed()
        # Bottom timeline (scrubber): click / drag to seek playback position.
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self._timeline_hit(getattr(event, "pos", None)):
                self._dragging_timeline = True
                self._timeline_dragging = True
                rect = self.timeline_rect
                frac = (event.pos[0] - rect.x) / max(1, rect.w)
                self._seek_time(frac)
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self._dragging_timeline = False
            self._timeline_dragging = False
        if event.type == pygame.MOUSEMOTION:
            if self._dragging_timeline or self._timeline_dragging:
                rect = self.timeline_rect
                frac = (event.pos[0] - rect.x) / max(1, rect.w)
                self._seek_time(frac)
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                from .menu import MenuScene
                self.manager.switch(MenuScene(self.manager))
            elif event.key == pygame.K_LEFT:
                self.player.pause()
                self.paused = True
                self.player.step(-1)
                self._seek_index(self.player.index)
            elif event.key == pygame.K_RIGHT:
                self.player.pause()
                self.paused = True
                self.player.step(1)
                self._seek_index(self.player.index)
            elif event.key == pygame.K_SPACE:
                if not self.records:
                    return
                if self.paused:
                    frames = self.player.record.frames if self.player.record else []
                    if frames and self.player.index >= len(frames) - 1:
                        self._seek_index(0)
                    self.paused = False
                else:
                    self.player.pause()
                    self.paused = True

    def update(self, dt):
        self._t += dt * self.player.speed
        if self.paused or not self.records:
            self._update_camera(dt)  # Update camera even when paused (for manual stepping)
            return
        self._playback_time += dt * self.player.speed
        self._sync_index_to_time()
        if self._frame_times and self._playback_time >= self._frame_times[-1]:
            self.player.pause()
            self.paused = True
        self._update_camera(dt)

    def _camera_target(self):
        """(target_zoom, keep_ship_zoom) for the current frame.

        Mirrors GameScene._camera_target: zooms out while unbound ship is off-map.
        """
        cur = self.player.frame
        if cur is None or not self._unbound:
            return 1.0, 1.0
        pos = (cur.get("x", 0.0), cur.get("y", 0.0))
        # Replay uses the same bounds as the level
        bounds = getattr(self._level, "bounds", None)
        if bounds is None:
            bounds = (config.WORLD_HALF_W, config.WORLD_HALF_H)
        from ..coords import fit_zoom
        return (fit_zoom(pos, bounds, margin=self._camera_margin_m),
                fit_zoom(pos, bounds, margin=0.5 * self._ship.length))

    def _update_camera(self, dt):
        """Ease the camera zoom toward its target (smooth out and back in).

        Mirrors GameScene._update_camera.
        """
        if self._viewport is None:
            return
        target, keep_ship = self._camera_target()
        zoom = self._viewport.zoom
        if zoom == target:
            return
        import math
        zoom += (target - zoom) * (1.0 - math.exp(-dt / self._camera_ease_s))
        zoom = min(zoom, keep_ship)
        self._viewport.zoom = target if abs(target - zoom) < 1e-3 else zoom

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
