"""Level-select pages: nine level cards per page, arrows beside the grid, dots below."""

from types import SimpleNamespace

import pygame
import pytest

from vector_drift import config
from vector_drift.config import px
from vector_drift.data import all_levels
from vector_drift.level_pages import WHEEL_COOLDOWN
from vector_drift.scenes import levels as levels_module
from vector_drift.scenes.base import SceneManager
from vector_drift.scenes.levels import LevelSelectScene

pytestmark = pytest.mark.usefixtures("pygame_display")


def _manager():
    played = []
    audio = SimpleNamespace(play=lambda name, *a, **k: played.append(name),
                            start_loop=lambda *a, **k: None, stop_loop=lambda *a, **k: None)
    manager = SceneManager(audio)
    manager.played = played
    return manager


def _scene(manager=None):
    manager = manager or _manager()
    scene = LevelSelectScene(manager)
    manager.switch(scene)
    return scene


def _fake_levels(monkeypatch, highest, planned=0):
    fake = [SimpleNamespace(id=i, name=f"Level {i}") for i in range(1, highest + 1)]
    monkeypatch.setattr(levels_module, "all_levels", lambda: fake)
    monkeypatch.setattr(config, "PLANNED_LEVELS", planned)


def _grid_cells():
    m = levels_module
    left, top = m.grid_origin()
    return [(px(left + c * (m.CARD_W + m.GAP)), px(top + r * (m.CARD_H + m.GAP)))
            for r in range(3) for c in range(m.COLS)]


def _walk_pages(scene):
    """Visit every page with the ">" arrow; return the level ids on each page."""
    cells = _grid_cells()
    pages = []
    while True:
        assert [r.topleft for _, r in scene.cards] == cells[:len(scene.cards)]  # slots in order
        pages.append([lid for lid, _ in scene.cards])
        if not scene.next_arrow.enabled:
            return pages
        _click(scene, scene.next_arrow.rect.center)


def _assert_covers(pages, highest):
    flat = [lid for page in pages for lid in page]
    assert flat == list(range(1, highest + 1))


def _click(scene, pos):
    scene.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=pos))


def _key(scene, key):
    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key, mod=0, unicode=""))


def _wheel(scene, y, now, monkeypatch):
    monkeypatch.setattr(scene, "_now", lambda: now)
    scene.handle_event(pygame.event.Event(pygame.MOUSEWHEEL, x=0, y=y, flipped=False))


# --- every slot is a level -------------------------------------------------------------
def test_real_levels_show_up_to_the_planned_count():
    highest = max(lv.id for lv in all_levels())
    pages = _walk_pages(_scene())
    _assert_covers(pages, max(highest, config.PLANNED_LEVELS))


def test_planned_count_of_24_gives_three_full_width_pages():
    assert config.PLANNED_LEVELS == 24
    pages = _walk_pages(_scene())
    assert [p[0] for p in pages] == [1, 10, 19]
    assert [len(p) for p in pages] == [9, 9, 6]


@pytest.mark.parametrize("planned, highest, shown", [
    (0, 8, 8), (24, 8, 24), (24, 30, 30), (5, 8, 8), (9, 4, 9),
])
def test_planned_count_and_highest_id_both_extend_the_range(monkeypatch, planned, highest, shown):
    _fake_levels(monkeypatch, highest, planned)
    _assert_covers(_walk_pages(_scene()), shown)


@pytest.mark.parametrize("highest, n_pages", [(1, 1), (9, 1), (10, 2), (18, 2), (19, 3), (30, 4)])
def test_nine_levels_per_page(monkeypatch, highest, n_pages):
    _fake_levels(monkeypatch, highest)
    scene = _scene()
    pages = _walk_pages(scene)
    assert len(pages) == n_pages == scene.page_count
    assert all(len(p) == 9 for p in pages[:-1])
    _assert_covers(pages, highest)


def test_level_seven_is_playable_and_later_ones_are_coming_soon():
    scene = _scene()
    played = scene.manager.played
    assert 7 in dict(scene.cards) and 7 in scene.levels
    scene._next_page()                                 # page 2: levels 10.. are coming soon
    coming = next(lid for lid, _ in scene.cards if lid not in scene.levels)
    _click(scene, dict(scene.cards)[coming].center)
    assert played[-1] == "error"                       # locked cards keep their behaviour
    assert scene.page == 1


# --- arrows ----------------------------------------------------------------------------
def test_arrows_enable_by_page(monkeypatch):
    _fake_levels(monkeypatch, 24)
    scene = _scene()
    states = []
    for _ in range(scene.page_count):
        states.append((scene.prev_arrow.enabled, scene.next_arrow.enabled))
        scene._next_page()
    assert states == [(False, True), (True, True), (True, False)]


def test_one_page_disables_both_arrows(monkeypatch):
    _fake_levels(monkeypatch, 9)
    scene = _scene()
    assert scene.page_count == 1
    assert not scene.prev_arrow.enabled and not scene.next_arrow.enabled


def test_clicking_the_arrows_turns_the_page(monkeypatch):
    _fake_levels(monkeypatch, 24)
    scene = _scene()
    _click(scene, scene.next_arrow.rect.center)
    assert scene.page == 1
    _click(scene, scene.prev_arrow.rect.center)
    assert scene.page == 0


def test_a_disabled_arrow_does_nothing(monkeypatch):
    _fake_levels(monkeypatch, 24)
    scene = _scene()
    played = scene.manager.played
    played.clear()
    _click(scene, scene.prev_arrow.rect.center)          # first page: "<" is off
    assert scene.page == 0 and played == []
    scene.handle_event(pygame.event.Event(pygame.MOUSEMOTION, pos=scene.prev_arrow.rect.center,
                                          rel=(0, 0), buttons=(0, 0, 0)))
    assert not scene.prev_arrow.hover                    # no hover either
    scene.page = 2
    scene._rebuild_cards()
    _click(scene, scene.next_arrow.rect.center)          # last page: ">" is off, no wrap
    assert scene.page == 2


