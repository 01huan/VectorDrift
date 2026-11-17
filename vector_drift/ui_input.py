"""A single-line text field (search boxes and numeric filters).

Separate from the code editor (``ui_editor``): this is a box with one line
of text, used by the community browser's search bar.  The widget reports
whether the text changed, so the scene can refresh its list only when it
really has to.
"""

from __future__ import annotations

from typing import Callable, Optional

import pygame

from . import config
from .config import px
from .ui_fonts import draw_text, fit_text, get_font

__all__ = ["TextInput", "Dropdown"]


class TextInput:
    """A focusable one-line text field.

    Parameters
    ----------
    rect:
        Where the field is drawn (real pixels).
    placeholder:
        Dimmed hint shown while the field is empty.
    font_size:
        Logical font size.
    max_length:
        Maximum number of characters.
    numeric:
        Only digits are accepted (used by the "at least N" filters).
    on_change:
        Called with the new text whenever it changes.
    """

    def __init__(self, rect, placeholder: str = "", *, font_size: int = 15,
                 max_length: int = 80, numeric: bool = False,
                 on_change: Optional[Callable[[str], None]] = None):
        self.rect = pygame.Rect(rect)
        self.placeholder = placeholder
        self.font_size = font_size
        self.max_length = max_length
        self.numeric = numeric
        self.on_change = on_change
        self.active = False
        self.cursor = 0
        self._text = ""
        self._scroll = 0
        self._keydown_inserted = False
        self._last_keydown_char = ""

    # ------------------------------------------------------------------ text

    @property
    def text(self) -> str:
        """The current text."""
        return self._text

    @text.setter
    def text(self, value) -> None:
        self.set_text(value)

    def set_text(self, value) -> None:
        """Replace the text (clipped to ``max_length``) and notify the owner."""
        if not isinstance(value, str):
            value = "" if value is None else str(value)
        value = self._one_line(value)
        if self.numeric:
            value = "".join(ch for ch in value if ch.isdigit())
        value = value[:self.max_length]
        if value == self._text:
            return
        self._text = value
        self.cursor = min(self.cursor, len(value))
        self._update_scroll()
        self._notify()

    def clear(self) -> None:
        """Empty the field."""
        self.set_text("")

    def _notify(self) -> None:
        if self.on_change is not None:
            try:
                self.on_change(self._text)
            except Exception:  # a broken listener must not break typing
                pass

    # ----------------------------------------------------------------- events

    def handle_event(self, event) -> bool:
        """Handle one event; returns True when the text changed."""
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self._keydown_inserted = False
            self._last_keydown_char = ""
            if self.rect.collidepoint(event.pos):
                self.active = True
                self._move_cursor_to_pos(event.pos[0])
            elif self.active:
                self.active = False       # clicking elsewhere drops the focus
            return False
        if not self.active:
            return False
        if event.type == pygame.TEXTINPUT:
            text = getattr(event, "text", "")
            if self._keydown_inserted and text == self._last_keydown_char:
                # The same character already arrived as a KEYDOWN event.
                self._keydown_inserted = False
                self._last_keydown_char = ""
                return False
            self._keydown_inserted = False
            self._last_keydown_char = ""
            return self._insert(text)
        if event.type != pygame.KEYDOWN:
            return False

        self._keydown_inserted = False
        self._last_keydown_char = ""
        mod = getattr(event, "mod", 0) or 0
        ctrl = bool(mod & pygame.KMOD_CTRL)
        # AltGr is reported as Ctrl+Alt, so it must keep typing instead of
        # triggering the Ctrl shortcuts (e.g. Polish "ą" via AltGr+A).
        altgr = ctrl and bool(mod & pygame.KMOD_ALT)
        if event.key == pygame.K_BACKSPACE:
            return self._delete_before()
        if event.key == pygame.K_DELETE:
            return self._delete_after()
        if event.key == pygame.K_LEFT:
            self.cursor = max(0, self.cursor - 1)
            self._update_scroll()
            return False
        if event.key == pygame.K_RIGHT:
            self.cursor = min(len(self._text), self.cursor + 1)
            self._update_scroll()
            return False
        if event.key == pygame.K_HOME:
            self.cursor = 0
            self._update_scroll()
            return False
        if event.key == pygame.K_END:
            self.cursor = len(self._text)
            self._update_scroll()
            return False
        if ctrl and not altgr and event.key == pygame.K_a:
            self.cursor = len(self._text)
            self._update_scroll()
            return False
        if ctrl and not altgr and event.key == pygame.K_c:
            try:
                pygame.scrap.put_text(self._text)
            except Exception:
                pass
            return False
        if ctrl and not altgr and event.key == pygame.K_x:
            try:
                pygame.scrap.put_text(self._text)
            except Exception:
                pass
            return self._delete_all()
        if ctrl and not altgr and event.key == pygame.K_v:
            try:
                pasted = pygame.scrap.get_text()
            except Exception:
                pasted = None
            return self._insert(pasted or "")
        # An unhandled Ctrl shortcut must not type its letter (Ctrl+Z used to
        # insert "z").  AltGr (Ctrl+Alt) still types through here.
        if ctrl and not altgr:
            return False
        unicode_text = getattr(event, "unicode", "")
        if unicode_text and len(unicode_text) == 1 and unicode_text.isprintable():
            if self._insert(unicode_text):
                self._keydown_inserted = True
                self._last_keydown_char = unicode_text
            return True
        return False

    # -------------------------------------------------------------- editing

    def _insert(self, text) -> bool:
        if not text:
            return False
        if self.numeric:
            text = "".join(ch for ch in text if ch.isdigit())
            if not text:
                return False
        text = self._one_line(text)
        room = self.max_length - len(self._text)
        if room <= 0:
            return False
        text = text[:room]
        self._text = self._text[:self.cursor] + text + self._text[self.cursor:]
        self.cursor += len(text)
        self._update_scroll()
        self._notify()
        return True

    def _delete_before(self) -> bool:
        if self.cursor <= 0:
            return False
        self._text = self._text[:self.cursor - 1] + self._text[self.cursor:]
        self.cursor -= 1
        self._update_scroll()
        self._notify()
        return True

    def _delete_after(self) -> bool:
        if self.cursor >= len(self._text):
            return False
        self._text = self._text[:self.cursor] + self._text[self.cursor + 1:]
        self._update_scroll()
        self._notify()
        return True

    def _delete_all(self) -> bool:
        if not self._text:
            return False
        self._text = ""
        self.cursor = 0
        self._scroll = 0
        self._notify()
        return True

    @staticmethod
    def _one_line(value: str) -> str:
        """A single line of text: line breaks and tabs from a paste become spaces."""
        return (value.replace("\r\n", " ").replace("\r", " ")
                .replace("\n", " ").replace("\t", " "))

    def _move_cursor_to_pos(self, x: int) -> None:
        """Put the cursor at the character closest to the click position."""
        font = get_font(self.font_size, "ui")
        left = self.rect.x + px(8) - self._scroll
        best = 0
        best_distance = abs(left - x)
        for index in range(len(self._text) + 1):
            position = left + font.size(self._text[:index])[0]
            distance = abs(position - x)
            if distance < best_distance:
                best_distance = distance
                best = index
        self.cursor = best
        self._update_scroll()

    def _update_scroll(self) -> None:
        """Keep the cursor inside the visible part of the field."""
        font = get_font(self.font_size, "ui")
        available = max(px(4), self.rect.w - px(16))
        cursor_x = font.size(self._text[:self.cursor])[0]
        if cursor_x - self._scroll > available - px(4):
            self._scroll = cursor_x - available + px(4)
        if cursor_x - self._scroll < 0:
            self._scroll = max(0, cursor_x - px(4))
        text_width = font.size(self._text)[0]
        self._scroll = min(self._scroll, max(0, text_width - px(4)))

    # ------------------------------------------------------------------ draw

    def draw(self, surface) -> None:
        pygame.draw.rect(surface, config.EDITOR_BG, self.rect, border_radius=px(4))
        pygame.draw.rect(surface, config.ACCENT if self.active else config.EDITOR_BORDER,
                         self.rect, width=max(1, px(1)), border_radius=px(4))
        if self._text:
            shown, color = self._text, config.TEXT
        else:
            shown, color = self.placeholder, config.TEXT_FAINT

        previous_clip = surface.get_clip()
        surface.set_clip(self.rect)
        try:
            draw_text(surface, shown, (self.rect.x + px(8) - self._scroll, self.rect.centery),
                      self.font_size, color, anchor="midleft")
            if self.active:
                font = get_font(self.font_size, "ui")
                cursor_x = (self.rect.x + px(8) - self._scroll
                            + font.size(self._text[:self.cursor])[0])
                pygame.draw.line(surface, config.EDITOR_CURSOR,
                                 (cursor_x, self.rect.y + px(5)),
                                 (cursor_x, self.rect.bottom - px(5)),
                                 max(1, px(1)))
        finally:
            surface.set_clip(previous_clip)


