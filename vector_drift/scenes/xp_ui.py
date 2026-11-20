"""The player level on screen: the XP bar (level select, win screen) and its row."""

import pygame

from .. import config
from ..config import px
from ..ui import draw_text
from ..xp import level_progress

XP_FILL = config.ACCENT
XP_TRACK = config.PANEL_EDGE
ROW_BAR_W, ROW_BAR_H = 140, 8       # the level select bar (logical px)


def xp_text(into, needed):
    return f"{into} / {needed} XP"


def bar_fill_width(rect, fraction):
    """Filled width of an XP bar: rounded ends, so a sliver is at least as wide as tall."""
    fraction = max(0.0, min(1.0, float(fraction)))
    if fraction <= 0:
        return 0
    return min(rect.w, max(rect.h, round(rect.w * fraction)))


def draw_xp_bar(surface, rect, fraction):
    """A rounded track with ``fraction`` (0-1) of it filled."""
    rect = pygame.Rect(rect)
    pygame.draw.rect(surface, XP_TRACK, rect, border_radius=rect.h // 2)
    width = bar_fill_width(rect, fraction)
    if width:
        pygame.draw.rect(surface, XP_FILL, (rect.x, rect.y, width, rect.h), border_radius=rect.h // 2)
    return rect


def draw_level_row(surface, total_xp, pos):
    """"Lv N", a short bar and "into / needed XP" in a row from ``pos`` (top left).

    Returns the rect the whole row covers.
    """
    progress = level_progress(int(total_xp or 0))
    label = draw_text(surface, f"Lv {progress.level}", pos, 16, config.TEXT, kind="bold")
    bar = pygame.Rect(label.right + px(10), label.centery - px(ROW_BAR_H) // 2,
                      px(ROW_BAR_W), px(ROW_BAR_H))
    draw_xp_bar(surface, bar, progress.into / progress.needed)
    numbers = draw_text(surface, xp_text(progress.into, progress.needed),
                        (bar.right + px(10), label.centery), 13, config.TEXT_DIM, anchor="midleft")
    return label.union(bar).union(numbers)
