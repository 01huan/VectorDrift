"""Replay viewer: fully re-renders a stored launch (ship, obstacles, pickups, field, trail)."""

import math

import pygame

from .. import config, render, sprites
from ..config import px
from ..coords import Viewport
from ..data import SHIPS, get_level
from ..physics import ForceField
from ..expr_parser import diagnose_expression
from ..ui import Button, draw_text
from .base import Scene
from ..replay import ReplayPlayer

START_MARKER_RADIUS_M = 0.45


class ReplayScene(Scene):
    music = "menu"

    def __init__(self, manager):
        super().__init__(manager)
        self.records = list(getattr(self.session, "replays", None) or [])
        self.index = 0 if self.records else -1
        self.player = ReplayPlayer(self.records[0] if self.records else None)
        self.paused = True
        self._acc = 0.0
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

        cx = config.WINDOW_W // 2
        self.back_button = Button((px(40), px(40), px(120), px(40)), "Back", style="plain", font_size=16)
        self.prev_button = Button((cx - px(260), config.WINDOW_H - px(90), px(100), px(40)), "Prev", style="plain", font_size=16)
        self.next_button = Button((cx - px(150), config.WINDOW_H - px(90), px(100), px(40)), "Next", style="plain", font_size=16)
        self.play_button = Button((cx + px(50), config.WINDOW_H - px(90), px(100), px(40)), "Play", style="primary", font_size=16)
        self.pause_button = Button((cx + px(160), config.WINDOW_H - px(90), px(100), px(40)), "Pause", style="plain", font_size=16)

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
        self.paused = True
        self._acc = 0.0
        self._setup_level_from_record(rec)

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

    def _setup_level_from_record(self, rec):
        from ..story import get_level_story

        level_id = int(rec.get("level_id", 1))
        seed = rec.get("seed")
        try:
            seed = int(seed) if seed is not None else None
        except (TypeError, ValueError):
            seed = None
        if seed is not None:
            self._level = get_level(level_id, seed=seed)
        else:
            self._level = get_level(level_id)

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
        self._obstacles = getattr(self._level, "obstacles", ()) or ()
        self._pickups = getattr(self._level, "pickups", ()) or ()
        self._holes = list(getattr(self._level, "holes", ()) or ())
        self._target_center = self._level.target_center
        self._target_radius = self._level.target_radius
        self._start = self._level.start
        self._story_planet = None
        try:
            story = get_level_story(level_id)
            self._story_planet = story.planet if story else None
        except Exception:
            self._story_planet = None

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
                self.player.seek(0)
                self.paused = False
                self._acc = 0.0
        if self.pause_button.handle_event(event) == "click":
            self.audio.play("click")
            self.player.pause()
            self.paused = True
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                from .menu import MenuScene
                self.manager.switch(MenuScene(self.manager))
            elif event.key == pygame.K_LEFT:
                self.player.pause()
                self.paused = True
                self.player.step(-1)
            elif event.key == pygame.K_RIGHT:
                self.player.pause()
                self.paused = True
                self.player.step(1)
            elif event.key == pygame.K_SPACE:
                if not self.records:
                    return
                if self.paused:
                    self.player.seek(0)
                    self.paused = False
                    self._acc = 0.0
                else:
                    self.player.pause()
                    self.paused = True

    def update(self, dt):
        self._t += dt
        if self.paused or not self.records:
            return
        self._acc += dt
        frames = self.player.record.frames if self.player.record else []
        while self._acc >= 0.05 and self.player.index < len(frames) - 1:
            self._acc -= 0.05
            self.player.step(1)
        if self.player.index >= len(frames) - 1:
            self.player.pause()
            self.paused = True

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

        launch = self._viewport.to_screen(*self._start)
        sprites.draw_start_marker(surface, launch, self._viewport.length(START_MARKER_RADIUS_M), self._t)
        sprites.draw_target(surface, self._viewport.to_screen(*self._target_center),
                            self._viewport.length(self._target_radius), self._t,
                            planet=self._story_planet)

        for obstacle in self._obstacles:
            sprites.draw_obstacle(surface, self._viewport.to_screen(*obstacle.center),
                                  self._viewport.length(obstacle.radius), self._t,
                                  kind=getattr(obstacle, "kind", "bumper"),
                                  seed=(obstacle.center, obstacle.radius))

        for pickup in self._pickups:
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
        if end > 1:
            pts = [self._viewport.to_screen(*self._frame_xy(f)) for f in frames[:end]]
            try:
                pygame.draw.lines(surface, config.TRAIL, False, pts, max(1, px(2)))
            except pygame.error:
                pass

        cur = self.player.current() or {}
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
            ("Level", str(rec.get("level_id"))),
            ("Ship", str(rec.get("ship_id"))),
            ("Outcome", str(rec.get("outcome"))),
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
        draw_text(surface, "Force", (px(40), ty + px(72)), 16, config.TEXT_DIM, anchor="midleft")
        draw_text(surface, f"({cur.get('fx', 0):.2f}, {cur.get('fy', 0):.2f}) N", (px(220), ty + px(72)), 16, config.TEXT, anchor="midleft")

        draw_text(surface, "Space: play/pause   Left/Right: step   Play restarts from head",
                  (config.WINDOW_W // 2, config.WINDOW_H - px(30)), 14, config.TEXT_FAINT, anchor="center")

        self.back_button.draw(surface)
        self.prev_button.draw(surface)
        self.next_button.draw(surface)
        self.play_button.draw(surface)
        self.pause_button.draw(surface)

