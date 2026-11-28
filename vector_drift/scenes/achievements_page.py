"""Achievements page: every achievement as a card, unlocked or not.

Three columns in the order of achievements.ACHIEVEMENTS. A tiered card
shows its highest tier, four pips, the next tier's goal and a progress bar;
a single card shows its rule. Locked cards are dimmed; hidden ones show
"???" until (their first tier is) unlocked. Back or Esc returns to the main
menu.
"""

import pygame

from .. import config
from ..achievements import (ACHIEVEMENTS, TIERS, counts, describe, display_name, is_unlocked,
                            thresholds, tier_met, tier_reached, value)
from ..config import px
from ..ui import Button, draw_text, get_font
from .achievement_ui import TIER_COLORS, draw_icon
from .base import Scene

COLUMNS = 3
SIDE, TOP, GAP = 40, 112, 8             # logical px
CARD_H = 58
ICON = 40
HIDDEN_NAME, HIDDEN_TEXT = "???", "Hidden achievement"
BAR_W, BAR_H = 360, 8
PIP_R, PIP_GAP = 4, 11


def _fit(text, size, width, kind="ui"):
    """``text`` cut with an ellipsis to fit ``width`` real pixels.

    Translate first: cutting the English source and translating the fragment
    would not match any catalog key and could overflow the card.
    """
    from ..i18n import translate
    from ..ui_fonts import _needs_cjk_font
    text = translate(text)
    font = get_font(size, kind, cjk=_needs_cjk_font(text))
    if font.size(text)[0] <= width:
        return text
    while text and font.size(text + "…")[0] > width:
        text = text[:-1]
    return text.rstrip() + "…"


def tier_status(session, achievement):
    """(tier reached, text of the goal shown, progress 0-1, number text) for a tiered card."""
    reached = tier_reached(session, achievement)
    goal = min(reached + 1, TIERS)
    current = value(session, achievement)
    limit = thresholds(achievement)[goal - 1]
    if reached == TIERS:
        fraction = 1.0
    elif achievement.lower_is_better:
        fraction = 1.0 if tier_met(achievement, current, limit) else 0.0
    else:
        fraction = min(1.0, (current or 0) / limit) if limit else 0.0
    if achievement.lower_is_better:
        number = "best —" if current is None else f"best {current:.2f} s"
    else:
        number = f"{min(current or 0, limit)} / {limit}"
    return reached, describe(achievement, goal), fraction, number


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
            rect = self.card_rect(i)
            if achievement.tiered:
                self._draw_tiered(surface, rect, achievement)
            else:
                self._draw_single(surface, rect, achievement)

    def _card(self, surface, rect, achievement, unlocked, tier=0):
        """Card frame and icon; returns (text x, text width)."""
        pygame.draw.rect(surface, config.PANEL_BG, rect, border_radius=px(4))
        edge = config.PANEL_EDGE if not unlocked else (64, 84, 130)
        pygame.draw.rect(surface, edge, rect, width=max(1, px(1)), border_radius=px(4))
        icon = pygame.Rect(0, 0, px(ICON), px(ICON))
        icon.midleft = (rect.x + px(9), rect.centery)
        secret = achievement.hidden and not unlocked
        draw_icon(surface, icon, achievement, locked=not unlocked, hidden=secret, tier=tier)
        tx = icon.right + px(10)
        return tx, rect.right - px(10) - tx

    def _draw_single(self, surface, rect, achievement):
        unlocked = is_unlocked(self.session, achievement.id)
        secret = achievement.hidden and not unlocked
        tx, width = self._card(surface, rect, achievement, unlocked)
        name = HIDDEN_NAME if secret else achievement.name
        text = HIDDEN_TEXT if secret else achievement.description
        draw_text(surface, _fit(name, 15, width, "bold"), (tx, rect.y + px(10)), 15,
                  config.TEXT if unlocked else config.TEXT_DIM, kind="bold")
        draw_text(surface, _fit(text, 12, width), (tx, rect.y + px(33)), 12,
                  config.TEXT_DIM if unlocked else config.TEXT_FAINT)

    def _draw_tiered(self, surface, rect, achievement):
        reached, goal, fraction, number = tier_status(self.session, achievement)
        unlocked = reached > 0
        secret = achievement.hidden and not unlocked
        tx, width = self._card(surface, rect, achievement, unlocked, tier=reached)

        # Four pips at the top right, lit in each reached tier's metal.
        pips_w = (TIERS - 1) * px(PIP_GAP)
        px0 = rect.right - px(12) - pips_w
        for t in range(1, TIERS + 1):
            center = (px0 + (t - 1) * px(PIP_GAP), rect.y + px(16))
            if t <= reached:
                pygame.draw.circle(surface, TIER_COLORS[t - 1], center, px(PIP_R))
            else:
                pygame.draw.circle(surface, config.PANEL_EDGE, center, px(PIP_R), max(1, px(1)))

        name = HIDDEN_NAME if secret else display_name(achievement, reached)
        name_w = px0 - px(PIP_R) - px(8) - tx
        draw_text(surface, _fit(name, 15, name_w, "bold"), (tx, rect.y + px(8)), 15,
                  config.TEXT if unlocked else config.TEXT_DIM, kind="bold")
        if secret:
            draw_text(surface, HIDDEN_TEXT, (tx, rect.y + px(29)), 12, config.TEXT_FAINT)
            return
        number_w = get_font(11).size(number)[0]
        draw_text(surface, number, (rect.right - px(10), rect.y + px(36)), 11, config.TEXT_DIM, anchor="midright")
        draw_text(surface, _fit(goal, 12, width - number_w - px(8)), (tx, rect.y + px(29)), 12,
                  config.TEXT_DIM if unlocked else config.TEXT_FAINT)
        bar = pygame.Rect(tx, rect.y + px(47), width, px(4))
        pygame.draw.rect(surface, config.PANEL_EDGE, bar, border_radius=bar.h // 2)
        if fraction > 0:
            fill = bar.copy()
            fill.w = max(bar.h, round(bar.w * fraction))
            color = TIER_COLORS[min(reached, TIERS - 1)] if reached < TIERS else TIER_COLORS[-1]
            pygame.draw.rect(surface, color, fill, border_radius=bar.h // 2)
