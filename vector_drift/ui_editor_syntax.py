"""Syntax coloring and error underlining for the code editor."""

import re

import pygame

from . import config
from .config import px

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
