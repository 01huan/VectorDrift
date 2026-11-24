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
            grouped by category, each with its card icon and name under the
            "Element guide" title; marked until its first demo opens. Usable
            on every step.
  popup   - clicking an element opens its demo (DemoPopup) left of the list,
            a small triangle pointing at the row: a title bar with the name
            and a close button, a 4:3 clip (field_guide.GuideDemoScene: the
            same physics, drawing, pickup effects and loop as before; the map
            only, never the formulas) and the text, with "n / m" for an item
            in several parts. One at a time: another element replaces it; the
            same element, the close button, Esc or a click on the dimmed
            walkthrough closes it (that click goes no further).

While a popup is open the walkthrough is paused - it is not updated at all,
so flights, timers and the demo step's launch countdown stand still - and
its last frame stays, dimmed, with "Paused" over it; input goes only to the
popup, the list and Exit. Esc closes the popup first, then leaves.

The walkthrough's own Exit is hidden (the header has one). Exit, Esc and
Start playing on the last step leave to level select. Each tutorial scene
borrows the session's formulas, ship and level (tutorial_play.BORROWED) and
gives them back: the walkthrough once for the whole tutorial, a popup's clip
from opening to closing. So the walkthrough gets its own values back when a
popup closes, and on leaving the session is as it was before the tutorial.
Nothing here counts for coins, progress, replays or achievements
(counts_for_progress).
"""

import pygame

from .. import config
from ..config import px
from ..tutorial import tutorial
from ..ui import Button, wrap_text
from ..ui_fonts import draw_text
from . import pickup_effects as pfx
from .base import Scene
from .field_guide import GuideDemoScene, draw_card_icon
from .game_layout import FLIGHT, R, fmt_clock
from .tutorial_basics import BasicsScene
from .tutorial_play import draw_attention_ring, give_back_session

FRAME = (20, 66, 1030, 580)     # logical px: the shrunk walkthrough
LIST = (1066, 66, 194, 580)     # logical px: the element list
HEADER_Y = 40                   # centre line of the header row
EXIT_SIZE = (96, 34)
LIST_PAD = 10
LIST_TITLE_H = 46               # "Element guide" + "Click a row to watch"
LIST_HEADER_H = 28              # a category name
LIST_ROW_H = 44                 # one element
LIST_GAP = 10                   # between categories
ICON_R = 13
ICON_X, NAME_X = 26, 54         # in a row: icon centre, name start (room for the two holes)
FRAME_EDGE = (60, 80, 120)
DIM = (4, 6, 14, 170)           # over the paused walkthrough

# The demo popup (logical px)
POPUP_W = 440
POPUP_PAD = 18
TITLE_H = 40
DEMO_SIZE = (404, 303)          # 4:3, like the game's plot
POPUP_GAP = 16                  # between the popup and the list (the triangle sits in it)
TRIANGLE = 10
CLOSE_SIZE = 28
POPUP_TEXT = 15
POPUP_FILL = (12, 18, 34)


class _InnerManager:
    """The manager the scenes inside the tutorial screen see.

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
        self._dimmed = pygame.Surface(self.frame.size, 0, self._full)
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
        self.seen_popup = False         # the list is marked until its first demo opens
        self.popup = None               # the open DemoPopup, else None
        self._mouse = (-1, -1)
        self.t = 0.0

    @staticmethod
    def _surface(size):
        surface = pygame.Surface(size)
        return surface.convert() if pygame.display.get_surface() is not None else surface

    def _layout_list(self):
        x, w = self.list_rect.x + px(LIST_PAD), self.list_rect.w - 2 * px(LIST_PAD)
        y = self.list_rect.y + px(LIST_PAD) + px(LIST_TITLE_H)
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

    # --- the popup --------------------------------------------------------------------
    def open_item(self, item):
        """Open ``item``'s demo (closing any other); the walkthrough waits."""
        self.seen_popup = True
        if self.popup is None:
            self._render_inner()                # the frame that stays while paused, dimmed once
            veil = pygame.Surface(self.frame.size, pygame.SRCALPHA)
            veil.fill(DIM)
            self._dimmed.blit(self._shrunk, (0, 0))
            self._dimmed.blit(veil, (0, 0))
        self.close_popup()
        if self.inner.state == FLIGHT:
            self.audio.stop_loop("thruster_loop")
        row = next(rect for it, rect in self.items if it is item)
        self.popup = DemoPopup(self, item, row)

    def close_popup(self):
        if self.popup is None:
            return
        popup, self.popup = self.popup, None
        popup.close()
        if self.inner.state == FLIGHT:
            self.audio.start_loop("thruster_loop")

    def _click_item(self, item):
        self.audio.play("click")
        if self.popup is not None and self.popup.item is item:
            self.close_popup()
        else:
            self.open_item(item)

    # --- leaving ----------------------------------------------------------------------
    def leave(self):
        """To level select, the session given back (BasicsScene.leave)."""
        self.close_popup()
        self.inner.leave()

    def on_exit(self):
        self.close_popup()
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
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            item = next((item for item, rect in self.items if rect.collidepoint(event.pos)), None)
            if item is not None:
                self._click_item(item)
                return
        if self.popup is not None:
            self._handle_popup_event(event)
            return
        if event.type in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONUP):
            self.inner.handle_event(self._to_inner(event))      # also ends a drag begun inside
            return
        if event.type == pygame.MOUSEBUTTONDOWN:
            if self.frame.collidepoint(event.pos):
                self.inner.handle_event(self._to_inner(event))
            return
        if event.type == pygame.MOUSEWHEEL:
            if self.frame.collidepoint(self._mouse):
                self.inner.handle_event(event)
            return
        self.inner.handle_event(event)                          # keys and typed text

    def _handle_popup_event(self, event):
        """A popup is open: Esc, its close button or a click on the dimmed walkthrough closes it."""
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.audio.play("click")
            self.close_popup()
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.popup.close_rect.collidepoint(event.pos):
                self.audio.play("click")
                self.close_popup()
            elif self.frame.collidepoint(event.pos) and not self.popup.rect.collidepoint(event.pos):
                self.close_popup()              # this click only closes the popup

    def update(self, dt):
        self.t += dt
        if self.popup is not None:
            self.popup.update(dt)               # the walkthrough is paused
        else:
            self.inner.update(dt)

    # --- drawing ----------------------------------------------------------------------
    def draw(self, surface):
        surface.fill(config.BG)
        self._draw_frame(surface)
        draw_text(surface, self.counter_text, (self.frame.x, px(HEADER_Y)), 17, config.TEXT,
                  kind="bold", anchor="midleft")
        self.exit_button.draw(surface)
        self._draw_list(surface)
        if self.popup is not None:
            self.popup.draw(surface, self._full)

    def _render_inner(self):
        """The walkthrough drawn full size, then smoothscaled into the frame's picture."""
        self.inner.draw(self._full)
        pygame.transform.smoothscale(self._full, self.frame.size, self._shrunk)

    def _draw_frame(self, surface):
        if self.popup is None:
            self._render_inner()
            surface.blit(self._shrunk, self.frame)
        else:                                   # paused: the last frame stays, dimmed
            surface.blit(self._dimmed, self.frame)
        pygame.draw.rect(surface, FRAME_EDGE, self.frame.inflate(px(2), px(2)), max(1, px(1)))
        if self.popup is not None:
            draw_text(surface, "Paused", (self.frame.centerx, self.frame.y + px(28)), 20, config.TEXT,
                      kind="bold", anchor="center")

    def _draw_list(self, surface):
        pygame.draw.rect(surface, config.PANEL_BG, self.list_rect, border_radius=px(6))
        pygame.draw.rect(surface, config.EDITOR_BORDER, self.list_rect, max(1, px(1)), border_radius=px(6))
        if not self.seen_popup:
            draw_attention_ring(surface, self.list_rect, self.t, pad=3)
        x = self.list_rect.x + px(LIST_PAD + 4)
        y = self.list_rect.y + px(LIST_PAD)
        draw_text(surface, "ELEMENT GUIDE", (x, y + px(12)), 13, config.ACCENT, kind="bold",
                  anchor="midleft")
        draw_text(surface, "Click a row to watch", (x, y + px(28)), 11, config.TEXT_DIM,
                  anchor="midleft")
        for name, pos in self.headers:
            draw_text(surface, name, pos, 13, config.ACCENT, kind="bold", anchor="midleft")
        for item, rect in self.items:
            self._draw_row(surface, item, rect)

    def _row_state(self, item):
        if self.popup is not None and self.popup.item is item:
            return "selected"
        return "hover" if self.hover is item else ""

    def _draw_row(self, surface, item, rect):
        state = self._row_state(item)
        if state:
            pygame.draw.rect(surface, config.EDITOR_LINE_HL, rect, border_radius=px(5))
            edge = config.ACCENT if state == "selected" else config.EDITOR_BORDER
            pygame.draw.rect(surface, edge, rect, max(2, px(2)) if state == "selected" else max(1, px(1)),
                             border_radius=px(5))
        draw_card_icon(surface, item.icon, (rect.x + px(ICON_X), rect.centery), px(ICON_R), self.t)
        draw_text(surface, item.name, (rect.x + px(NAME_X), rect.centery), 14,
                  config.TEXT, kind="bold" if state == "selected" else "ui", anchor="midleft")


