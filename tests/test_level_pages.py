"""Level-select pages cover 1..highest level id exactly once, inside a 3x3 grid."""

from types import SimpleNamespace

import pygame
import pytest

from vector_drift import config
from vector_drift.config import px
from vector_drift.data import all_levels
from vector_drift.scenes import levels as levels_module
from vector_drift.scenes.base import SceneManager
from vector_drift.scenes.levels import LevelSelectScene

pytestmark = pytest.mark.usefixtures("pygame_display")


def _scene():
    audio = SimpleNamespace(play=lambda *a, **k: None, start_loop=lambda *a, **k: None,
                            stop_loop=lambda *a, **k: None)
    manager = SceneManager(audio)
    scene = LevelSelectScene(manager)
    manager.switch(scene)
    return scene


def _grid_cells():
    m = levels_module
    grid_w = m.COLS * m.CARD_W + (m.COLS - 1) * m.GAP
    left, top = (1280 - grid_w) // 2, 200
    return {(px(left + c * (m.CARD_W + m.GAP)), px(top + r * (m.CARD_H + m.GAP)))
            for r in range(3) for c in range(m.COLS)}


def _walk_pages(scene):
    """Visit every page with the Next button; return the level ids on each page."""
    cells = _grid_cells()
    pages = []
    while True:
        rects = [rect for _, rect in scene.cards]
        rects += [b.rect for b in (scene.prev_button, scene.next_button) if b is not None]
        assert len(rects) <= 9
        assert len({r.topleft for r in rects}) == len(rects)       # no two in one slot
        assert {r.topleft for r in rects} <= cells                 # all inside the 3x3 grid
        assert (scene.prev_button is None) == (scene.page == 0)
        pages.append([lid for lid, _ in scene.cards])
        if scene.next_button is None:
            return pages
        scene._next_page()


def _assert_covers(pages, highest):
    flat = [lid for page in pages for lid in page]
    assert flat == list(range(1, highest + 1))


def test_real_levels_show_up_to_the_planned_count():
    highest = max(lv.id for lv in all_levels())
    scene = _scene()
    pages = _walk_pages(scene)
    _assert_covers(pages, max(highest, config.PLANNED_LEVELS))


def test_planned_count_of_24_gives_four_pages():
    assert config.PLANNED_LEVELS == 24
    pages = _walk_pages(_scene())
    assert [p[0] for p in pages] == [1, 9, 16, 23]


@pytest.mark.parametrize("planned, highest, shown", [
    (0, 8, 8), (24, 8, 24), (24, 30, 30), (5, 8, 8), (9, 4, 9),
])
def test_planned_count_and_highest_id_both_extend_the_range(monkeypatch, planned, highest, shown):
    fake = [SimpleNamespace(id=i, name=f"Level {i}") for i in range(1, highest + 1)]
    monkeypatch.setattr(levels_module, "all_levels", lambda: fake)
    monkeypatch.setattr(config, "PLANNED_LEVELS", planned)
    _assert_covers(_walk_pages(_scene()), shown)


def test_single_page_has_no_page_buttons(monkeypatch):
    monkeypatch.setattr(config, "PLANNED_LEVELS", 0)
    scene = _scene()
    assert len(_walk_pages(scene)) == 1
    assert scene.next_button is None and scene.prev_button is None


@pytest.mark.parametrize("highest", [1, 8, 9, 10, 16, 17, 20, 30])
def test_pages_cover_every_id_once(monkeypatch, highest):
    fake = [SimpleNamespace(id=i, name=f"Level {i}") for i in range(1, highest + 1) if i % 4]
    fake.append(SimpleNamespace(id=highest, name="Last"))
    monkeypatch.setattr(levels_module, "all_levels", lambda: fake)
    monkeypatch.setattr(config, "PLANNED_LEVELS", 0)
    scene = _scene()
    pages = _walk_pages(scene)
    _assert_covers(pages, highest)
    assert (len(pages) == 1) == (highest <= 9)

    # Walking back with Previous returns to the first page.
    while scene.prev_button is not None:
        scene._prev_page()
    assert scene.page == 0


def test_every_page_draws(monkeypatch):
    scene = _scene()
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    for _ in range(scene.page_count):
        scene.draw(surface)
        scene._next_page()
