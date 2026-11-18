"""The tutorial screen: the Basics walkthrough, shrunk, beside a list of the map's elements.

Reached after the story (story.scene_after_story): after the first Start and
from the Tutorial button on level select.

  header  - "Tutorial n / 4" on the left, Exit on the right (its right edge on
            the frame's right edge).
  frame   - the Basics walkthrough (tutorial_basics.BasicsScene: the ordinary
            game screen) at about 80.5% of its size. It is drawn full size on
            an off-screen surface and smoothscaled into the frame, so text,
            arrows, ship and buttons all shrink together and stay sharp; mouse
            positions are mapped back to full-size coordinates before the
            walkthrough sees them. Ordinary levels never go through this.
  list    - the elements of tutorial.toml's [guide] (rocks, portals, pickups),
            grouped by category, each with its card icon and name.

The walkthrough's own Exit is hidden (the header has one). Exit, Esc and
Start playing on the last step leave to level select, giving the session
back as the walkthrough borrowed it. Nothing here counts for coins,
progress, replays or achievements (counts_for_progress).
"""

import pygame

from .. import config
from ..config import px
from ..tutorial import tutorial
from ..ui import Button
from ..ui_fonts import draw_text
from .base import Scene
from .field_guide import draw_card_icon
from .game_layout import R
from .tutorial_basics import BasicsScene

FRAME = (20, 66, 1030, 580)     # logical px: the shrunk walkthrough
LIST = (1066, 66, 194, 580)     # logical px: the element list
HEADER_Y = 40                   # centre line of the header row
EXIT_SIZE = (96, 34)
LIST_PAD = 10
LIST_HEADER_H = 28              # a category name
LIST_ROW_H = 44                 # one element
LIST_GAP = 10                   # between categories
ICON_R = 13
ICON_X, NAME_X = 26, 54         # in a row: icon centre, name start (room for the two holes)
FRAME_EDGE = (60, 80, 120)


class _InnerManager:
    """The manager the walkthrough inside the frame sees.

    Everything is the real manager's, except: the screen is the off-screen
    surface, and a switch to the next step stays inside the tutorial screen
    (anything else, such as level select, really switches).
    """

    def __init__(self, outer, screen):
        object.__setattr__(self, "_outer", outer)
        object.__setattr__(self, "screen", screen)

    def __getattr__(self, name):
        return getattr(self._outer.manager, name)

    def __setattr__(self, name, value):
        setattr(self._outer.manager, name, value)

    def switch(self, scene):
        self._outer.switch_from_inside(scene)


