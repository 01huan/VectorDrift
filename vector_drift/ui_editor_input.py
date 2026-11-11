"""Mouse and keyboard input for the code editor."""

import pygame

from .ui_editor_history import STEP_BREAKERS


class CodeEditorInputMixin:

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
                self._end_step()
            return False
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self._dragging = False
            return False
        if event.type == pygame.TEXTINPUT:
            self._type(event.text)
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
                self._end_step()
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

    def _wrap_selection(self):
        """"(" over a selection: wrap it in parentheses and keep it selected."""
        start, end = self.selection()
        text = self.lines[self.line]
        if len(text) + 2 > self.max_len:
            return
        before = self._state()
        forward = self.col > self.anchor
        self.lines[self.line] = text[:start] + "(" + text[start:end] + ")" + text[end:]
        self._changed()
        self.anchor, self.col = (start + 1, end + 1) if forward else (end + 1, start + 1)
        self._record(before)

    def _auto_closes(self):
        """"(" with nothing or a space after the cursor gets its ")" too (if both fit)."""
        text = self.lines[self.line]
        return (self.selection() is None and len(text) + 2 <= self.max_len
                and text[self.col:self.col + 1] in ("", " "))

    def _steps_over_close_paren(self):
        """")" just before a ")" moves past it, unless the line is short of one."""
        text = self.lines[self.line]
        return (self.selection() is None and text[self.col:self.col + 1] == ")"
                and text.count("(") == text.count(")"))

    def _type(self, chars):
        """Typed text: one character grows the open "insert" step."""
        if chars == "(" and self.selection():
            self._wrap_selection()
            return
        if chars == ")" and self._steps_over_close_paren():
            self.col += 1
            self._blink = 0.0
            return
        before = self._state()
        replacing = self.selection() is not None
        if chars == "(" and self._auto_closes():
            text = self.lines[self.line]
            self.lines[self.line] = text[:self.col] + "()" + text[self.col:]
            self.col += 1                       # cursor between the pair
            self._changed()
        else:
            self._insert(chars)
        single = len(chars) == 1
        self._record(before, "insert" if single else None, join=not replacing)
        if single and chars in STEP_BREAKERS:
            self.history[self.line].open = None

    def _key_down(self, event):
        ctrl = event.mod & pygame.KMOD_CTRL
        shift = bool(event.mod & pygame.KMOD_SHIFT)
        text = self.lines[self.line]
        sel = self.selection()
        key = event.key
        before = self._state()
        if key == pygame.K_BACKSPACE:
            if self._delete_selection():
                self._changed()
                self._record(before)
            elif self.col:
                cut = 0 if ctrl else self.col - 1
                end = self.col + 1 if not ctrl and text[cut:self.col + 1] == "()" else self.col
                self.lines[self.line] = text[:cut] + text[end:]     # "(|)" loses both
                self.col = cut
                self._changed()
                self._record(before, None if ctrl else "delete")
        elif key == pygame.K_DELETE:
            if self._delete_selection():
                self._changed()
                self._record(before)
            elif self.col < len(text):
                self.lines[self.line] = text[: self.col] + text[self.col + 1:]
                self._changed()
                self._record(before, "delete")
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
            self._end_step()
        elif ctrl and key == pygame.K_c:
            if sel:
                from . import ui as _ui; _ui.clipboard_put(self.selected_text())
        elif ctrl and key == pygame.K_x:
            if sel:
                from . import ui as _ui; _ui.clipboard_put(self.selected_text())
                self._delete_selection()
                self._changed()
                self._record(before)
        elif ctrl and key == pygame.K_v:
            from . import ui as _ui; clip = _ui.clipboard_get()
            if clip:
                self._insert(clip)
                self._record(before)
        elif ctrl and key in (pygame.K_z, pygame.K_y):
            if self.focused:            # Ctrl+Z undo; Ctrl+Shift+Z / Ctrl+Y redo
                self._undo(redo=key == pygame.K_y or shift)
        else:
            return False
        self._blink = 0.0
        return True
