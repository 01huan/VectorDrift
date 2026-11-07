"""Hint dialog for the fixed levels: one step per page, then the answers."""

import pygame

from .. import config
from ..config import px
from ..ui import Button, draw_icon_row, draw_text, wrap_text

CARD_W, CARD_H = 620, 420
PAD = 28
TEXT_SIZE = 17
LINE_H = 26
BUTTON_W, BUTTON_H = 120, 40

SOLUTION_USED_TEXT = ("Showing the answer reveals the full formulas. Applying it resets the "
                      "current section to its start/checkpoint (your lives stay). The answer "
                      "price is the only cost: best time, clear reward, and coins collected "
                      "this run all still count as usual.")
CONFIRM_TEXT = SOLUTION_USED_TEXT + " You won't be asked again until you restart the game."


def confirm_text(price=0):
    """Body of the "Show the answer?" question.

    A paid answer's price sits above it with the coin pictures
    (``HintPopup.confirm_price``); a free answer keeps the once-per-launch
    wording.
    """
    text = SOLUTION_USED_TEXT if price else CONFIRM_TEXT
    return text


class HintPopup:
    """Pages 0 .. answer_page - 1 are the steps; answer_page shows the answers.

    handle_event only reports what the player asked for -- "next", "prev",
    "close", "confirm", "cancel" or ("apply", index) -- and the GameScene
    decides what happens (confirmation, level reset, filling the editor).
    """

    def __init__(self, hint):
        self.hint = hint
        self.page = 0
        self.confirming = False         # "Show the answer?" question is up
        self.confirm_text = CONFIRM_TEXT
        self.confirm_price = None       # icon row parts with the price, above confirm_text
        self.message = None             # icon row parts: why the answer can't open (too few coins)
        self.answer_price = 0           # what the answer page costs now (set by GameScene)
        self.available = 0              # coins the player can spend on it
        self.card = pygame.Rect(0, 0, px(CARD_W), px(CARD_H))
        self.card.center = (config.WINDOW_W // 2, config.WINDOW_H // 2)

        bw, bh, gap = px(BUTTON_W), px(BUTTON_H), px(12)
        row_y = self.card.bottom - px(PAD) - bh
        self.prev_button = Button((self.card.x + px(PAD), row_y, bw, bh), "Back",
                                  style="plain", font_size=15)
        self.next_button = Button((self.prev_button.rect.right + gap, row_y, bw, bh), "Next",
                                  style="primary", font_size=15)
        self.close_button = Button((self.card.right - px(PAD) - bw, row_y, bw, bh), "Close",
                                   style="plain", font_size=15)
        self.cancel_button = Button((self.card.centerx - gap // 2 - bw, row_y, bw, bh), "Cancel",
                                    style="plain", font_size=15)
        self.confirm_button = Button((self.card.centerx + gap // 2, row_y, bw, bh), "Show answer",
                                     style="danger", font_size=15)
        self.apply_buttons = [Button((0, 0, px(90), px(32)), "Apply", style="primary", font_size=14)
                              for _ in hint.answers]
        self._answer_rows = self._layout_answers()

    def _text_lines(self, text):
        return wrap_text(text, TEXT_SIZE, self.card.width - 2 * px(PAD))

    def _layout_answers(self):
        """[(label_y, row_rect)] for the answer page; places the Apply buttons."""
        x = self.card.x + px(PAD)
        y = self.card.y + px(78) + len(self._text_lines(self.hint.answer_note)) * px(LINE_H) + px(10)
        rows = []
        for answer, button in zip(self.hint.answers, self.apply_buttons):
            label_y = y
            if answer.label:
                y += px(22)
            row = pygame.Rect(x, y, self.card.width - 2 * px(PAD), px(40))
            button.rect.midright = (row.right - px(4), row.centery)
            rows.append((label_y, row))
            y = row.bottom + px(14)
        return rows

    @property
    def answer_page(self):
        return len(self.hint.steps)

    @property
    def on_answer_page(self):
        return self.page == self.answer_page

    def _buttons(self):
        """(button, action) pairs that take input on the current page."""
        if self.confirming:
            return [(self.cancel_button, "cancel"), (self.confirm_button, "confirm")]
        pairs = [(self.prev_button, "prev"), (self.close_button, "close")]
        if self.on_answer_page:
            pairs += [(b, ("apply", i)) for i, b in enumerate(self.apply_buttons)]
        else:
            pairs.append((self.next_button, "next"))
        return pairs

    def handle_event(self, event):
        if event.type == pygame.KEYDOWN:
            if self.confirming:
                if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    return "confirm"
                if event.key == pygame.K_ESCAPE:
                    return "cancel"
                return None
            if event.key == pygame.K_ESCAPE:
                return "close"
            if event.key in (pygame.K_RIGHT, pygame.K_RETURN, pygame.K_KP_ENTER) and not self.on_answer_page:
                return "next"
            if event.key == pygame.K_LEFT and self.page > 0:
                return "prev"
            return None
        self.prev_button.enabled = self.page > 0
        for button, action in self._buttons():
            if button.handle_event(event) == "click":
                return action
        return None

    # ------------------------------------------------------------------ draw
    def draw(self, surface):
        shade = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        shade.fill((5, 8, 18, 200))
        surface.blit(shade, (0, 0))
        card = self.card
        edge = config.WARNING if self.confirming else config.ACCENT
        pygame.draw.rect(surface, config.PANEL_BG, card, border_radius=px(6))
        pygame.draw.rect(surface, edge, card, width=max(1, px(1)), border_radius=px(6))

        if self.confirming:
            title = "Show the answer?"
        elif self.on_answer_page:
            title = "Answer"
        else:
            title = f"Hint {self.page + 1} / {self.answer_page}"
        draw_text(surface, title, (card.x + px(PAD), card.y + px(22)), 26,
                  config.WARNING if self.confirming else config.TEXT, kind="bold")
        y = card.y + px(78)

        if self.confirming:
            if self.confirm_price:
                draw_icon_row(surface, self.confirm_price, (card.x + px(PAD), y), TEXT_SIZE)
                y += px(LINE_H) + px(10)
            self._draw_paragraph(surface, self.confirm_text, y)
            for button in (self.cancel_button, self.confirm_button):
                button.draw(surface)
            return

        if self.on_answer_page:
            self._draw_paragraph(surface, self.hint.answer_note, y)
            for answer, button, (label_y, row) in zip(self.hint.answers, self.apply_buttons,
                                                      self._answer_rows):
                self._draw_answer(surface, answer, button, label_y, row)
        else:
            self._draw_paragraph(surface, self.hint.steps[self.page], y)
            last = self.page + 1 == self.answer_page
            self.next_button.label = "Answer" if last else "Next"
            self.next_button.price = self.answer_price if last and self.answer_price else None
            self.next_button.price_short = self.answer_price > self.available
            self.next_button.draw(surface)
            if self.message:
                draw_icon_row(surface, self.message, (card.x + px(PAD), self.next_button.rect.y - px(12)),
                              15, anchor="bottomleft")
        self.prev_button.enabled = self.page > 0
        self.prev_button.draw(surface)
        self.close_button.draw(surface)

    def _draw_paragraph(self, surface, text, y):
        for line in self._text_lines(text):
            draw_text(surface, line, (self.card.x + px(PAD), y), TEXT_SIZE, config.TEXT)
            y += px(LINE_H)

    def _draw_answer(self, surface, answer, button, label_y, row):
        """One answer row: optional label, then Fx / Fy with Apply on the right."""
        if answer.label:
            draw_text(surface, answer.label, (row.x, label_y), 15, config.TEXT_DIM, kind="bold")
        pygame.draw.rect(surface, config.BG, row, border_radius=px(4))
        draw_text(surface, f"Fx = {answer.fx}    Fy = {answer.fy}", (row.x + px(12), row.centery),
                  16, config.TEXT, kind="mono", anchor="midleft")
        button.draw(surface)