def test_the_hit_strip_is_wider_and_taller_than_the_drawn_arrow():
    scene = _scene()
    for arrow in (scene.prev_arrow, scene.next_arrow):
        glyph = arrow.glyph_rect()
        assert arrow.rect.contains(glyph)
        assert arrow.rect.w > glyph.w and arrow.rect.h > 2 * glyph.h


def test_arrows_sit_at_the_screen_sides_centred_on_the_grid():
    scene = _scene()
    grid = scene.grid_rect()
    for arrow in (scene.prev_arrow, scene.next_arrow):
        assert abs(arrow.rect.centery - grid.centery) <= 1
        assert not arrow.rect.colliderect(grid)
    assert scene.prev_arrow.rect.left < px(40)
    assert scene.next_arrow.rect.right > config.WINDOW_W - px(40)
    assert scene.prev_arrow.rect.right <= grid.left and scene.next_arrow.rect.left >= grid.right


def test_arrows_do_not_overlap_the_other_buttons():
    scene = _scene()
    others = [scene.menu_button, scene.shop_button, scene.editor_button, scene.tutorial_button,
              scene.inventory_button]
    for arrow in (scene.prev_arrow, scene.next_arrow):
        assert 0 <= arrow.rect.left and arrow.rect.right <= config.WINDOW_W
        for button in others:
            assert not arrow.rect.colliderect(button.rect), button
        for _, card in scene.cards:
            assert not arrow.rect.colliderect(card)


def test_hover_brightens_an_enabled_arrow(monkeypatch):
    _fake_levels(monkeypatch, 24)
    scene = _scene()
    motion = lambda pos: scene.handle_event(pygame.event.Event(  # noqa: E731
        pygame.MOUSEMOTION, pos=pos, rel=(0, 0), buttons=(0, 0, 0)))
    motion(scene.next_arrow.rect.center)
    assert scene.next_arrow.hover
    assert scene.next_arrow.color() != levels_module.PageArrow(1, scene.next_arrow.rect).color()
    motion((config.WINDOW_W // 2, px(20)))
    assert not scene.next_arrow.hover


# --- keys and wheel --------------------------------------------------------------------
def test_arrow_keys_turn_pages_and_stop_at_the_ends(monkeypatch):
    _fake_levels(monkeypatch, 24)
    scene = _scene()
    _key(scene, pygame.K_LEFT)
    assert scene.page == 0
    for expected in (1, 2, 2):
        _key(scene, pygame.K_RIGHT)
        assert scene.page == expected
    _key(scene, pygame.K_LEFT)
    assert scene.page == 1


def test_wheel_down_is_next_and_up_is_previous(monkeypatch):
    _fake_levels(monkeypatch, 24)
    scene = _scene()
    _wheel(scene, -1, 10.0, monkeypatch)
    assert scene.page == 1
    _wheel(scene, 1, 11.0, monkeypatch)
    assert scene.page == 0
    _wheel(scene, 1, 12.0, monkeypatch)                  # disabled direction: no wrap
    assert scene.page == 0


def test_a_fast_scroll_turns_only_one_page(monkeypatch):
    _fake_levels(monkeypatch, 30)
    scene = _scene()
    for k in range(8):
        _wheel(scene, -1, 3.0 + k * WHEEL_COOLDOWN / 4, monkeypatch)
    assert scene.page == 1


# --- page dots -------------------------------------------------------------------------
def test_page_dots_sit_centred_below_the_grid(monkeypatch):
    _fake_levels(monkeypatch, 24)
    scene = _scene()
    grid = scene.grid_rect()
    for page in range(3):
        scene.page = page
        scene._rebuild_cards()
        dots = scene.page_dots()
        assert [filled for _, filled in dots] == [k == page for k in range(3)]
        xs = [c[0] for c, _ in dots]
        assert abs((xs[0] + xs[-1]) / 2 - grid.centerx) <= 1
        assert all(grid.bottom < c[1] < config.WINDOW_H for c, _ in dots)


def test_clicking_a_dot_does_nothing(monkeypatch):
    _fake_levels(monkeypatch, 24)
    scene = _scene()
    _click(scene, scene.page_dots()[2][0])
    assert scene.page == 0


# --- remembered page -------------------------------------------------------------------
def test_coming_back_shows_the_page_the_player_left(monkeypatch):
    _fake_levels(monkeypatch, 24)
    manager = _manager()
    scene = _scene(manager)
    scene._next_page()
    scene._next_page()
    assert _scene(manager).page == 2                     # e.g. back from the Shop


def test_coming_back_from_a_level_shows_its_page(monkeypatch):
    _fake_levels(monkeypatch, 24)
    manager = _manager()
    _scene(manager)                                      # left on page 0 ...
    manager.session.level_id = 12                        # ... then played on to level 12
    assert _scene(manager).page == 1


def test_starting_a_level_remembers_its_page(monkeypatch):
    from vector_drift.scenes import game as game_module
    _fake_levels(monkeypatch, 24)
    monkeypatch.setattr(game_module, "GameScene", lambda manager: SimpleNamespace(music=None))
    manager = _manager()
    scene = _scene(manager)
    scene._next_page()
    scene._start(14)
    assert manager.session.level_select_page == (1, 14)


def test_every_page_draws(monkeypatch):
    scene = _scene()
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    for _ in range(scene.page_count):
        scene.prev_arrow.hover = scene.prev_arrow.enabled
        scene.draw(surface)
        scene._next_page()
