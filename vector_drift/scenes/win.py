"""Level-complete screen: stats + Replay / Levels / Main Menu."""

import pygame

from .. import config
from ..config import px
from ..image_assets import COIN_BALANCE
from ..level_presets import is_dynamic_level
from ..ui import draw_coins, draw_text
from .base import Scene, draw_overlay_card, result_buttons


class WinScene(Scene):
    def __init__(self, manager, background=None):
        super().__init__(manager)
        self.background = background
        self.replay_button, self.levels_button, self.menu_button = result_buttons("Replay")
        for b in (self.replay_button, self.levels_button, self.menu_button):
            b.rect.y = config.WINDOW_H // 2 + px(150)

    def handle_event(self, event):
        if self.replay_button.handle_event(event) == "click" or (
                event.type == pygame.KEYDOWN and event.key == pygame.K_RETURN):
            self.audio.play("click")
            from .game import GameScene
            self.session.fx_text = self.session.fy_text = ""     # replay starts clean
            self.session.editor_history = None
            self.manager.switch(GameScene(self.manager))
        elif self.levels_button.handle_event(event) == "click":
            self.audio.play("click")
            from .levels import LevelSelectScene
            self.manager.switch(LevelSelectScene(self.manager))
        elif self.menu_button.handle_event(event) == "click":
            self.audio.play("click")
            from .menu import MenuScene
            self.manager.switch(MenuScene(self.manager))

    def _notes(self, s):
        """(text, colour) lines under the stats: why this run earned what it did."""
        if s.get("solution_used"):
            return [("Solution used · not counted as a best time", config.WARNING),
                    ("Showing the answer means no coins for this run", config.WARNING)]
        if not s.get("clear_reward"):
            where = "map" if is_dynamic_level(self.session.level_id) else "level"
            return [(f"Clear reward already collected for this {where}", config.TEXT_DIM)]
        return []

    def draw(self, surface):
        s = self.session.stats
        lines = [
            ("Last flight", f"{s.get('time', 0):.2f} s"),
            ("Total flight time", f"{s.get('total_time', 0):.2f} s"),
            ("Attempts", str(s.get("attempts", 1))),
            ("Lives left", f"{s.get('lives_left', 0)} / {s.get('max_lives', 5)}"),
            ("Fx", s.get("fx", "0")),
            ("Fy", s.get("fy", "0")),
            ("Coins earned", ""),                       # amount drawn below, with coin_2
        ]
        card = draw_overlay_card(surface, self.background, "MISSION COMPLETE", config.SUCCESS, lines,
                                 card_h=470)
        draw_coins(surface, int(self.session.money), (px(12), px(12)), 16, config.TEXT, icon=COIN_BALANCE)
        # Stat lines start at card.y + 104, 30 apart (draw_overlay_card).
        coins_y = card.y + px(104) + (len(lines) - 1) * px(30)
        draw_coins(surface, f"+{int(s.get('coins_earned', 0))}", (card.right - px(48), coins_y), 17,
                   config.TEXT, kind="mono", anchor="midright")
        y = coins_y + px(36)
        for text, color in self._notes(s):
            draw_text(surface, text, (card.centerx, y), 16, color, kind="bold", anchor="center")
            y += px(26)
        for b in (self.replay_button, self.levels_button, self.menu_button):
            b.draw(surface)
