"""Level-complete screen: stats + Replay / Levels / Main Menu."""

import pygame

from .. import config
from ..config import px
from ..ui import draw_text
from .base import Scene, draw_overlay_card, result_buttons


class WinScene(Scene):
    def __init__(self, manager, background=None):
        super().__init__(manager)
        self.background = background
        self.replay_button, self.levels_button, self.menu_button = result_buttons("Replay")
        for b in (self.replay_button, self.levels_button, self.menu_button):
            b.rect.y = config.WINDOW_H // 2 + px(120)

    def handle_event(self, event):
        if self.replay_button.handle_event(event) == "click" or (
                event.type == pygame.KEYDOWN and event.key == pygame.K_RETURN):
            self.audio.play("click")
            from .game import GameScene
            self.session.fx_text = self.session.fy_text = ""     # replay starts clean
            self.manager.switch(GameScene(self.manager))
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
        lines = [
            ("Last flight", f"{s.get('time', 0):.2f} s"),
            ("Total flight time", f"{s.get('total_time', 0):.2f} s"),
            ("Attempts", str(s.get("attempts", 1))),
            ("Lives left", f"{s.get('lives_left', 0)} / {s.get('max_lives', 5)}"),
            ("Fx", s.get("fx", "0")),
            ("Fy", s.get("fy", "0")),
        ]
        card = draw_overlay_card(surface, self.background, "MISSION COMPLETE", config.SUCCESS, lines,
                                 card_h=410)
        if s.get("solution_used"):
            # Below the stat lines (they start at card.y + 104, 30 apart).
            draw_text(surface, "Solution used · not counted as a best time",
                      (card.centerx, card.y + px(104 + 30 * len(lines) + 6)), 16, config.WARNING,
                      kind="bold", anchor="center")
        for b in (self.replay_button, self.levels_button, self.menu_button):
            b.draw(surface)
