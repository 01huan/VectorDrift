"""Cursor, selection and text edits of the code editor."""


class CodeEditTextMixin:

    def set_lines(self, texts, record=True):
        """Replace the text (cursor to the end of Fx).

        With ``record`` every line that changes gets one undo step; pass False
        when loading a starting text that should not be undoable.
        """
        old, old_state = list(self.lines), self._state()
        self.lines = [t[: self.max_len] for t in texts]
        self.line = 0
        self.col = len(self.lines[0])
        self.anchor = None
        if record:
            for i, (was, now) in enumerate(zip(old, self.lines)):
                if was != now:
                    before = old_state if i == old_state[3] else (was, len(was), None, i)
                    self._push(i, before[:3], (now, len(now), None))
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
        self._end_step()
