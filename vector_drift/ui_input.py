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
from .ui_fonts import draw_text, get_font

__all__ = ["TextInput"]


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
        mod = getattr(event, "mod", 0)
        ctrl = bool(mod & pygame.KMOD_CTRL)
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
        if ctrl and event.key == pygame.K_a:
            self.cursor = len(self._text)
            self._update_scroll()
            return False
        if ctrl and event.key == pygame.K_c:
            try:
                pygame.scrap.put_text(self._text)
            except Exception:
                pass
            return False
        if ctrl and event.key == pygame.K_x:
            try:
                pygame.scrap.put_text(self._text)
            except Exception:
                pass
            return self._delete_all()
        if ctrl and event.key == pygame.K_v:
            try:
                pasted = pygame.scrap.get_text()
            except Exception:
                pasted = None
            return self._insert(pasted or "")
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
