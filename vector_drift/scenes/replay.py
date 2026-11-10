"""Replay viewer: fully re-renders a stored launch (ship, obstacles, pickups, field, trail)."""

import pygame

from .. import config, render
from ..config import px
from ..coords import Viewport
from ..data import (SHIPS, custom_level_from_snapshot, get_level, section_count,
                    section_level)
from ..physics import ForceField
from ..pickups import PickupState
from ..expr_parser import diagnose_expression
# draw_text is kept importable here: the render/timeline mixins late-bind it
# through this module so tests can monkeypatch scenes.replay.draw_text.
from ..ui import Button, draw_text
from .base import Scene
from ..replay import ReplayPlayer, section_index_from
from .replay_camera import ReplayCameraMixin
# Re-exported for callers/tests that historically imported these names here.
from .replay_data import (JUMP_SLACK_M, START_MARKER_RADIUS_M, _get, _is_jump,
                          trail_strokes)
from .replay_render import ReplayRenderMixin
from .replay_timeline import ReplayTimelineMixin


class ReplayScene(ReplayTimelineMixin, ReplayCameraMixin, ReplayRenderMixin, Scene):
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
