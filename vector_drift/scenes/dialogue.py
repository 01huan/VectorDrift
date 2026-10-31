"""Story dialogue box: Poland says a few lines in the middle of the plot.

The box is modal. A click, Enter or Space shows the whole line at once if it
is still typing, else moves on; Esc skips the rest. After the last line
``done`` turns True and GameScene closes the box.
"""

import pygame

from .. import config, sprites
from ..config import px
from ..ui import draw_text, wrap_text

BOX_W, BOX_H = 600, 190
PAD = 22
BALL_R = 32                     # half the ball's height
TEXT_SIZE = 20
LINE_H = 28
CHARS_PER_S = 45
BLIP_EVERY = 3                  # one "blip" per this many typed characters
SPEAKER = "POLAND"
ADVANCE_KEYS = (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE)


class DialogueBox:
    def __init__(self, lines, area, audio=None):
        """``lines``: what Poland says, one per page. ``area``: the rect to center in.
        ``audio`` (a SoundBank, optional) plays the typing blips."""
        self.lines = tuple(lines)
        self.audio = audio
        self.index = 0
        self.shown = 0.0                # characters of the current line typed so far
        self.done = not self.lines
        self.t = 0.0
        self.rect = pygame.Rect(0, 0, px(BOX_W), px(BOX_H))
        self.rect.center = pygame.Rect(area).center
        ball_rx = BALL_R * sprites.POLAND_WIDTH
        self.ball_center = (self.rect.x + px(PAD + ball_rx), self.rect.bottom - px(PAD + BALL_R))
        self.text_x = self.rect.x + px(2 * PAD + 2 * ball_rx)
        self.text_w = self.rect.right - px(PAD) - self.text_x

    @property
    def line(self):
        return self.lines[self.index]

    @property
    def typing(self):
        return self.shown < len(self.line)

    def advance(self):
        if self.done:
            return
        if self.typing:
            self.shown = len(self.line)
            return
        self.index += 1
        self.shown = 0.0
        if self.index >= len(self.lines):
            self.index = len(self.lines) - 1
            self.done = True

    def skip(self):
        self.done = True

    def handle_event(self, event):
        """Returns True when the event was a click or key the box used."""
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.advance()
            return True
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.skip()
            elif event.key in ADVANCE_KEYS:
                self.advance()
            return True
        return False

    def update(self, dt):
        self.t += dt
        if not self.done and self.typing:
            before = int(self.shown)
            self.shown = min(len(self.line), self.shown + CHARS_PER_S * dt)
            if self.audio is not None and int(self.shown) // BLIP_EVERY > before // BLIP_EVERY:
                self.audio.play("blip")

    def draw(self, surface):
        shade = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        shade.fill((5, 8, 18, 110))
        surface.blit(shade, (0, 0))

        box = self.rect
        pygame.draw.rect(surface, config.PANEL_BG, box, border_radius=px(8))
        pygame.draw.rect(surface, sprites.POLAND_RED, box, width=max(2, px(2)), border_radius=px(8))
        sprites.draw_polandball(surface, self.ball_center, px(BALL_R), self.t,
                                talking=not self.done and self.typing)

        y = box.y + px(PAD)
        draw_text(surface, SPEAKER, (self.text_x, y), 14, sprites.POLAND_RED, kind="bold")
        y += px(26)
        text = self.line[:int(self.shown)]
        # Wrap the whole line so words do not jump to the next row mid-typing.
        rows, used = [], 0
        for row in wrap_text(self.line, TEXT_SIZE, self.text_w):
            rows.append(text[used:used + len(row)])
            used += len(row) + 1
        for row in rows:
            if row:
                draw_text(surface, row, (self.text_x, y), TEXT_SIZE, config.TEXT)
            y += px(LINE_H)

        footer = f"{self.index + 1}/{len(self.lines)}   click to continue · Esc to skip"
        draw_text(surface, footer, (box.right - px(PAD), box.bottom - px(14)), 12,
                  config.TEXT_FAINT, anchor="midright")