class Dropdown:
    """A value picker that opens a small list below its button.

    ``items`` is a sequence of ``(value, label)`` pairs; one entry is always
    selected.  Clicking the button toggles the list, clicking an entry picks
    it (and calls ``on_select``), and clicking anywhere outside closes the
    list without selecting anything.  While the list is open every event is
    consumed so nothing underneath reacts.

    The button itself is drawn with :meth:`draw`; the open list is drawn on
    top of everything with :meth:`draw_overlay` (call it after the cards).
    """

    ITEM_H = 26        # logical height of one entry in the open list

    def __init__(self, rect, items, *, font_size: int = 14, prefix: str = "",
                 on_select: Optional[Callable[[object], None]] = None):
        self.items = list(items or ())
        self.rect = pygame.Rect(rect)
        self.font_size = font_size
        self.prefix = prefix
        self.on_select = on_select
        self.open = False
        self.hover = -1
        self._value = self.items[0][0] if self.items else None
        self._button = _DropdownButton(self.rect, self._label(), font_size)

    # ------------------------------------------------------------------ value

    @property
    def value(self):
        return self._value

    @property
    def button(self):
        """The button face (e.g. for tooltips and tests)."""
        return self._button

    def label_of(self, value) -> str:
        for item_value, label in self.items:
            if item_value == value:
                return label
        return str(value)

    def set_value(self, value) -> None:
        self._value = value
        self._button.label = self._label()

    def close(self) -> None:
        self.open = False
        self.hover = -1
        self._button.hover = False

    def _label(self) -> str:
        label = self.label_of(self._value) if self.items else ""
        return f"{self.prefix}{label}" if self.prefix else label

    # ------------------------------------------------------------------ events

    def item_rects(self) -> list:
        """The rect of every entry in the open list, below the button."""
        width = self.rect.w
        x, y = self.rect.x, self.rect.bottom + px(2)
        return [pygame.Rect(x, y + index * px(self.ITEM_H), width, px(self.ITEM_H))
                for index in range(len(self.items))]

    def handle_event(self, event) -> bool:
        if self.open:
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self.close()
                return True
            if event.type == pygame.MOUSEMOTION:
                self.hover = self._index_at(event.pos)
                return True
            if event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:
                    if self.rect.collidepoint(event.pos):
                        self.close()
                        return True
                    index = self._index_at(event.pos)
                    if index >= 0:
                        self._pick(index)
                    else:
                        self.close()
                return True
            # Swallow everything else while the list is open.
            return True
        if self._button.handle_event(event) == "click":
            self.open = True
            self.hover = -1
            return True
        return False

    def _index_at(self, pos) -> int:
        for index, rect in enumerate(self.item_rects()):
            if rect.collidepoint(pos):
                return index
        return -1

    def _pick(self, index: int) -> None:
        value, _label = self.items[index]
        self.open = False
        self.hover = -1
        self._value = value
        self._button.label = self._label()
        if self.on_select is not None:
            try:
                self.on_select(value)
            except Exception:  # noqa: BLE001 - a broken listener must not break the picker
                pass

    # ------------------------------------------------------------------- draw

    def draw(self, surface) -> None:
        self._button.draw(surface, chevron_down=True)

    def draw_overlay(self, surface) -> None:
        if not self.open:
            return
        rects = self.item_rects()
        if not rects:
            self.open = False
            return
        total = rects[-1].bottom - rects[0].top
        backdrop = pygame.Rect(rects[0].x, rects[0].y, rects[0].w, total)
        panel = backdrop.inflate(px(4), px(4))
        pygame.draw.rect(surface, config.PANEL_BG, panel, border_radius=px(4))
        pygame.draw.rect(surface, config.PANEL_EDGE, panel, width=max(1, px(1)),
                         border_radius=px(4))
        for index, (rect, (value, label)) in enumerate(zip(rects, self.items)):
            selected = value == self._value
            if index == self.hover:
                pygame.draw.rect(surface, config.EDITOR_LINE_HL, rect, border_radius=px(3))
            if selected:
                check = [(rect.x + px(6), rect.centery),
                         (rect.x + px(10), rect.centery + px(4)),
                         (rect.x + px(17), rect.centery - px(4))]
                pygame.draw.lines(surface, config.ACCENT, False, check, max(1, px(2)))
            draw_text(surface, fit_text(label, rect.w - px(34), self.font_size),
                      (rect.x + px(24), rect.centery), self.font_size,
                      config.TEXT if selected else config.TEXT_DIM,
                      kind="bold" if selected else "ui", anchor="midleft")


