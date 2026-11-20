"""The player level on screen: the XP bar (level select, win screen) and its row."""

import pygame

from .. import config
from ..config import px
from ..ui import draw_text
from ..xp import level_progress, xp_to_next

XP_FILL = config.ACCENT
XP_TRACK = config.PANEL_EDGE
ROW_BAR_W, ROW_BAR_H = 140, 8       # the level select bar (logical px)
XP_BAR_S = 1.0                      # the win screen bar grows for this long (ease-out)


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


def _ease_out(x):
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


def xp_bar_state(before_total, after_total, t, duration=XP_BAR_S):
    """(level, fraction filled) of a bar growing from ``before_total`` to ``after_total`` XP.

    ``t`` seconds in, eased out over ``duration``. With a level up the bar
    first fills its old level, then grows from 0 in the new one (levels
    jumped in between are not shown); each part takes time in proportion to
    how far it grows.
    """
    start = level_progress(max(0, int(before_total)))
    end = level_progress(max(int(before_total), int(after_total)))
    from_fraction = start.into / start.needed
    to_fraction = end.into / end.needed
    if end.level == start.level:
        first, second = to_fraction - from_fraction, 0.0
    else:
        first, second = 1.0 - from_fraction, to_fraction
    total = first + second
    if total <= 0:
        return end.level, to_fraction
    eased = _ease_out(t / duration if duration > 0 else 1.0)
    if eased >= 1.0:
        return end.level, to_fraction
    covered = total * eased
    if covered < first:
        return start.level, from_fraction + covered
    return end.level, min(to_fraction, covered - first)


def draw_xp_bar_row(surface, card, y, level, fraction):
    """The win screen's bar row across ``card`` at ``y``: "Lv N", the bar, the numbers under it.

    Returns the bar's rect.
    """
    needed = xp_to_next(level)
    draw_text(surface, f"Lv {level}", (card.x + px(48), y), 17, config.TEXT, kind="bold",
              anchor="midleft")
    bar = pygame.Rect(card.x + px(110), y - px(5), card.w - px(110) - px(48), px(10))
    draw_xp_bar(surface, bar, fraction)
    draw_text(surface, xp_text(round(fraction * needed), needed), (bar.right, bar.bottom + px(4)), 13,
              config.TEXT_DIM, anchor="topright")
    return bar
