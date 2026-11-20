"""The daily map's Answer dialog: pay for today's reference answer, then see it.

Three modes, styled like the Hint dialog (hint_popup.py):

* ``"confirm"`` -- "Show today's answer for N coins? (You have M)", Cancel / Show answer
* ``"short"``   -- too few coins: says so, Close only
* ``"answer"``  -- the reference answer with Apply, Close

handle_event only reports what the player asked for -- "confirm", "cancel",
"apply" or "close" -- and the GameScene decides what happens (charging,
filling the editor).
"""

import pygame

from .. import config
from ..config import px
from ..ui import Button, draw_text, wrap_text

CARD_W = 620
CARD_H = {"confirm": 280, "short": 200, "answer": 280}
PAD = 28
TEXT_SIZE = 17
NOTE_SIZE = 15
LINE_H = 26
BUTTON_W, BUTTON_H = 120, 40

COST_NOTE = ("Paying is the only cost: coins you collect and the clear reward still count. "
             "You pay once per day; today's answer stays free after that.")


ANSWER_NOTE = "Today's reference answer. Other force fields can reach the target too."


def confirm_message(price, balance):
    return f"Show today's answer for {price} coins? (You have {balance})"


def short_message(price):
    return f"You need {price} coins to see today's answer."


class DailyAnswerPopup:
    """One dialog; ``mode`` says which of its three faces is up."""

    def __init__(self, fx, fy):
        self.fx, self.fy = fx, fy
        self.mode = None
        self.message = ""
        self.card = pygame.Rect(0, 0, px(CARD_W), px(CARD_H["confirm"]))
        bw, bh = px(BUTTON_W), px(BUTTON_H)
        self.cancel_button = Button((0, 0, bw, bh), "Cancel", style="plain", font_size=15)
        self.confirm_button = Button((0, 0, bw, bh), "Show answer", style="danger", font_size=15)
        self.close_button = Button((0, 0, bw, bh), "Close", style="plain", font_size=15)
        self.apply_button = Button((0, 0, px(90), px(32)), "Apply", style="primary", font_size=14)
        self.answer_row = pygame.Rect(0, 0, 0, 0)

    # ------------------------------------------------------------------ modes
    def show_confirm(self, price, balance):
        self._set_mode("confirm", confirm_message(price, balance))

    def show_short(self, price):
        self._set_mode("short", short_message(price))

    def show_answer(self):
        self._set_mode("answer", "")

    def _set_mode(self, mode, message):
        self.mode, self.message = mode, message
        self.card.size = (px(CARD_W), px(CARD_H[mode]))
        self.card.center = (config.WINDOW_W // 2, config.WINDOW_H // 2)
        gap = px(12)
        row_y = self.card.bottom - px(PAD) - px(BUTTON_H)
        self.cancel_button.rect.topright = (self.card.centerx - gap // 2, row_y)
        self.confirm_button.rect.topleft = (self.card.centerx + gap // 2, row_y)
        if mode == "short":
            self.close_button.rect.midtop = (self.card.centerx, row_y)
        else:
            self.close_button.rect.topright = (self.card.right - px(PAD), row_y)
        # The answer row under its note, Apply at its right end (like a Hint answer).
        width = self.card.width - 2 * px(PAD)
        note_h = len(wrap_text(ANSWER_NOTE, TEXT_SIZE, width)) * px(LINE_H)
        self.answer_row = pygame.Rect(self.card.x + px(PAD), self.card.y + px(78) + note_h + px(10),
                                      width, px(40))
        self.apply_button.rect.midright = (self.answer_row.right - px(4), self.answer_row.centery)

    def answer_text(self):
        return f"Fx = {self.fx}    Fy = {self.fy}"

    # ------------------------------------------------------------------ input
    def buttons(self):
        """(button, action) pairs that take input in the current mode."""
        if self.mode == "confirm":
            return [(self.cancel_button, "cancel"), (self.confirm_button, "confirm")]
        if self.mode == "answer":
            return [(self.apply_button, "apply"), (self.close_button, "close")]
        return [(self.close_button, "close")]

    def handle_event(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                return "cancel" if self.mode == "confirm" else "close"
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                return {"confirm": "confirm", "short": "close"}.get(self.mode)
            return None
        for button, action in self.buttons():
            if button.handle_event(event) == "click":
                return action
        return None

    # ------------------------------------------------------------------ draw
    def draw(self, surface):
        shade = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        shade.fill((5, 8, 18, 200))
        surface.blit(shade, (0, 0))
        card = self.card
        asking = self.mode != "answer"
        edge = config.WARNING if asking else config.ACCENT
        pygame.draw.rect(surface, config.PANEL_BG, card, border_radius=px(6))
        pygame.draw.rect(surface, edge, card, width=max(1, px(1)), border_radius=px(6))
        title = {"confirm": "Show today's answer?", "short": "Not enough coins",
                 "answer": "Answer"}[self.mode]
        draw_text(surface, title, (card.x + px(PAD), card.y + px(22)), 26,
                  config.WARNING if asking else config.TEXT, kind="bold")
        x, y = card.x + px(PAD), card.y + px(78)
        if self.mode == "answer":
            self._draw_answer(surface, x, y)
        else:
            draw_text(surface, self.message, (x, y), TEXT_SIZE, config.TEXT)
            if self.mode == "confirm":
                self._draw_paragraph(surface, COST_NOTE, y + px(36), NOTE_SIZE, config.TEXT_DIM)
        for button, _action in self.buttons():
            button.draw(surface)

    def _draw_paragraph(self, surface, text, y, size=TEXT_SIZE, color=config.TEXT):
        for line in wrap_text(text, size, self.card.width - 2 * px(PAD)):
            draw_text(surface, line, (self.card.x + px(PAD), y), size, color)
            y += px(LINE_H)
        return y

    def _draw_answer(self, surface, x, y):
        self._draw_paragraph(surface, ANSWER_NOTE, y)
        row = self.answer_row
        pygame.draw.rect(surface, config.BG, row, border_radius=px(4))
        draw_text(surface, self.answer_text(), (row.x + px(12), row.centery), 16, config.TEXT,
                  kind="mono", anchor="midleft")
