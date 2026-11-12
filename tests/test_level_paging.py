"""Level-select paging rules: plain functions, no pygame."""

import pytest

from vector_drift.level_pages import (
    PER_PAGE, WHEEL_COOLDOWN, can_next, can_prev, clamp_page, levels_on_page, page_count,
    page_of, restore_page, wheel_step,
)


def ids(n):
    return list(range(1, n + 1))


def test_nine_levels_per_page():
    assert PER_PAGE == 9


@pytest.mark.parametrize("n_levels, pages", [(0, 1), (1, 1), (9, 1), (10, 2), (18, 2), (19, 3), (24, 3)])
def test_page_count(n_levels, pages):
    assert page_count(n_levels, PER_PAGE) == pages


@pytest.mark.parametrize("n_levels, page, shown", [
    (0, 0, []),
    (9, 0, ids(9)),
    (10, 0, ids(9)),
    (10, 1, [10]),
    (18, 1, list(range(10, 19))),
    (19, 1, list(range(10, 19))),
    (19, 2, [19]),
    (19, 3, []),
    (19, -1, []),
])
def test_levels_on_page(n_levels, page, shown):
    assert levels_on_page(ids(n_levels), page, PER_PAGE) == shown


@pytest.mark.parametrize("n_levels", [0, 9, 10, 18, 19])
def test_pages_cover_every_level_once(n_levels):
    levels = ids(n_levels)
    flat = [lid for p in range(page_count(len(levels), PER_PAGE))
            for lid in levels_on_page(levels, p, PER_PAGE)]
    assert flat == levels


@pytest.mark.parametrize("page, n_pages, clamped", [
    (-5, 3, 0), (-1, 3, 0), (0, 3, 0), (1, 3, 1), (2, 3, 2), (3, 3, 2), (99, 3, 2),
    (0, 1, 0), (4, 1, 0), (-1, 1, 0), (2, 0, 0),
])
def test_clamp_page(page, n_pages, clamped):
    assert clamp_page(page, n_pages) == clamped


@pytest.mark.parametrize("page, n_pages, prev, nxt", [
    (0, 3, False, True),      # first page
    (1, 3, True, True),       # middle page
    (2, 3, True, False),      # last page
    (0, 1, False, False),     # only one page
])
def test_can_prev_and_can_next(page, n_pages, prev, nxt):
    assert can_prev(page) is prev
    assert can_next(page, n_pages) is nxt


def test_page_of():
    levels = ids(19)
    assert page_of(levels, 1, PER_PAGE) == 0
    assert page_of(levels, 9, PER_PAGE) == 0
    assert page_of(levels, 10, PER_PAGE) == 1
    assert page_of(levels, 19, PER_PAGE) == 2
    assert page_of(levels, 20, PER_PAGE) is None
    assert page_of(levels, -3, PER_PAGE) is None


def test_restore_page_keeps_the_page_the_player_left():
    levels = ids(24)
    # Browsed to page 2 while level 1 was the current one (e.g. a Shop round trip).
    assert restore_page((2, 1), 1, levels, PER_PAGE) == 2


def test_restore_page_follows_a_new_level():
    levels = ids(24)
    # Left from page 0 on level 9, then "next level" took the player to level 10.
    assert restore_page((0, 9), 10, levels, PER_PAGE) == 1
    # Nothing saved yet: the current level's page.
    assert restore_page(None, 20, levels, PER_PAGE) == 2


def test_restore_page_falls_back_and_clamps():
    levels = ids(24)
    assert restore_page(None, None, levels, PER_PAGE) == 0
    assert restore_page(None, 1001, levels, PER_PAGE) == 0          # custom level: not listed
    assert restore_page((2, 5), 1001, levels, PER_PAGE) == 2
    assert restore_page((7, 5), 5, levels, PER_PAGE) == 2            # fewer pages now


# --- mouse wheel ----------------------------------------------------------------------
def test_wheel_down_is_next_and_up_is_previous():
    assert wheel_step(-1, 10.0, None) == (1, 10.0)
    assert wheel_step(1, 10.0, None) == (-1, 10.0)
    assert wheel_step(0, 10.0, None) == (0, None)                    # sideways only


def test_wheel_cooldown_is_about_a_fifth_of_a_second():
    assert 0.15 <= WHEEL_COOLDOWN <= 0.25


def test_one_gesture_turns_one_page():
    # A touchpad flick: wheel events every 50 ms for half a second.
    last, turned = None, 0
    for k in range(10):
        step, last = wheel_step(-1, 5.0 + 0.05 * k, last)
        turned += step
    assert turned == 1


def test_a_new_gesture_after_the_cooldown_turns_again():
    step, last = wheel_step(-1, 1.0, None)
    assert step == 1
    step, last = wheel_step(-1, 1.0 + WHEEL_COOLDOWN / 2, last)
    assert step == 0
    step, last = wheel_step(-1, last + WHEEL_COOLDOWN + 0.01, last)
    assert step == 1