class _DropdownButton:
    """The flat button face of a :class:`Dropdown` (icon arrow included)."""

    def __init__(self, rect, label: str, font_size: int):
        self.rect = pygame.Rect(rect)
        self.label = label
        self.font_size = font_size
        self.enabled = True
        self.hover = False

    def handle_event(self, event):
        if event.type == pygame.MOUSEMOTION:
            self.hover = self.rect.collidepoint(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                return "click" if self.enabled else "disabled"
        return None

    def draw(self, surface, chevron_down: bool = True) -> None:
        bg, hover_bg = config.BUTTON_PLAIN, config.BUTTON_PLAIN_HOVER
        if self.hover:
            bg = hover_bg
        pygame.draw.rect(surface, bg, self.rect, border_radius=px(3))
        chevron_x = self.rect.right - px(18)
        center_y = self.rect.centery
        draw_text(surface, fit_text(self.label, self.rect.w - px(38), self.font_size, "bold"),
                  (self.rect.x + px(10), center_y), self.font_size,
                  (255, 255, 255), kind="bold", anchor="midleft")
        direction = 1 if chevron_down else -1
        tip_y = center_y + direction * px(3)
        base_y = center_y - direction * px(3)
        points = [(chevron_x - px(4), base_y), (chevron_x + px(4), base_y),
                  (chevron_x, tip_y)]
        pygame.draw.polygon(surface, (255, 255, 255), points)