class TutorialScene(Scene):
    music = "level"
    counts_for_progress = False         # achievements ignore this screen

    def __init__(self, manager, index=0):
        super().__init__(manager)
        self.frame = R(*FRAME)
        self.list_rect = R(*LIST)
        self._full = self._surface((config.WINDOW_W, config.WINDOW_H))
        self._shrunk = pygame.Surface(self.frame.size, 0, self._full)
        self.inner_manager = _InnerManager(self, self._full)
        self.inner = None
        self._set_inner(BasicsScene(self.inner_manager, index))
        self.exit_button = Button((0, 0, px(EXIT_SIZE[0]), px(EXIT_SIZE[1])), "Exit", style="plain",
                                  font_size=15)
        self.exit_button.rect.right = self.frame.right
        self.exit_button.rect.centery = px(HEADER_Y)
        self.headers = []               # (category name, (x, y))
        self.items = []                 # (guide item, row rect)
        self._layout_list()
        self.hover = None
        self.t = 0.0

    @staticmethod
    def _surface(size):
        surface = pygame.Surface(size)
        return surface.convert() if pygame.display.get_surface() is not None else surface

    def _layout_list(self):
        x, w = self.list_rect.x + px(LIST_PAD), self.list_rect.w - 2 * px(LIST_PAD)
        y = self.list_rect.y + px(LIST_PAD)
        for k, cat in enumerate(tutorial().guide):
            if k:
                y += px(LIST_GAP)
            self.headers.append((cat.name, (x + px(4), y + px(LIST_HEADER_H) // 2)))
            y += px(LIST_HEADER_H)
            for item in cat.items:
                self.items.append((item, pygame.Rect(x, y, w, px(LIST_ROW_H))))
                y += px(LIST_ROW_H)

    # --- the walkthrough inside -------------------------------------------------------
    def _set_inner(self, scene):
        scene.show_exit = False
        self.inner = scene

    def switch_from_inside(self, scene):
        """The walkthrough asked to switch: the next step stays here; anything else leaves."""
        if isinstance(scene, BasicsScene):
            old = self.inner
            if old is not scene:
                old.on_exit()
            self._set_inner(scene)
            return
        self.manager.switch(scene)

    def _to_inner(self, event):
        """A mouse event with its position in the walkthrough's full-size coordinates."""
        f = self.frame
        sx, sy = config.WINDOW_W / f.w, config.WINDOW_H / f.h
        attrs = dict(event.dict)
        x, y = event.pos
        attrs["pos"] = (round((x - f.x) * sx), round((y - f.y) * sy))
        if "rel" in attrs:
            attrs["rel"] = (round(attrs["rel"][0] * sx), round(attrs["rel"][1] * sy))
        return pygame.event.Event(event.type, attrs)

    @property
    def counter_text(self):
        return f"Tutorial {self.inner.index + 1} / {len(self.inner.steps)}"

    # --- leaving ----------------------------------------------------------------------
    def leave(self):
        """To level select, the session given back (BasicsScene.leave)."""
        self.inner.leave()

    def on_exit(self):
        self.inner.on_exit()

    # --- input ------------------------------------------------------------------------
    def handle_event(self, event):
        if self.exit_button.handle_event(event) == "click":
            self.audio.play("click")
            self.leave()
            return
        if event.type == pygame.MOUSEMOTION:
            self._mouse = event.pos
            self.hover = next((item for item, rect in self.items if rect.collidepoint(event.pos)), None)
        if event.type in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONUP):
            self.inner.handle_event(self._to_inner(event))      # also ends a drag begun inside
            return
        if event.type == pygame.MOUSEBUTTONDOWN:
            if self.frame.collidepoint(event.pos):
                self.inner.handle_event(self._to_inner(event))
            return
        if event.type == pygame.MOUSEWHEEL:
            if self.frame.collidepoint(getattr(self, "_mouse", (-1, -1))):
                self.inner.handle_event(event)
            return
        self.inner.handle_event(event)                          # keys and typed text

    def update(self, dt):
        self.t += dt
        self.inner.update(dt)

    # --- drawing ----------------------------------------------------------------------
    def draw(self, surface):
        surface.fill(config.BG)
        self._draw_frame(surface)
        draw_text(surface, self.counter_text, (self.frame.x, px(HEADER_Y)), 17, config.TEXT,
                  kind="bold", anchor="midleft")
        self.exit_button.draw(surface)
        self._draw_list(surface)

    def _draw_frame(self, surface):
        self.inner.draw(self._full)
        pygame.transform.smoothscale(self._full, self.frame.size, self._shrunk)
        surface.blit(self._shrunk, self.frame)
        pygame.draw.rect(surface, FRAME_EDGE, self.frame.inflate(px(2), px(2)), max(1, px(1)))

    def _draw_list(self, surface):
        pygame.draw.rect(surface, config.PANEL_BG, self.list_rect, border_radius=px(6))
        pygame.draw.rect(surface, config.EDITOR_BORDER, self.list_rect, max(1, px(1)), border_radius=px(6))
        for name, pos in self.headers:
            draw_text(surface, name, pos, 13, config.ACCENT, kind="bold", anchor="midleft")
        for item, rect in self.items:
            self._draw_row(surface, item, rect)

    def _row_state(self, item):
        return "hover" if self.hover is item else ""

    def _draw_row(self, surface, item, rect):
        state = self._row_state(item)
        if state:
            fill = config.EDITOR_LINE_HL
            pygame.draw.rect(surface, fill, rect, border_radius=px(5))
            edge = config.ACCENT if state == "selected" else config.EDITOR_BORDER
            pygame.draw.rect(surface, edge, rect, max(2, px(2)) if state == "selected" else max(1, px(1)),
                             border_radius=px(5))
        draw_card_icon(surface, item.icon, (rect.x + px(ICON_X), rect.centery), px(ICON_R), self.t)
        draw_text(surface, item.name, (rect.x + px(NAME_X), rect.centery), 14,
                  config.TEXT, kind="bold" if state == "selected" else "ui", anchor="midleft")


__all__ = ["TutorialScene", "FRAME", "LIST"]
