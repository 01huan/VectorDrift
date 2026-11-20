"""Level-complete screen: stats + Replay / Levels / Main Menu."""

import pygame

from .. import config
from ..config import px
from ..daily_level import is_daily_level
from ..data import is_custom_map
from ..image_assets import COIN_BALANCE
from ..level_presets import is_dynamic_level
from ..ui import draw_coins, draw_text
from .base import Scene, back_label, draw_overlay_card, result_buttons
from .xp_ui import draw_xp_bar_row, xp_bar_state

CARD_H = 560                    # stats, coins, XP, up to two notes, the XP bar, the buttons
BUTTONS_UP = 70                 # the buttons' top, this far above the card's bottom edge


class WinScene(Scene):
    def __init__(self, manager, background=None):
        super().__init__(manager)
        self.background = background
        self.replay_button, self.levels_button, self.menu_button = result_buttons("Replay", back_label(self.session))
        for b in (self.replay_button, self.levels_button, self.menu_button):
            b.rect.y = config.WINDOW_H // 2 + px(CARD_H // 2 - BUTTONS_UP)
        self.xp_t = 0.0                 # seconds the XP bar has been growing
        self.xp_bar_rect = None

    def update(self, dt):
        self.xp_t += dt

    def _xp_span(self, s):
        """(XP before this clear, XP after it) for the bar."""
        gained = max(0, int(s.get("xp_gained", 0) or 0))
        before = s.get("xp_before")
        if not isinstance(before, int) or isinstance(before, bool) or before < 0:
            before = max(0, int(getattr(self.session, "xp_total", 0) or 0) - gained)
        return before, before + gained

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
            from .base import back_scene_for_level
            Target = back_scene_for_level(self.session, self)
            self.manager.switch(Target(self.manager))
        elif self.menu_button.handle_event(event) == "click":
            self.audio.play("click")
            from .menu import MenuScene
            self.manager.switch(MenuScene(self.manager))

    def _notes(self, s):
        """(text, colour) lines under the stats: why this run earned what it did."""
        if not s.get("clear_reward"):
            if is_custom_map(self.session.level_id, self.session):
                # Custom/community maps never pay a clear reward: saying it
                # was "already collected" would be a lie.
                return [("No clear reward on custom maps", config.TEXT_DIM)]
            if is_daily_level(self.session.level_id):
                return [("Clear reward already collected today", config.TEXT_DIM)]
            where = "map" if is_dynamic_level(self.session.level_id) else "level"
            return [(f"Clear reward already collected for this {where}", config.TEXT_DIM)]
        return []

    def _xp_notes(self):
        """Maps whose clear gives no XP say so (their achievements may still give some)."""
        if is_custom_map(self.session.level_id, self.session):
            return [("No XP for clearing custom maps", config.TEXT_DIM)]
        if is_daily_level(self.session.level_id):
            return [("No XP for clearing the daily challenge", config.TEXT_DIM)]
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
            ("XP earned", f"+{int(s.get('xp_gained', 0) or 0)}"),   # with this clear's achievements
        ]
        card = draw_overlay_card(surface, self.background, "MISSION COMPLETE", config.SUCCESS, lines,
                                 card_h=CARD_H)
        draw_coins(surface, int(self.session.money), (px(12), px(12)), 16, config.TEXT, icon=COIN_BALANCE)
        # Stat lines start at card.y + 104, 30 apart (draw_overlay_card).
        coins_y = card.y + px(104) + (len(lines) - 2) * px(30)
        draw_coins(surface, f"+{int(s.get('coins_earned', 0))}", (card.right - px(48), coins_y), 17,
                   config.TEXT, kind="mono", anchor="midright")
        y = coins_y + px(30) + px(36)
        for text, color in self._notes(s) + self._xp_notes():
            draw_text(surface, text, (card.centerx, y), 16, color, kind="bold", anchor="center")
            y += px(26)
        # The bar row keeps one place under room for two notes.
        bar_y = coins_y + px(30) + px(36) + 2 * px(26) + px(8)
        level, fraction = xp_bar_state(*self._xp_span(s), self.xp_t)
        self.xp_bar_rect = draw_xp_bar_row(surface, card, bar_y, level, fraction)
        for b in (self.replay_button, self.levels_button, self.menu_button):
            b.draw(surface)
