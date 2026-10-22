"""Fonts and basic widgets: Button, CodeEditor."""

import re

import pygame

from . import config
from .config import px

_font_cache = {}

_FONT_CHOICES = {
    # kind: (asset file, system font fallbacks)
    "ui": ("ui.ttf", "segoeui,arial,helvetica"),
    "bold": ("ui_bold.ttf", "segoeuisemibold,segoeui,arial"),
    "mono": ("mono.ttf", "consolas,couriernew,dejavusansmono"),
}


def get_font(size, kind="ui"):
    """Font at a logical size (scaled to real pixels)."""
    key = (kind, size)
    font = _font_cache.get(key)
    if font is None:
        filename, sys_names = _FONT_CHOICES[kind]
        path = config.ASSETS_DIR / "fonts" / filename
        if path.exists():
            font = pygame.font.Font(str(path), px(size))
        else:
            font = pygame.font.SysFont(sys_names, px(size), bold=(kind == "bold"))
        _font_cache[key] = font
    return font


def draw_text(surface, text, pos, size=16, color=config.TEXT, kind="ui", anchor="topleft"):
    img = get_font(size, kind).render(text, True, color)
    rect = img.get_rect(**{anchor: pos})
    surface.blit(img, rect)
    return rect


def wrap_text(text, size, max_width, kind="ui"):
    """Split `text` into lines no wider than `max_width` real pixels (word wrap).

    A single word wider than `max_width` keeps a line of its own.
    """
    font = get_font(size, kind)
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}" if line else word
        if line and font.size(trial)[0] > max_width:
            lines.append(line)
            line = word
        else:
            line = trial
    if line:
        lines.append(line)
    return lines


def draw_panel_box(surface, rect, fill=config.PANEL_BG, edge=config.PANEL_EDGE, radius=4):
    pygame.draw.rect(surface, fill, rect, border_radius=px(radius))
    pygame.draw.rect(surface, edge, rect, width=max(1, px(1)), border_radius=px(radius))


