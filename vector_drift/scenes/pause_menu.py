"""Pause menu for the level screen (Esc): Resume, Abort flight, Restart, Levels, Main Menu, Quit,
plus Music / Sound on-off switches."""

import pygame

from .. import config
from ..config import px
from ..ui import Button, draw_text

CARD_W = 340
BUTTON_W, BUTTON_H, GAP = 260, 44, 12
TOP = 82                        # title area above the first button
PAD = 28


class PauseMenu:
    """handle_event only reports what the player asked for -- "resume", "abort",
    "restart", "levels", "menu" or "quit" -- and the GameScene decides what
    happens. Quit asks first ("Quit VectorDrift?"); Cancel / Esc go back.
    The bottom row holds two switches, reported as "toggle_music" /
    "toggle_sfx"; they keep the menu open (GameScene calls set_audio after).
    """

    def __init__(self, in_flight=False, music_on=True, sfx_on=True):
        self.in_flight = in_flight          # Abort flight is only offered mid-flight
        self.confirming_quit = False
        rows = [("Resume", "resume", "primary")]
        if in_flight:
            rows.append(("Abort flight", "abort", "danger"))
        rows += [("Restart", "restart", "plain"), ("Levels", "levels", "plain"),
                 ("Main Menu", "menu", "plain"), ("Quit", "quit", "plain")]

        bw, bh, gap = px(BUTTON_W), px(BUTTON_H), px(GAP)
        lines = len(rows) + 1                   # + the Music / Sound row
        height = px(TOP) + lines * bh + (lines - 1) * gap + px(PAD)
        self.card = pygame.Rect(0, 0, px(CARD_W), height)
        self.card.center = (config.WINDOW_W // 2, config.WINDOW_H // 2)
        x, y = self.card.centerx - bw // 2, self.card.y + px(TOP)
        self._menu = []
        for label, action, style in rows:
            self._menu.append((Button((x, y, bw, bh), label, style=style, font_size=17), action))
            y += bh + gap
        half = (bw - gap) // 2
        self.music_button = Button((x, y, half, bh), "", style="plain", font_size=17)
        self.sfx_button = Button((x + half + gap, y, half, bh), "", style="plain", font_size=17)
        self.set_audio(music_on, sfx_on)

        self.confirm_card = pygame.Rect(0, 0, px(CARD_W), px(TOP) + bh + px(PAD))
        self.confirm_card.center = self.card.center
        row_y = self.confirm_card.bottom - px(PAD) - bh
        self.cancel_button = Button((x, row_y, half, bh), "Cancel", style="plain", font_size=17)
        self.quit_button = Button((x + half + gap, row_y, half, bh), "Quit", style="danger",
                                  font_size=17)

    def set_audio(self, music_on, sfx_on):
        """Show the current state on the two switches."""
        self.music_button.label = "Music: On" if music_on else "Music: Off"
        self.sfx_button.label = "Sound: On" if sfx_on else "Sound: Off"

    def buttons(self):
        """(button, action) pairs that take input right now (switches: see toggles)."""
        if self.confirming_quit:
            return [(self.cancel_button, "cancel"), (self.quit_button, "quit")]
        return list(self._menu)

    def toggles(self):
        """(button, action) pairs of the Music / Sound switches (hidden while confirming)."""
        if self.confirming_quit:
            return []
        return [(self.music_button, "toggle_music"), (self.sfx_button, "toggle_sfx")]

    def handle_event(self, event):
        if event.type == pygame.KEYDOWN:
            if self.confirming_quit:
                if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    return "quit"
                if event.key == pygame.K_ESCAPE:
                    self.confirming_quit = False
            elif event.key == pygame.K_ESCAPE:
                return "resume"
            return None
        for button, action in self.buttons() + self.toggles():
            if button.handle_event(event) == "click":
                if action == "cancel":
                    self.confirming_quit = False
                    return None
                if action == "quit" and not self.confirming_quit:
                    self.confirming_quit = True
                    return None
                return action
        return None

    # ------------------------------------------------------------------ draw
    def draw(self, surface):
        shade = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        shade.fill((5, 8, 18, 200))
        surface.blit(shade, (0, 0))
        card = self.confirm_card if self.confirming_quit else self.card
        edge = config.WARNING if self.confirming_quit else config.ACCENT
        pygame.draw.rect(surface, config.PANEL_BG, card, border_radius=px(6))
        pygame.draw.rect(surface, edge, card, width=max(1, px(1)), border_radius=px(6))
        title = "Quit VectorDrift?" if self.confirming_quit else "Paused"
        draw_text(surface, title, (card.centerx, card.y + px(26)), 26,
                  config.WARNING if self.confirming_quit else config.TEXT, kind="bold",
                  anchor="midtop")
        for button, _action in self.buttons() + self.toggles():
            button.draw(surface)
