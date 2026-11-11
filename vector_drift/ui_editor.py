"""Code editor widget.

The widget is assembled here (construction and geometry); editing, undo
history, input handling, painting and syntax helpers live in the
``ui_editor_*`` submodules. The helpers ``vector_drift.ui`` imports from
this module are re-exported below.
"""

import pygame

from . import config
from .config import px
from .ui_fonts import get_font
from .ui_editor_draw import CodeEditorDrawMixin
from .ui_editor_edit import CodeEditTextMixin
from .ui_editor_history import (
    HISTORY_LIMIT,
    STEP_BREAKERS,
    CodeEditorHistoryMixin,
    LineHistory,
    _Step,
)
from .ui_editor_input import CodeEditorInputMixin
from .ui_editor_syntax import (
    _TOKEN_RE,
    _dim,
    draw_squiggle,
    error_span,
    highlight,
)


def clipboard_get():
    try:
        return pygame.scrap.get_text() if hasattr(pygame.scrap, "get_text") else ""
    except Exception:            # clipboard unavailable on this platform
        return ""


def clipboard_put(text):
    try:
        if hasattr(pygame.scrap, "put_text"):
            pygame.scrap.put_text(text)
    except Exception:            # clipboard unavailable on this platform
        pass


class CodeEditor(CodeEditorHistoryMixin, CodeEditTextMixin,
                 CodeEditorInputMixin, CodeEditorDrawMixin):
    """A small IDE-style panel: a header bar, one code line per prefix (line
    numbers, syntax colors, error squiggles), a PROBLEMS list and an optional
    footer section whose rows the owner draws (see `footer_body`).

    Each line keeps its own undo history (Ctrl+Z, Ctrl+Shift+Z / Ctrl+Y).
    Typing groups into one step until the cursor moves, typing turns into
    deleting (or back), or a space / operator is typed; paste, cut,
    deleting a selection and set_lines() are steps of their own."""

    def __init__(self, pos, width, prefixes=("Fx", "Fy"), title="Vector_field",
                 footer_title=None, footer_rows_h=0, max_len=config.MAX_EXPR_LEN, on_change=None):
        self.TAB_H, self.LINE_H, self.GUTTER_W = px(28), px(28), px(30)
        self.PROB_HEADER_H, self.PROB_ROW_H, self.TEXT_PAD = px(22), px(18), px(8)
        self.prefixes = prefixes
        self.n = len(prefixes)
        self.footer_title = footer_title
        self.footer_h = (self.PROB_HEADER_H + px(footer_rows_h)) if footer_title else 0
        height = (self.TAB_H + self.LINE_H * self.n + self.PROB_HEADER_H + self.PROB_ROW_H * self.n
                  + px(6) + self.footer_h)
        self.rect = pygame.Rect(pos[0], pos[1], width, height)
        self.title = title
        self.max_len = max_len
        self.on_change = on_change
        self.lines = [""] * self.n
        self.errors = [None] * self.n        # (message, pos) per line
        self.line = 0
        self.col = 0
        self.anchor = None                   # selection anchor column on the current line
        self.history = [LineHistory() for _ in prefixes]
        self._dragging = False
        self._last_click = (0, None)         # (ticks, (line, col)) for double-click
        self.focused = True
        self.enabled = True
        self._scroll = [0] * self.n
        self._blink = 0.0
        self.font = get_font(16, "mono")
        self.small_mono = get_font(13, "mono")
        self.prefix_w = self.font.size(f"{prefixes[0]} = ")[0]

    # -- geometry --------------------------------------------------------------
    @property
    def body(self):
        return pygame.Rect(self.rect.x, self.rect.y + self.TAB_H, self.rect.w, self.LINE_H * self.n)

    def line_rect(self, i):
        b = self.body
        return pygame.Rect(b.x, b.y + i * self.LINE_H, b.w, self.LINE_H)

    def text_area(self, i):
        lr = self.line_rect(i)
        x0 = lr.x + self.GUTTER_W + self.TEXT_PAD + self.prefix_w
        return pygame.Rect(x0, lr.y, lr.right - self.TEXT_PAD - x0, lr.h)

    def problem_rect(self, k):
        top = self.body.bottom + self.PROB_HEADER_H
        return pygame.Rect(self.rect.x, top + k * self.PROB_ROW_H, self.rect.w, self.PROB_ROW_H)

    @property
    def header_rect(self):
        return pygame.Rect(self.rect.x, self.rect.y, self.rect.w, self.TAB_H)

    @property
    def footer_rect(self):
        return pygame.Rect(self.rect.x, self.rect.bottom - self.footer_h, self.rect.w, self.footer_h)

    @property
    def footer_body(self):
        """Area under the footer's title where the owner draws its rows."""
        f = self.footer_rect
        return pygame.Rect(f.x, f.y + self.PROB_HEADER_H, f.w, f.h - self.PROB_HEADER_H)


__all__ = [
    "CodeEditor", "HISTORY_LIMIT", "LineHistory", "STEP_BREAKERS",
    "clipboard_get", "clipboard_put", "draw_squiggle", "error_span",
    "highlight",
]