class Button:
    """Flat button (VS Code style)."""
    STYLES = {
        "primary": (config.BUTTON_PRIMARY, config.BUTTON_PRIMARY_HOVER),
        "danger": (config.BUTTON_DANGER, config.BUTTON_DANGER_HOVER),
        "plain": (config.BUTTON_PLAIN, config.BUTTON_PLAIN_HOVER),
    }

    def __init__(self, rect, label, style="primary", font_size=18):
        self.rect = pygame.Rect(rect)
        self.label = label
        self.style = style
        self.font_size = font_size
        self.enabled = True
        self.hover = False

    def handle_event(self, event):
        """Return 'click', 'disabled' (clicked while disabled) or None."""
        if event.type == pygame.MOUSEMOTION:
            self.hover = self.rect.collidepoint(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                return "click" if self.enabled else "disabled"
        return None

    def draw(self, surface):
        bg, hover_bg = self.STYLES[self.style]
        text_color = (255, 255, 255)
        if not self.enabled:
            bg, text_color = config.BUTTON_DISABLED, config.TEXT_FAINT
        elif self.hover:
            bg = hover_bg
        pygame.draw.rect(surface, bg, self.rect, border_radius=px(3))
        if not self.enabled:
            pygame.draw.rect(surface, config.PANEL_EDGE, self.rect, width=max(1, px(1)), border_radius=px(3))
        draw_text(surface, self.label, self.rect.center, self.font_size, text_color,
                  kind="bold", anchor="center")


# --- code editor ------------------------------------------------------------------
_TOKEN_RE = re.compile(r"(\s+)|(\d+\.?\d*|\.\d*)|([A-Za-z_]+)|([+\-*/−])|(.)")


def highlight(text):
    """Split text into (chunk, color) pairs for syntax coloring."""
    out = []
    for m in _TOKEN_RE.finditer(text):
        ws, num, word, op, _other = m.groups()
        if ws:
            color = config.SYN_PLAIN
        elif num:
            color = config.SYN_NUMBER
        elif word:
            color = config.SYN_VARIABLE if word.lower() in ("x", "y") else config.SYN_IDENT
        elif op:
            color = config.SYN_OPERATOR
        else:
            color = config.SYN_PLAIN
        out.append((m.group(), color))
    return out


def error_span(text, pos):
    """(start, end) character range to underline for an error at `pos`."""
    if pos is None:
        return None
    if pos >= len(text):
        return len(text), len(text) + 1
    m = _TOKEN_RE.match(text, pos)
    end = m.end() if m and not m.group(1) else pos + 1
    return pos, max(end, pos + 1)


def _dim(color, f=0.5, bg=config.EDITOR_BG):
    return tuple(round(b + (c - b) * f) for c, b in zip(color, bg))


def draw_squiggle(surface, x0, x1, y, color=config.SQUIGGLE):
    amp, step = 1.5 * config.UI_SCALE, max(2, px(2))
    pts = []
    x, up = x0, True
    while x <= x1:
        pts.append((x, y - amp if up else y + amp))
        x += step
        up = not up
    if len(pts) >= 2:
        for dy in range(max(2, px(2))):
            pygame.draw.aalines(surface, color, False, [(qx, qy + dy * 0.7) for qx, qy in pts])


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


class CodeEditor:
    """A small IDE-style panel: a header bar, one code line per prefix (line
    numbers, syntax colors, error squiggles), a PROBLEMS list and an optional
    footer section whose rows the owner draws (see `footer_body`)."""

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

    # -- editing ---------------------------------------------------------------
    def set_lines(self, texts):
        self.lines = [t[: self.max_len] for t in texts]
        self.line = 0
        self.col = len(self.lines[0])
        self.anchor = None
        self._changed()

    def set_errors(self, errors):
        self.errors = list(errors)

    def is_text_area(self, pos):
        """True where the mouse should show a text cursor."""
        return self.enabled and self.body.collidepoint(pos)

    def selection(self):
        """(start, end) columns selected on the current line, or None."""
        if self.anchor is None or self.anchor == self.col:
            return None
        return min(self.anchor, self.col), max(self.anchor, self.col)

    def selected_text(self):
        sel = self.selection()
        return self.lines[self.line][sel[0]:sel[1]] if sel else ""

    def _changed(self):
        self.anchor = None              # any edit ends the selection (incl. a pending drag anchor)
        self._blink = 0.0
        if self.on_change:
            self.on_change(self)

    def _delete_selection(self):
        sel = self.selection()
        if not sel:
            return False
        text = self.lines[self.line]
        self.lines[self.line] = text[: sel[0]] + text[sel[1]:]
        self.col, self.anchor = sel[0], None
        return True

    def _insert(self, chars):
        chars = "".join(ch for ch in chars if ch.isprintable() and ch not in "\t\r\n")
        removed = self._delete_selection()
        text = self.lines[self.line]
        chars = chars[: self.max_len - len(text)]
        if chars:
            self.lines[self.line] = text[: self.col] + chars + text[self.col:]
            self.col += len(chars)
        if chars or removed:
            self._changed()

    def _goto(self, line, col, extend=False):
        """Move the cursor; with extend=True grow the selection (same line only)."""
        line = max(0, min(self.n - 1, line))
        if extend and line == self.line:
            if self.anchor is None:
                self.anchor = self.col
        else:
            self.anchor = None
        self.line = line
        self.col = max(0, min(len(self.lines[line]), col))
        self._blink = 0.0

    def _word_bounds(self, i, col):
        """Columns of the word (number / name) at `col`, for double-click."""
        text = self.lines[i]

        def is_word(ch):
            return ch.isalnum() or ch in "._"

        if col < len(text) and is_word(text[col]):
            start = col
        elif col > 0 and is_word(text[col - 1]):
            start = col - 1
        else:
            return col, min(len(text), col + 1)
        end = start
        while start > 0 and is_word(text[start - 1]):
            start -= 1
        while end < len(text) and is_word(text[end]):
            end += 1
        return start, end

    def _col_from_x(self, i, mouse_x):
        text = self.lines[i]
        local = mouse_x - self.text_area(i).x + self._scroll[i]
        best, best_dist = 0, abs(local)
        for c in range(1, len(text) + 1):
            dist = abs(self.font.size(text[:c])[0] - local)
            if dist < best_dist:
                best, best_dist = c, dist
        return best

    def handle_event(self, event):
        """Return True if the event was consumed (mouse motion/release never are)."""
        if not self.enabled:
            self._dragging = False
            return False
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            return self._mouse_down(event.pos)
        if event.type == pygame.MOUSEMOTION:
            if self._dragging:
                self.col = self._col_from_x(self.line, event.pos[0])
                self._blink = 0.0
            return False
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self._dragging = False
            return False
        if event.type == pygame.TEXTINPUT:
            self._insert(event.text)
            return True
        if event.type == pygame.KEYDOWN:
            return self._key_down(event)
        return False

    def _mouse_down(self, pos):
        if self.body.collidepoint(pos):
            i = min(self.n - 1, (pos[1] - self.body.y) // self.LINE_H)
            col = self._col_from_x(i, pos[0])
            now = pygame.time.get_ticks()
            double = now - self._last_click[0] < 400 and self._last_click[1] == (i, col)
            self._last_click = (now, (i, col))
            if double:
                start, end = self._word_bounds(i, col)
                self.line, self.anchor, self.col = i, start, end
                self._dragging = False
            else:
                shift = pygame.key.get_mods() & pygame.KMOD_SHIFT
                self._goto(i, col, extend=bool(shift))
                if self.anchor is None:
                    self.anchor = self.col          # start of a possible drag-selection
                self._dragging = True
            self._blink = 0.0
            return True
        # Clicking a problem jumps to it, like an IDE.
        listed = [i for i, e in enumerate(self.errors) if e]
        for k, i in enumerate(listed):
            if self.problem_rect(k).collidepoint(pos):
                self._goto(i, self.errors[i][1])
                return True
        return self.rect.collidepoint(pos)

    def _key_down(self, event):
        ctrl = event.mod & pygame.KMOD_CTRL
        shift = bool(event.mod & pygame.KMOD_SHIFT)
        text = self.lines[self.line]
        sel = self.selection()
        key = event.key
        if key == pygame.K_BACKSPACE:
            if self._delete_selection():
                self._changed()
            elif self.col:
                cut = 0 if ctrl else self.col - 1
                self.lines[self.line] = text[:cut] + text[self.col:]
                self.col = cut
                self._changed()
        elif key == pygame.K_DELETE:
            if self._delete_selection():
                self._changed()
            elif self.col < len(text):
                self.lines[self.line] = text[: self.col] + text[self.col + 1:]
                self._changed()
        elif key == pygame.K_LEFT:
            if sel and not shift:
                self._goto(self.line, sel[0])
            elif self.col == 0 and self.line > 0 and not shift:
                self._goto(self.line - 1, len(self.lines[self.line - 1]))
            else:
                self._goto(self.line, self.col - 1, extend=shift)
        elif key == pygame.K_RIGHT:
            if sel and not shift:
                self._goto(self.line, sel[1])
            elif self.col == len(text) and self.line < self.n - 1 and not shift:
                self._goto(self.line + 1, 0)
            else:
                self._goto(self.line, self.col + 1, extend=shift)
        elif key == pygame.K_UP:
            self._goto(self.line - 1, self.col)
        elif key == pygame.K_DOWN:
            self._goto(self.line + 1, self.col)
        elif key == pygame.K_TAB:
            nxt = (self.line + 1) % self.n
            self._goto(nxt, len(self.lines[nxt]))
        elif key == pygame.K_HOME:
            self._goto(self.line, 0, extend=shift)
        elif key == pygame.K_END:
            self._goto(self.line, len(text), extend=shift)
        elif ctrl and key == pygame.K_a:
            self.anchor, self.col = 0, len(text)
        elif ctrl and key == pygame.K_c:
            if sel:
                clipboard_put(self.selected_text())
        elif ctrl and key == pygame.K_x:
            if sel:
                clipboard_put(self.selected_text())
                self._delete_selection()
                self._changed()
        elif ctrl and key == pygame.K_v:
            clip = clipboard_get()
            if clip:
                self._insert(clip)
        else:
            return False
        self._blink = 0.0
        return True

    # -- drawing ---------------------------------------------------------------
    def update(self, dt):
        self._blink += dt

    def _keep_cursor_visible(self, i):
        area = self.text_area(i)
        cx = self.font.size(self.lines[i][: self.col])[0]
        if cx - self._scroll[i] > area.w - px(2):
            self._scroll[i] = cx - area.w + px(2)
        elif cx < self._scroll[i]:
            self._scroll[i] = cx
        text_w = self.font.size(self.lines[i])[0]
        self._scroll[i] = max(0, min(self._scroll[i], max(0, text_w - area.w + px(2))))

    def draw(self, surface):
        r = self.rect
        active = self.enabled and self.focused
        pygame.draw.rect(surface, config.EDITOR_BG, r)
        self._draw_header(surface, active)
        for i in range(self.n):
            self._draw_line(surface, i, active and i == self.line)
        self._draw_problems(surface)
        if self.footer_title:
            f = self.footer_rect
            pygame.draw.line(surface, config.EDITOR_BORDER, f.topleft, (f.right - 1, f.top), max(1, px(1)))
            draw_text(surface, self.footer_title, (f.x + px(10), f.y + self.PROB_HEADER_H // 2 + px(1)), 11,
                      config.TEXT_DIM, kind="bold", anchor="midleft")
        pygame.draw.rect(surface, config.EDITOR_BORDER, r, max(1, px(1)))

    def _draw_header(self, surface, active):
        """Title bar; its right end is left free for a run/stop button."""
        bar = self.header_rect
        pygame.draw.rect(surface, config.EDITOR_TABBAR, bar)
        pygame.draw.line(surface, config.ACCENT if active else config.EDITOR_GUTTER,
                         bar.topleft, (bar.right - 1, bar.top), max(2, px(2)))
        icon = self.small_mono.render("{}", True, config.SYN_NUMBER)
        label = get_font(13).render(self.title, True, config.TEXT if self.enabled else config.TEXT_DIM)
        surface.blit(icon, icon.get_rect(midleft=(bar.x + px(10), bar.centery)))
        surface.blit(label, label.get_rect(midleft=(bar.x + px(16) + icon.get_width(), bar.centery)))

    def _draw_line(self, surface, i, is_cur):
        lr = self.line_rect(i)
        if is_cur:
            pygame.draw.rect(surface, config.EDITOR_LINE_HL, lr)
        num_color = config.EDITOR_GUTTER_ACTIVE if is_cur else config.EDITOR_GUTTER
        draw_text(surface, str(i + 1), (lr.x + self.GUTTER_W - px(6), lr.centery), 14, num_color,
                  kind="mono", anchor="midright")

        def fade(c):
            return c if self.enabled else _dim(c, 0.55)

        x = lr.x + self.GUTTER_W + self.TEXT_PAD
        for chunk, color in ((self.prefixes[i], config.SYN_KEYWORD), (" = ", config.SYN_OPERATOR)):
            img = self.font.render(chunk, True, fade(color))
            surface.blit(img, img.get_rect(midleft=(x, lr.centery)))
            x += img.get_width()

        area = self.text_area(i)
        if is_cur:
            self._keep_cursor_visible(i)
        scroll = self._scroll[i]
        prev_clip = surface.get_clip()
        surface.set_clip(area.clip(prev_clip))
        text = self.lines[i]
        sel = self.selection() if i == self.line and self.enabled else None
        if sel:
            x0 = area.x - scroll + self.font.size(text[: sel[0]])[0]
            x1 = area.x - scroll + self.font.size(text[: sel[1]])[0]
            pygame.draw.rect(surface, config.EDITOR_SELECTION,
                             (x0, lr.y + px(4), x1 - x0, lr.h - px(8)))
        if text:
            cx = area.x - scroll
            for chunk, color in highlight(text):
                img = self.font.render(chunk, True, fade(color))
                surface.blit(img, img.get_rect(midleft=(cx, lr.centery)))
                cx += img.get_width()
        elif not is_cur:
            img = self.font.render("0", True, config.EDITOR_GUTTER)
            surface.blit(img, img.get_rect(midleft=(area.x, lr.centery)))

        err = self.errors[i]
        if err and self.enabled:
            start, end = error_span(text, err[1])
            x0 = area.x - scroll + self.font.size(text[:start])[0]
            if end <= len(text):
                x1 = area.x - scroll + self.font.size(text[:end])[0]
            else:
                x1 = area.x - scroll + self.font.size(text)[0] + self.font.size("0")[0]
            draw_squiggle(surface, x0, x1, lr.bottom - px(6))

        if is_cur and (self._blink % 1.0) < 0.55:
            cx = area.x - scroll + self.font.size(text[: self.col])[0]
            pygame.draw.line(surface, config.EDITOR_CURSOR, (cx, lr.y + px(5)), (cx, lr.bottom - px(6)),
                             max(2, px(2)))
        surface.set_clip(prev_clip)

    def _draw_problems(self, surface):
        r = self.rect
        top = self.body.bottom
        pygame.draw.line(surface, config.EDITOR_BORDER, (r.x, top), (r.right - 1, top), max(1, px(1)))
        head = draw_text(surface, "PROBLEMS", (r.x + px(10), top + self.PROB_HEADER_H // 2 + px(1)), 11,
                         config.TEXT_DIM, kind="bold", anchor="midleft")
        listed = [(i, e) for i, e in enumerate(self.errors) if e] if self.enabled else []
        if not listed:
            pr = self.problem_rect(0)
            ok = (pr.x + px(16), pr.centery)
            check = [(ok[0] - px(4), ok[1]), (ok[0] - px(1), ok[1] + px(3)), (ok[0] + px(4), ok[1] - px(3))]
            pygame.draw.lines(surface, config.SUCCESS, False, check, max(2, px(2)))
            draw_text(surface, "No problems", (pr.x + px(28), pr.centery), 12, config.TEXT_DIM, anchor="midleft")
            return

        badge = (head.right + px(12), head.centery)
        pygame.draw.circle(surface, config.SQUIGGLE, badge, px(7))
        draw_text(surface, str(len(listed)), badge, 11, (255, 255, 255), kind="bold", anchor="center")
        for k, (i, (msg, pos)) in enumerate(listed):
            pr = self.problem_rect(k)
            ic = (pr.x + px(16), pr.centery)
            d, lw = px(2), max(1, px(1))
            pygame.draw.circle(surface, config.SQUIGGLE, ic, px(5))
            pygame.draw.line(surface, (255, 255, 255), (ic[0] - d, ic[1] - d), (ic[0] + d, ic[1] + d), lw)
            pygame.draw.line(surface, (255, 255, 255), (ic[0] - d, ic[1] + d), (ic[0] + d, ic[1] - d), lw)
            loc = self.small_mono.render(f"Ln {i + 1}  ", True, config.EDITOR_GUTTER)
            surface.blit(loc, loc.get_rect(midleft=(pr.x + px(28), pr.centery)))
            text_x = pr.x + px(28) + loc.get_width()
            room = pr.right - px(8) - text_x
            size = 12
            while size > 9 and get_font(size).size(msg)[0] > room:
                size -= 1
            draw_text(surface, msg, (text_x, pr.centery), size, config.TEXT, anchor="midleft")


# --- icons ----------------------------------------------------------------------------
_icon_cache = {}


def icon_surface(name, size, color):
    """Anti-aliased vector icon (play, stop, grid, chev_left, chev_right, lock)."""
    key = (name, size, color)
    if key in _icon_cache:
        return _icon_cache[key]
    k = 4
    S = size * k
    big = pygame.Surface((S, S), pygame.SRCALPHA)

    def P(x, y):
        return (x * S, y * S)

    def thick_polyline(pts, w):
        pts = [P(*q) for q in pts]
        pygame.draw.lines(big, color, False, pts, max(1, round(w * S)))
        for q in pts:
            pygame.draw.circle(big, color, q, w * S / 2)

    if name == "play":
        pygame.draw.polygon(big, color, [P(0.30, 0.18), P(0.30, 0.82), P(0.82, 0.50)])
    elif name == "stop":
        pygame.draw.rect(big, color, pygame.Rect(P(0.26, 0.26), P(0.48, 0.48)), border_radius=round(0.08 * S))
    elif name == "grid":
        for gx in (0.22, 0.54):
            for gy in (0.22, 0.54):
                pygame.draw.rect(big, color, pygame.Rect(P(gx, gy), P(0.24, 0.24)), border_radius=round(0.05 * S))
    elif name == "chev_left":
        thick_polyline([(0.62, 0.18), (0.34, 0.50), (0.62, 0.82)], 0.11)
    elif name == "chev_right":
        thick_polyline([(0.38, 0.18), (0.66, 0.50), (0.38, 0.82)], 0.11)
    elif name == "lock":
        pygame.draw.circle(big, color, P(0.5, 0.42), 0.20 * S, round(0.08 * S))
        pygame.draw.rect(big, color, pygame.Rect(P(0.24, 0.44), P(0.52, 0.42)), border_radius=round(0.07 * S))
    elif name == "check":
        thick_polyline([(0.22, 0.52), (0.42, 0.72), (0.80, 0.30)], 0.12)
    else:
        raise ValueError(name)
    icon = pygame.transform.smoothscale(big, (size, size))
    _icon_cache[key] = icon
    return icon


class IconButton:
    """Small icon button. style 'circle' = filled round button, 'ghost' = icon only."""

    def __init__(self, rect, icon, style="ghost", color=config.TEXT):
        self.rect = pygame.Rect(rect)
        self.icon = icon
        self.style = style
        self.color = color
        self.enabled = True
        self.hover = False

    def handle_event(self, event):
        """Return 'click', 'disabled' (clicked while disabled) or None."""
        if event.type == pygame.MOUSEMOTION:
            self.hover = self.rect.collidepoint(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                return "click" if self.enabled else "disabled"
        return None

    def draw(self, surface):
        size = min(self.rect.w, self.rect.h)
        if self.style == "circle":
            if self.enabled:
                bg = config.BUTTON_PRIMARY_HOVER if self.hover else config.BUTTON_PRIMARY
            else:
                bg = config.BUTTON_DISABLED
            _draw_disc(surface, self.rect.center, size / 2, bg)
            icon_color = (255, 255, 255) if self.enabled else config.TEXT_FAINT
            icon = icon_surface(self.icon, round(size * 0.62), icon_color)
        else:
            if self.enabled and self.hover:
                pygame.draw.rect(surface, config.EDITOR_LINE_HL, self.rect, border_radius=px(3))
            icon = icon_surface(self.icon, size, self.color if self.enabled else config.TEXT_FAINT)
        surface.blit(icon, icon.get_rect(center=self.rect.center))


_disc_cache = {}


def _draw_disc(surface, center, radius, color):
    """Anti-aliased filled circle."""
    key = (round(radius * 2), color)
    if key not in _disc_cache:
        d = key[0]
        big = pygame.Surface((d * 4, d * 4), pygame.SRCALPHA)
        pygame.draw.circle(big, color, (d * 2, d * 2), d * 2)
        _disc_cache[key] = pygame.transform.smoothscale(big, (d, d))
    disc = _disc_cache[key]
    surface.blit(disc, disc.get_rect(center=center))

