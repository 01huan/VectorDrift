"""Achievements page: every achievement as a card, unlocked or not.

Three columns in the order of achievements.ACHIEVEMENTS. Locked cards are
dimmed; hidden ones show "???" until unlocked. Back or Esc returns to the
main menu.
"""

import pygame

from .. import config
from ..achievements import ACHIEVEMENTS, counts, is_unlocked
from ..config import px
from ..ui import Button, draw_text, get_font
from .achievement_ui import draw_icon
from .base import Scene

COLUMNS = 3
SIDE, TOP, GAP = 40, 112, 8             # logical px
CARD_H = 58
ICON = 40
HIDDEN_NAME, HIDDEN_TEXT = "???", "Hidden achievement"
BAR_W, BAR_H = 360, 8


def _fit(text, size, width, kind="ui"):
    """``text`` cut with an ellipsis to fit ``width`` real pixels."""
    font = get_font(size, kind)
    if font.size(text)[0] <= width:
        return text
    while text and font.size(text + "…")[0] > width:
        text = text[:-1]
    return text.rstrip() + "…"


class AchievementsScene(Scene):
    music = "menu"

    def __init__(self, manager):
        super().__init__(manager)
        self.back_button = Button((px(20), px(20), px(110), px(40)), "Back", style="plain", font_size=16)

    def card_rect(self, index):
        width = (config.WINDOW_W - 2 * px(SIDE) - (COLUMNS - 1) * px(GAP)) // COLUMNS
        row, col = divmod(index, COLUMNS)
        return pygame.Rect(px(SIDE) + col * (width + px(GAP)), px(TOP) + row * (px(CARD_H) + px(GAP)),
                           width, px(CARD_H))

    def handle_event(self, event):
        if self.back_button.handle_event(event) == "click" or (
                event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
            self.audio.play("click")
            from .menu import MenuScene
            self.manager.switch(MenuScene(self.manager))

    def draw(self, surface):
        surface.fill(config.BG)
        self.back_button.draw(surface)
        cx = config.WINDOW_W // 2
        draw_text(surface, "Achievements", (cx, px(40)), 30, config.TEXT, kind="bold", anchor="center")
        done, total = counts(self.session)
        bar = pygame.Rect(0, 0, px(BAR_W), px(BAR_H))
        bar.center = (cx, px(80))
        pygame.draw.rect(surface, config.PANEL_EDGE, bar, border_radius=bar.h // 2)
        if done:
            fill = bar.copy()
            fill.w = max(bar.h, round(bar.w * done / total))
            pygame.draw.rect(surface, config.ACCENT, fill, border_radius=bar.h // 2)
        draw_text(surface, f"{done} / {total}", (bar.right + px(12), bar.centery), 15, config.TEXT_DIM,
                  anchor="midleft")

        for i, achievement in enumerate(ACHIEVEMENTS):
            self._draw_card(surface, self.card_rect(i), achievement)

    def _draw_card(self, surface, rect, achievement):
        unlocked = is_unlocked(self.session, achievement.id)
        secret = achievement.hidden and not unlocked
        pygame.draw.rect(surface, config.PANEL_BG, rect, border_radius=px(4))
        edge = config.PANEL_EDGE if not unlocked else (64, 84, 130)
        pygame.draw.rect(surface, edge, rect, width=max(1, px(1)), border_radius=px(4))
        icon = pygame.Rect(0, 0, px(ICON), px(ICON))
        icon.midleft = (rect.x + px(9), rect.centery)
        draw_icon(surface, icon, achievement, locked=not unlocked, hidden=secret)
        tx = icon.right + px(10)
        width = rect.right - px(10) - tx
        name = HIDDEN_NAME if secret else achievement.name
        text = HIDDEN_TEXT if secret else achievement.description
        draw_text(surface, _fit(name, 15, width, "bold"), (tx, rect.y + px(10)), 15,
                  config.TEXT if unlocked else config.TEXT_DIM, kind="bold")
        draw_text(surface, _fit(text, 12, width), (tx, rect.y + px(33)), 12,
                  config.TEXT_DIM if unlocked else config.TEXT_FAINT)