class DemoPopup:
    """One element's demo beside the list: its clip, name, text and part."""

    def __init__(self, screen, item, row):
        self.screen = screen
        self.item = item
        self._session = screen.session
        # Borrows the session from the walkthrough's values; close() gives them back.
        self.demo = GuideDemoScene(screen.inner_manager, item)
        self.text_w = px(DEMO_SIZE[0]) - (px(56) if len(item.parts) > 1 else 0)
        lines = max(len(wrap_text(part.text, POPUP_TEXT, self.text_w)) for part in item.parts)
        height = (px(TITLE_H) + px(DEMO_SIZE[1]) + px(12) + lines * px(POPUP_TEXT + 7)
                  + px(POPUP_PAD))
        self.rect = pygame.Rect(0, 0, px(POPUP_W), height)
        self.rect.right = screen.list_rect.x - px(POPUP_GAP)
        margin = px(8)
        self.rect.top = max(margin, min(row.centery - px(TITLE_H) // 2,
                                        config.WINDOW_H - margin - height))
        self.pointer_y = max(self.rect.top + px(TRIANGLE + 6),
                             min(row.centery, self.rect.bottom - px(TRIANGLE + 6)))
        self.close_rect = pygame.Rect(0, 0, px(CLOSE_SIZE), px(CLOSE_SIZE))
        self.close_rect.center = (self.rect.right - px(POPUP_PAD) - px(CLOSE_SIZE) // 2 + px(4),
                                  self.rect.y + px(TITLE_H) // 2)
        self.demo_rect = pygame.Rect(self.rect.x + px(POPUP_PAD), self.rect.y + px(TITLE_H),
                                     px(DEMO_SIZE[0]), px(DEMO_SIZE[1]))
        self.clock_pos = (self.demo_rect.right - px(44), self.demo_rect.y + px(20))
        self._clip = pygame.Surface(self.demo_rect.size, 0, screen._full)
        # The "+N" of an extratime flies to the clock shown over the clip.
        plot = pygame.Rect(self.demo.camera.rect)
        sx, sy = plot.w / self.demo_rect.w, plot.h / self.demo_rect.h
        self.demo.timer_target = (round(plot.x + (self.clock_pos[0] - self.demo_rect.x) * sx),
                                  round(plot.y + (self.clock_pos[1] - self.demo_rect.y) * sy))

    def update(self, dt):
        self.demo.update(dt)

    def close(self):
        """Stop the clip and give the walkthrough its session values back."""
        self.demo.on_exit()
        give_back_session(self._session, self.demo.restore)

    # --- drawing ----------------------------------------------------------------------
    def draw(self, surface, full):
        r = self.rect
        tip_x = self.screen.list_rect.x - px(3)
        pygame.draw.polygon(surface, config.ACCENT, [(r.right - 1, self.pointer_y - px(TRIANGLE)),
                                                     (tip_x, self.pointer_y),
                                                     (r.right - 1, self.pointer_y + px(TRIANGLE))])
        pygame.draw.rect(surface, POPUP_FILL, r, border_radius=px(8))
        pygame.draw.rect(surface, config.ACCENT, r, max(1, px(1)), border_radius=px(8))
        draw_text(surface, self.item.name, (r.x + px(POPUP_PAD), r.y + px(TITLE_H) // 2), 18,
                  config.TEXT, kind="bold", anchor="midleft")
        self._draw_close(surface)
        self._draw_clip(surface, full)
        part = self.demo.part
        y = self.demo_rect.bottom + px(12)
        for line in wrap_text(part.text, POPUP_TEXT, self.text_w):
            draw_text(surface, line, (self.demo_rect.x, y), POPUP_TEXT, config.TEXT)
            y += px(POPUP_TEXT + 7)
        if len(self.item.parts) > 1:
            draw_text(surface, f"{self.demo.part_index + 1} / {len(self.item.parts)}",
                      (self.demo_rect.right, self.demo_rect.bottom + px(12)), 14, config.TEXT_DIM,
                      kind="bold", anchor="topright")

    def _draw_close(self, surface):
        c = self.close_rect
        hover = c.collidepoint(self.screen._mouse)
        if hover:
            pygame.draw.rect(surface, config.EDITOR_LINE_HL, c, border_radius=px(4))
        k, width = px(7), max(2, px(2))
        color = config.TEXT if hover else config.TEXT_DIM
        pygame.draw.line(surface, color, (c.centerx - k, c.centery - k), (c.centerx + k, c.centery + k),
                         width)
        pygame.draw.line(surface, color, (c.centerx - k, c.centery + k), (c.centerx + k, c.centery - k),
                         width)

    def _draw_clip(self, surface, full):
        """The clip's map drawn full size, then smoothscaled into the 4:3 area."""
        demo = self.demo
        demo.draw(full)
        plot = pygame.Rect(demo.camera.rect).clip(full.get_rect())
        pygame.transform.smoothscale(full.subsurface(plot), self.demo_rect.size, self._clip)
        surface.blit(self._clip, self.demo_rect)
        pygame.draw.rect(surface, FRAME_EDGE, self.demo_rect, max(1, px(1)))
        if demo.part.show_timer:
            self._draw_clock(surface)

    def _draw_clock(self, surface):
        """The flight clock over the clip's top right (show_timer)."""
        demo = self.demo
        time_left = demo._shown_time_left()
        color = config.WARNING if demo.state == FLIGHT and time_left < 1.0 else config.TEXT
        if demo.pickup_fx.popping(pfx.TIMER):
            color = pfx.EXTRATIME_COLOR
        back = pygame.Rect(0, 0, px(78), px(30))
        back.center = self.clock_pos
        layer = pygame.Surface(back.size, pygame.SRCALPHA)
        pygame.draw.rect(layer, (6, 9, 20, 190), layer.get_rect(), border_radius=px(5))
        surface.blit(layer, back)
        draw_text(surface, fmt_clock(time_left), self.clock_pos,
                  round(20 * demo.pickup_fx.pop_scale(pfx.TIMER)), color, kind="mono", anchor="center")


__all__ = ["TutorialScene", "DemoPopup", "FRAME", "LIST"]
