"""Main menu: Start / Quit over an animated starfield."""

import math

import pygame

from .. import config, render, sprites
from ..config import px
from ..coords import Viewport
from ..data import SHIPS
from ..physics import ForceField
from ..ui import Button, draw_text
from .base import Scene


class MenuScene(Scene):
    def __init__(self, manager):
        super().__init__(manager)
        size = (config.WINDOW_W, config.WINDOW_H)
        self.background = render.make_space_background(size, seed=3, star_count=300)
        self._make_swirl()
        cx = config.WINDOW_W // 2
        self.start_button = Button((cx - px(110), px(400), px(220), px(54)), "Start", font_size=22)
        self.quit_button = Button((cx - px(110), px(470), px(220), px(54)), "Quit", style="plain", font_size=22)
        self.t = 0.0

    def _make_swirl(self):
        """Faint decorative rotational field behind the title."""
        vp = Viewport((0, 0, config.WINDOW_W, config.WINDOW_H), scale=64 * config.UI_SCALE)
        layer, _ = render.make_field_layer(vp, ForceField(b=-0.6, d=0.6, a=-0.08, e=-0.08))
        layer.set_alpha(90)
        self.swirl = layer

    def handle_event(self, event):
        if self.start_button.handle_event(event) == "click" or (
                event.type == pygame.KEYDOWN and event.key == pygame.K_RETURN):
            self.audio.play("click")
            from .levels import LevelSelectScene
            self.manager.switch(LevelSelectScene(self.manager))
        elif self.quit_button.handle_event(event) == "click":
            self.audio.play("click")
            self.manager.quit()

    def update(self, dt):
        self.t += dt

    def draw(self, surface):
        surface.blit(self.background, (0, 0))
        surface.blit(self.swirl, (0, 0))
        sprites.draw_target(surface, (px(150), config.WINDOW_H - px(90)), px(120), self.t)

        # A ship drifting along an ellipse, nose along its velocity.
        a, b, w = px(430), px(230), 0.35
        cx, cy = config.WINDOW_W / 2, config.WINDOW_H / 2 + px(10)
        th = self.t * w
        pos = (cx + a * math.cos(th), cy - b * math.sin(th))
        heading = math.atan2(b * math.cos(th), -a * math.sin(th))
        sprites.draw_ship(surface, pos, heading, px(64), SHIPS["drifter"])

        draw_text(surface, "VECTOR DRIFT", (config.WINDOW_W // 2 + px(4), px(195)), 76, config.OUTLINE,
                  kind="bold", anchor="center")
        draw_text(surface, "VECTOR DRIFT", (config.WINDOW_W // 2, px(190)), 76, config.TEXT,
                  kind="bold", anchor="center")
        draw_text(surface, "Design a force field. Let physics fly the ship.",
                  (config.WINDOW_W // 2, px(262)), 22, config.ACCENT, anchor="center")
        self.start_button.draw(surface)
        self.quit_button.draw(surface)
        draw_text(surface, "Enter: launch   Tab: switch line   Esc: abort   Ctrl+M: mute",
                  (config.WINDOW_W // 2, config.WINDOW_H - px(26)), 14, config.TEXT_FAINT, anchor="center")
