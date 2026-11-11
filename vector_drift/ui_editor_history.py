"""Undo / redo history of the code editor (one stack per line)."""

HISTORY_LIMIT = 100            # undo steps kept per editor line
STEP_BREAKERS = " +-*/"        # typing one of these ends the current undo step


class _Step:
    """One undo step on one line: (text, col, anchor) before and after it."""
    __slots__ = ("before", "after")

    def __init__(self, before, after):
        self.before, self.after = before, after


class LineHistory:
    """Undo / redo stacks of one editor line."""

    def __init__(self):
        self.undo = []
        self.redo = []
        self.open = None       # "insert" / "delete" while the top step can still grow


class CodeEditorHistoryMixin:

    def _state(self):
        """(text, col, anchor, line) of the current line."""
        return self.lines[self.line], self.col, self.anchor, self.line

    def _push(self, i, before, after, kind=None, join=False):
        """Add an undo step on line `i`, or grow the open one of the same kind."""
        h = self.history[i]
        h.redo.clear()
        if join and kind is not None and h.open == kind and h.undo:
            h.undo[-1].after = after
        else:
            h.undo.append(_Step(before, after))
            del h.undo[:-HISTORY_LIMIT]
        h.open = kind

    def _record(self, before, kind=None, join=True):
        """Store the edit that turned `before` (from _state) into the current line."""
        text, col, anchor, line = self._state()
        if text != before[0]:
            self._push(line, before[:3], (text, col, anchor), kind, join)

    def _end_step(self):
        """The cursor moved: the next edit starts a new undo step."""
        for h in self.history:
            h.open = None

    def _undo(self, redo=False):
        h = self.history[self.line]
        src, dst = (h.redo, h.undo) if redo else (h.undo, h.redo)
        if not src:
            return
        step = src.pop()
        dst.append(step)
        h.open = None
        text, col, anchor = step.after if redo else step.before
        self.lines[self.line] = text
        self.col = col
        self._changed()                 # same path as typing: owner re-checks the text
        self.anchor = anchor
