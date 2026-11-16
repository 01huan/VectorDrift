"""Basics: the four-step walkthrough on the ordinary game screen.

Steps and texts come from tutorial.toml (tutorial.py):
  play - the player types the force and presses Play; any flight that
         reaches the planet clears the step. A miss just tries again (no
         lives). Play stays off while a line is empty: the grey
         placeholders are hints and are never used as the formula.
  demo - the force is filled in and read only; the game flies it on its
         own. Each beat is one caption with Next; a flight that ends stops
         on its last frame until Next, then the usual rules apply (a time
         up resumes where the ship stopped, anything else goes back to start).
  card - a card with one button; the Hint button is marked, not usable.
Esc or Exit leaves to level select at any time.
"""

import pygame

from .. import config
from ..config import px
from ..tutorial import tutorial
from ..ui import Button
from ..ui_fonts import draw_text
from .game_layout import ARRIVED, FLIGHT, SETUP
from .tutorial_play import TutorialGameScene, draw_pointer, draw_rich, rich_height

HOLD = "tutorial_hold"          # a demo flight ended: its last frame stays until Next
AUTO_LAUNCH_S = 0.8             # a demo flies this long after the step opens
BOX_PAD = 18
TEXT_SIZE = 16


class BasicsScene(TutorialGameScene):

    def __init__(self, manager, index=0, restore=None):
        self.steps = tutorial().basics
        self.index = index
        self.step = self.steps[index]
        self.beat = -1                  # demo: the beat shown (or flying toward)
        self.pending = None             # demo: outcome held on the last frame
        self.done = False               # play: the planet was reached
        self.caption = None             # (text, point) shown in the box
        self.auto_wait = AUTO_LAUNCH_S
        fx, fy = self.step.force or ("", "")
        super().__init__(manager, self.step.map.level(self.step.title), fx, fy, restore)
        self.editor.placeholders = self.step.placeholders
        if self.step.kind == "card":
            self.caption = (self.step.text, self.step.point)
        self.next_button = Button((0, 0, px(110), px(36)), "Next", style="primary", font_size=16)
        self.exit_button = Button((config.WINDOW_W - px(110), px(12), px(96), px(34)), "Exit",
                                  style="plain", font_size=15)
        self.card_button = Button((0, 0, px(180), px(42)), self.step.button or "OK",
                                  style="primary", font_size=17)
        self._refresh_buttons()

    # --- state ------------------------------------------------------------------------
    @property
    def counter_text(self):
        return f"{self.index + 1} / {len(self.steps)}"

    @property
    def can_next(self):
        if self.step.kind == "play":
            return self.done
        if self.step.kind == "demo":
            return self.caption is not None
        return False

    def _empty_line(self):
        return any(not line.strip() for line in self.editor.lines)

    def _refresh_buttons(self):
        super()._refresh_buttons()
        step = getattr(self, "step", None)
        if step is None:
            return
        if step.kind != "play" or getattr(self, "done", False):
            self.editor.enabled = False
            self.run_button.enabled = False
        elif self.state == SETUP and self._empty_line():
            self.run_button.enabled = False

    # --- flying -----------------------------------------------------------------------
    def _try_launch(self):
        if self.step.kind == "card" or (self.step.kind == "play" and (self.done or self._empty_line())):
            self.audio.play("error")
            return
        super()._try_launch()

    def _record_clear(self):
        """Play step: home. (Nothing is paid or recorded in the tutorial.)"""
        if self.step.kind == "play":
            self.done = True
            self.caption = (self.step.success, "")

    def _end_flight(self, outcome):
        if self.step.kind != "demo":
            super()._end_flight(outcome)
            return
        self.audio.stop_loop("thruster_loop")
        self._sync_trail()
        self.pending = outcome
        self.state = HOLD
        beat = self.step.beats[self.beat]
        self.caption = (beat.text, beat.point)
        self._refresh_buttons()

    def _apply_pending(self):
        """Let the held flight end by the game's usual rules (resume or back to start)."""
        if self.pending is None:
            return
        outcome, self.pending = self.pending, None
        self.state = FLIGHT
        super()._end_flight(outcome)
        self.banner = None              # the caption says it

    def _start_beat(self, i):
        self.beat = i
        self.caption = None
        beat = self.step.beats[i]
        self._apply_pending()
        if beat.launch:
            self._try_launch()
        else:
            self.caption = (beat.text, beat.point)
        self._refresh_buttons()

    def advance(self):
        """Next: the next beat, else the next step (or level select after the last)."""
        self.audio.play("click")
        if self.step.kind == "demo" and self.beat + 1 < len(self.step.beats):
            self._start_beat(self.beat + 1)
            return
        if self.index + 1 < len(self.steps):
            self.audio.stop_loop("thruster_loop")
            self.manager.switch(BasicsScene(self.manager, self.index + 1, restore=self.restore))
            return
        self.leave()

    def update(self, dt):
        super().update(dt)
        if self.step.kind == "demo" and self.beat < 0:
            self.auto_wait -= dt
            if self.auto_wait <= 0:
                self._start_beat(0)

    # --- input ------------------------------------------------------------------------
    def handle_event(self, event):
        if self.exit_button.handle_event(event) == "click":
            self.audio.play("click")
            self.leave()
            return
        if self.step.kind == "card":
            if self.card_button.handle_event(event) == "click":
                self.audio.play("click")
                self.leave()
                return
        elif self.can_next:
            if self.next_button.handle_event(event) == "click":
                self.advance()
                return
            if event.type == pygame.KEYDOWN and event.key in (pygame.K_RETURN, pygame.K_KP_ENTER,
                                                              pygame.K_SPACE):
                self.advance()
                return
        if self.step.kind != "play" and event.type in (pygame.KEYDOWN, pygame.TEXTINPUT) and not (
                event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
            return                      # demo / card: the editor is read only
        super().handle_event(event)

    # --- drawing ----------------------------------------------------------------------
    def _box_text(self):
        if self.step.kind == "play":
            return self.step.text
        if self.step.kind == "demo":
            return self.caption[0] if self.caption else ""
        return ""

    def draw_overlay(self, surface):
        plot = pygame.Rect(self.camera.rect)
        self.exit_button.draw(surface)
        if self.step.kind == "card":
            self._draw_card(surface, plot)
            return
        width = plot.w - 2 * px(40)
        text_w = width - 2 * px(BOX_PAD)
        body = self._box_text()
        success = self.caption[0] if self.step.kind == "play" and self.done else ""
        height = px(BOX_PAD) * 2 + px(24) + rich_height(body, text_w, TEXT_SIZE)
        if success:
            height += px(8) + rich_height(success, text_w, TEXT_SIZE + 2)
        if self.can_next:
            height += px(46)
        box = pygame.Rect(plot.x + px(40), plot.y + px(56), width, height)
        self._draw_box(surface, box)
        x, y = box.x + px(BOX_PAD), box.y + px(BOX_PAD)
        draw_text(surface, f"{self.counter_text}   {self.step.title}", (x, y), 15, config.TEXT_DIM,
                  kind="bold")
        y += px(24)
        y += draw_rich(surface, body, (x, y), text_w, TEXT_SIZE)
        if success:
            y += px(8)
            y += draw_rich(surface, success, (x, y), text_w, TEXT_SIZE + 2, color=config.SUCCESS)
        if self.can_next:
            self.next_button.rect.bottomright = (box.right - px(BOX_PAD), box.bottom - px(12))
            self.next_button.draw(surface)
        self._draw_point(surface)

    def _draw_box(self, surface, box):
        layer = pygame.Surface(box.size, pygame.SRCALPHA)
        pygame.draw.rect(layer, (8, 12, 26, 225), layer.get_rect(), border_radius=px(8))
        pygame.draw.rect(layer, (*config.ACCENT, 200), layer.get_rect(), max(1, px(1)),
                         border_radius=px(8))
        surface.blit(layer, box.topleft)

    def _draw_point(self, surface):
        point = self.caption[1] if self.caption else ""
        if point == "ship":
            where = (self.flight.x, self.flight.y) if self.flight is not None else self.launch_pos
            draw_pointer(surface, self.world_to_screen(where), self.t)
        elif point == "start":
            draw_pointer(surface, self.world_to_screen(self.level.start), self.t)

    def _draw_card(self, surface, plot):
        # The Hint button, marked but not usable (hidden everywhere else in the tutorial).
        self.ai_button.label = "Hint"
        self.ai_button.enabled = False
        self.ai_button.draw(surface)
        mark = self.ai_button.rect.inflate(px(8), px(8))
        pygame.draw.rect(surface, (255, 214, 102), mark, max(2, px(2)), border_radius=px(6))
        draw_pointer(surface, mark.midtop, self.t)
        width = min(px(620), plot.w - 2 * px(40))
        text_w = width - 2 * px(BOX_PAD + 6)
        height = px(BOX_PAD) * 2 + px(28) + rich_height(self.step.text, text_w, TEXT_SIZE) + px(64)
        box = pygame.Rect(0, 0, width, height)
        box.center = plot.center
        self._draw_box(surface, box)
        x, y = box.x + px(BOX_PAD + 6), box.y + px(BOX_PAD)
        draw_text(surface, f"{self.counter_text}   {self.step.title}", (x, y), 15, config.TEXT_DIM,
                  kind="bold")
        draw_rich(surface, self.step.text, (x, y + px(28)), text_w, TEXT_SIZE)
        self.card_button.rect.midbottom = (box.centerx, box.bottom - px(BOX_PAD))
        self.card_button.draw(surface)


__all__ = ["BasicsScene", "HOLD", "ARRIVED"]
