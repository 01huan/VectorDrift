"""Replay viewer for stored launch records."""

import pygame

from .. import config
from ..config import px
from ..ui import Button, draw_text
from .base import Scene
from ..replay import ReplayPlayer


class ReplayScene(Scene):
    music = "menu"

    def __init__(self, manager):
        super().__init__(manager)
        self.records = list(getattr(self.session, "replays", None) or [])
        self.index = 0 if self.records else -1
        self.player = ReplayPlayer(self.records[0] if self.records else None)
        self.paused = False
        self._acc = 0.0

        cx = config.WINDOW_W // 2
        self.back_button = Button((px(40), px(40), px(120), px(40)), "Back", style="plain", font_size=16)
        self.prev_button = Button((cx - px(260), config.WINDOW_H - px(90), px(100), px(40)), "Prev", style="plain", font_size=16)
        self.next_button = Button((cx - px(150), config.WINDOW_H - px(90), px(100), px(40)), "Next", style="plain", font_size=16)
        self.play_button = Button((cx + px(50), config.WINDOW_H - px(90), px(100), px(40)), "Play", style="primary", font_size=16)
        self.pause_button = Button((cx + px(160), config.WINDOW_H - px(90), px(100), px(40)), "Pause", style="plain", font_size=16)

    def _load(self, idx):
        if not self.records:
            self.player = ReplayPlayer(None)
            self.index = -1
            return
        self.index = max(0, min(len(self.records) - 1, idx))
        self.player = ReplayPlayer(self.records[self.index])
        self.player.seek(0)

    def handle_event(self, event):
        if self.back_button.handle_event(event) == "click":
            self.audio.play("click")
            from .menu import MenuScene
            self.manager.switch(MenuScene(self.manager))
            return
        if self.prev_button.handle_event(event) == "click":
            self._load(self.index - 1)
        if self.next_button.handle_event(event) == "click":
            self._load(self.index + 1)
        if self.play_button.handle_event(event) == "click":
            self.player.seek(0)
            self.player.play()
            self.paused = False
            self._acc = 0.0
        if self.pause_button.handle_event(event) == "click":
            self.player.pause()
            self.paused = True
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_LEFT:
                self.player.step(-1)
            elif event.key == pygame.K_RIGHT:
                self.player.step(1)
            elif event.key == pygame.K_SPACE:
                if self.paused:
                    if self.player.index >= len(self.player.record.frames or []) - 1:
                        self.player.seek(0)
                    self.player.play(); self.paused = False
                    self._acc = 0.0
                else:
                    self.player.pause(); self.paused = True
            elif event.key == pygame.K_ESCAPE:
                from .menu import MenuScene
                self.manager.switch(MenuScene(self.manager))

    def update(self, dt):
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

    def draw(self, surface):
        surface.fill(config.BG)
        draw_text(surface, "REPLAYS", (config.WINDOW_W // 2, px(40)), 34, config.TEXT, kind="bold", anchor="center")
        if not self.records:
            draw_text(surface, "No launch records saved yet.", (config.WINDOW_W // 2, config.WINDOW_H // 2), 20, config.TEXT_DIM, anchor="center")
        else:
            rec = self.records[self.index]
            lines = [
                ("Record", f"{self.index + 1} / {len(self.records)}"),
                ("Level", str(rec.get("level_id"))),
                ("Ship", str(rec.get("ship_id"))),
                ("Outcome", str(rec.get("outcome"))),
            ]
            y = px(120)
            for label, value in lines:
                draw_text(surface, label, (px(80), y), 16, config.TEXT_DIM, anchor="midleft")
                draw_text(surface, value, (px(260), y), 16, config.TEXT, anchor="midleft")
                y += px(26)
            cur = self.player.current() or {}
            draw_text(surface, "Time", (px(80), y + px(20)), 16, config.TEXT_DIM, anchor="midleft")
            draw_text(surface, f"{cur.get('t', 0):.2f}s", (px(260), y + px(20)), 16, config.TEXT, anchor="midleft")
            draw_text(surface, "Position", (px(80), y + px(46)), 16, config.TEXT_DIM, anchor="midleft")
            draw_text(surface, f"({cur.get('x',0):.2f}, {cur.get('y',0):.2f})", (px(260), y + px(46)), 16, config.TEXT, anchor="midleft")
            draw_text(surface, "Velocity", (px(80), y + px(72)), 16, config.TEXT_DIM, anchor="midleft")
            draw_text(surface, f"({cur.get('vx',0):.2f}, {cur.get('vy',0):.2f})", (px(260), y + px(72)), 16, config.TEXT, anchor="midleft")
            draw_text(surface, "Force", (px(80), y + px(98)), 16, config.TEXT_DIM, anchor="midleft")
            draw_text(surface, f"({cur.get('fx',0):.2f}, {cur.get('fy',0):.2f})", (px(260), y + px(98)), 16, config.TEXT, anchor="midleft")
            draw_text(surface, "Space: play/pause  Left/Right: step", (config.WINDOW_W // 2, config.WINDOW_H - px(130)), 14, config.TEXT_FAINT, anchor="center")
        for b in (self.back_button, self.prev_button, self.next_button, self.play_button, self.pause_button):
            b.draw(surface)
