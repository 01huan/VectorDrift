"""Level-failed screen: Retry Level (keeps formulas) / Levels / Main Menu."""

import pygame

from .. import config
from ..config import px
from .base import Scene, draw_overlay_card, result_buttons


class FailScene(Scene):
    def __init__(self, manager, background=None):
        super().__init__(manager)
        self.background = background
        self.retry_button, self.levels_button, self.menu_button = result_buttons("Retry Level")
        for b in (self.retry_button, self.levels_button, self.menu_button):
            b.rect.y = config.WINDOW_H // 2 + px(50)

    def handle_event(self, event):
        if self.retry_button.handle_event(event) == "click" or (
                event.type == pygame.KEYDOWN and event.key == pygame.K_RETURN):
            self.audio.play("click")
            from .game import GameScene
            self.manager.switch(GameScene(self.manager))       # formulas kept in session
        elif self.levels_button.handle_event(event) == "click":
            self.audio.play("click")
            from .levels import LevelSelectScene
            self.manager.switch(LevelSelectScene(self.manager))
        elif self.menu_button.handle_event(event) == "click":
            self.audio.play("click")
            from .menu import MenuScene
            self.manager.switch(MenuScene(self.manager))

    def draw(self, surface):
        s = self.session.stats
        draw_text(surface, f"Money: {int(self.session.money)}", (px(12), px(12)), 16, config.TEXT, kind="bold")
        lines = [
            ("Last result", s.get("reason", "")),
            ("Attempts", str(s.get("attempts", 0))),
        ]
        draw_overlay_card(surface, self.background, "MISSION FAILED", config.DANGER, lines, card_h=280)
        for b in (self.retry_button, self.levels_button, self.menu_button):
            b.draw(surface)
