"""Paging rules for the level-select grid, kept free of pygame so they test plainly.

Every page holds PER_PAGE level cards (the 3x3 grid); paging is done with
arrows beside the grid, the arrow keys and the mouse wheel, never by giving
up a card slot. There is always at least one page, possibly empty. Paging
stops at either end: it never wraps round.
"""

import math

PER_PAGE = 9              # 3x3 grid, every slot a level
WHEEL_COOLDOWN = 0.2      # s of wheel quiet that ends one scroll gesture


def page_count(n_levels, per_page=PER_PAGE):
    """Number of pages for ``n_levels`` cards: at least one (empty) page."""
    return max(1, math.ceil(max(0, n_levels) / per_page))


def clamp_page(page, n_pages):
    """``page`` limited to 0 .. n_pages - 1 (0 when there are no pages)."""
    return max(0, min(page, n_pages - 1))


def can_prev(page):
    return page > 0


def can_next(page, n_pages):
    return page < n_pages - 1


def levels_on_page(levels, page, per_page=PER_PAGE):
    """The slice of ``levels`` shown on ``page`` (empty outside the pages)."""
    if page < 0:
        return []
    return list(levels[page * per_page:(page + 1) * per_page])


def page_of(levels, level_id, per_page=PER_PAGE):
    """Index of the page showing ``level_id``, or None if it is not listed."""
    try:
        return list(levels).index(level_id) // per_page
    except ValueError:
        return None


def restore_page(saved, level_id, levels, per_page=PER_PAGE):
    """The page to open the level select on.

    ``saved`` is (page, level_id) as last stored by the level select, or None.
    If the current level is still the one stored with that page, the player
    comes back to the page they left (e.g. after the Shop). Otherwise they
    played on to another level, so its page is shown. With neither, the
    saved page (clamped) or the first page.
    """
    n_pages = page_count(len(levels), per_page)
    if saved is not None and saved[1] == level_id:
        return clamp_page(saved[0], n_pages)
    page = page_of(levels, level_id, per_page)
    if page is not None:
        return page
    return clamp_page(saved[0], n_pages) if saved is not None else 0


def wheel_step(wheel_y, now, last_wheel, cooldown=WHEEL_COOLDOWN):
    """Page step for one mouse-wheel event: (step, new last_wheel).

    ``wheel_y`` > 0 is scrolling up (previous page, -1), < 0 down (next page,
    +1). ``now`` and ``last_wheel`` are times in seconds (``last_wheel`` is
    None before any wheel event). Wheel events closer than ``cooldown`` to the
    previous one belong to the same gesture (a touchpad flick or a fast spin
    sends many), so only the first event of a gesture turns a page. The
    caller still ignores a step toward a disabled direction.
    """
    if not wheel_y:
        return 0, last_wheel
    starts_gesture = last_wheel is None or now - last_wheel >= cooldown
    step = (-1 if wheel_y > 0 else 1) if starts_gesture else 0
    return step, now
