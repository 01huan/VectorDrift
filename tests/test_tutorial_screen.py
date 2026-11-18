"""The tutorial screen: the Basics walkthrough shrunk into a frame, the header and the element list."""

from types import SimpleNamespace

import pygame
import pytest

from vector_drift import config
from vector_drift.config import px
from vector_drift.scenes import tutorial_screen as ts
from vector_drift.scenes.base import SceneManager
from vector_drift.scenes.game import GameScene
from vector_drift.scenes.game_layout import FLIGHT, SETUP
from vector_drift.scenes.levels import LevelSelectScene
from vector_drift.scenes.tutorial_basics import BasicsScene
from vector_drift.scenes.tutorial_screen import TutorialScene
from vector_drift.tutorial import tutorial

pytestmark = pytest.mark.usefixtures("pygame_display")


def _manager():
    audio = SimpleNamespace(play=lambda *a, **k: None, start_loop=lambda *a, **k: None,
                            stop_loop=lambda *a, **k: None, toggle_mute=lambda: None)
    mgr = SceneManager(audio)
    mgr.screen = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    return mgr


def _open(index=0, mgr=None):
    mgr = mgr or _manager()
    scene = TutorialScene(mgr, index)
    mgr.switch(scene)
    return mgr, scene


def _click(scene, pos):
    for kind in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
        scene.handle_event(pygame.event.Event(kind, button=1, pos=pos))


def _key(scene, key):
    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key, mod=0, unicode="", scancode=0))


def _outer(scene, inner_pos):
    """Where a point of the full-size walkthrough shows inside the frame."""
    f = scene.frame
    return (round(f.x + inner_pos[0] * f.w / config.WINDOW_W),
            round(f.y + inner_pos[1] * f.h / config.WINDOW_H))


def _type(inner, fx, fy):
    inner.editor.set_lines([fx, fy])
    inner._on_text_change(inner.editor)


def _draw(scene):
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    scene.draw(surface)
    return surface


# --- layout ----------------------------------------------------------------------------------
def test_layout_in_logical_px():
    assert ts.FRAME == (20, 66, 1030, 580)
    assert ts.LIST == (1066, 66, 194, 580)
    _, scene = _open()
    assert scene.frame == pygame.Rect(px(20), px(66), px(1030), px(580))
    assert scene.list_rect == pygame.Rect(px(1066), px(66), px(194), px(580))
    # About 80.5% of the full game screen, keeping its shape.
    assert scene.frame.w / config.WINDOW_W == pytest.approx(0.805, abs=0.002)
    assert scene.frame.h / config.WINDOW_H == pytest.approx(0.805, abs=0.002)


def test_header_shows_the_step_and_exit_lines_up_with_the_frame(monkeypatch):
    drawn = []
    real = ts.draw_text
    monkeypatch.setattr(ts, "draw_text", lambda s, text, *a, **k: drawn.append(text) or real(s, text, *a, **k))
    _, scene = _open(1)
    _draw(scene)
    assert "Tutorial 2 / 4" in drawn
    assert scene.exit_button.rect.right == scene.frame.right
    assert scene.exit_button.rect.bottom <= scene.frame.top


def test_the_walkthrough_inside_has_no_exit_button_of_its_own():
    _, scene = _open()
    assert isinstance(scene.inner, BasicsScene) and not scene.inner.show_exit
    # Where the inner Exit used to be (top right of the full screen) nothing happens.
    _click(scene, _outer(scene, scene.inner.exit_button.rect.center))
    assert scene.manager.scene is scene


def test_the_list_follows_the_guide_categories():
    _, scene = _open()
    guide = tutorial().guide
    assert [name for name, _ in scene.headers] == [c.name for c in guide] == ["Obstacles", "Portals", "Pickups"]
    assert [item.name for item, _ in scene.items] == [i.name for c in guide for i in c.items]
    for _, rect in scene.items:
        assert scene.list_rect.contains(rect)


def test_hovering_a_list_item_marks_it():
    _, scene = _open()
    item, rect = scene.items[2]
    scene.handle_event(pygame.event.Event(pygame.MOUSEMOTION, pos=rect.center, rel=(0, 0), buttons=(0, 0, 0)))
    assert scene.hover is item
    scene.handle_event(pygame.event.Event(pygame.MOUSEMOTION, pos=scene.frame.center, rel=(0, 0),
                                          buttons=(0, 0, 0)))
    assert scene.hover is None


@pytest.mark.parametrize("index", [0, 1, 2, 3])
def test_every_step_draws(index):
    _, scene = _open(index)
    for _ in range(5):
        scene.update(1 / 30)
        _draw(scene)


def test_the_picture_is_the_walkthrough_scaled_into_the_frame():
    _, scene = _open()
    surface = _draw(scene)
    full = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    scene.inner.draw(full)
    # The left panel's background shows at the frame's left edge, the plot further right.
    inner_px = full.get_at((px(10), px(400)))[:3]
    got = surface.get_at(_outer(scene, (px(10), px(400))))[:3]
    assert all(abs(a - b) <= 12 for a, b in zip(got, inner_px))


# --- input goes to the right place -------------------------------------------------------------
def test_clicking_the_shrunk_play_button_plays():
    _, scene = _open()
    inner = scene.inner
    _type(inner, "5", "0")
    assert inner.run_button.enabled and inner.state == SETUP
    _click(scene, _outer(scene, inner.run_button.rect.center))
    assert inner.state == FLIGHT


def test_a_click_beside_the_shrunk_play_button_does_not_play():
    _, scene = _open()
    inner = scene.inner
    _type(inner, "5", "0")
    rect = inner.run_button.rect
    # The same spot taken as full-size coordinates is far from the shrunk button.
    _click(scene, (rect.right + px(60), rect.bottom + px(60)))
    assert inner.state == SETUP


def test_a_drag_in_the_editor_selects_where_the_shrunk_text_is():
    _, scene = _open()
    inner = scene.inner
    _type(inner, "5", "0")
    real = inner.editor.handle_event
    seen = []
    inner.editor.handle_event = lambda event: seen.append(event) or real(event)
    start = _outer(scene, inner.editor.rect.center)
    scene.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=start))
    scene.handle_event(pygame.event.Event(pygame.MOUSEMOTION, pos=(start[0] + 10, start[1]),
                                          rel=(10, 0), buttons=(1, 0, 0)))
    scene.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=(start[0] + 10, start[1])))
    down = next(e for e in seen if e.type == pygame.MOUSEBUTTONDOWN)
    assert abs(down.pos[0] - inner.editor.rect.centerx) <= 2
    assert abs(down.pos[1] - inner.editor.rect.centery) <= 2


def test_keys_reach_the_walkthrough():
    _, scene = _open(1)                                 # a demo step: Next on Enter
    inner = scene.inner
    for _ in range(600):
        if inner.caption is not None:
            break
        scene.update(1 / 30)
    beat = inner.beat
    _key(scene, pygame.K_RETURN)
    assert inner.beat == beat + 1


def test_next_step_stays_inside_the_tutorial_screen():
    mgr, scene = _open(1)
    for _ in range(3000):                               # play the demo's beats through
        if scene.inner.index != 1:
            break
        if scene.inner.can_next:
            scene.inner.advance()
        scene.update(1 / 30)
    assert mgr.scene is scene
    assert isinstance(scene.inner, BasicsScene) and scene.inner.index == 2


# --- leaving -------------------------------------------------------------------------------------
@pytest.mark.parametrize("how", ["exit", "esc"])
def test_exit_and_esc_leave_to_level_select_and_give_the_session_back(how):
    mgr = _manager()
    session = mgr.session
    session.fx_text, session.fy_text, session.level_id = "x", "y", 4
    session.ship_id, session.random_seed = "ship02", 1234
    before = {k: getattr(session, k) for k in ("fx_text", "fy_text", "editor_history", "ship_id",
                                                "level_id", "random_seed")}
    _, scene = _open(0, mgr)
    if how == "exit":
        _click(scene, scene.exit_button.rect.center)
    else:
        _key(scene, pygame.K_ESCAPE)
    assert isinstance(mgr.scene, LevelSelectScene)
    assert {k: getattr(session, k) for k in before} == before


def test_start_playing_on_the_last_step_leaves_to_level_select():
    mgr, scene = _open(3)
    _click(scene, _outer(scene, scene.inner.card_button.rect.center))
    assert isinstance(mgr.scene, LevelSelectScene)


# --- nothing counts --------------------------------------------------------------------------------
def test_the_tutorial_screen_counts_for_nothing():
    mgr, scene = _open()
    assert scene.counts_for_progress is False
    session = mgr.session
    before = (dict(session.achievements), dict(session.achievement_progress), session.money)
    inner = scene.inner
    _type(inner, "5", "0")
    _click(scene, _outer(scene, inner.run_button.rect.center))
    t = 0.0
    while not inner.done and t < 20:
        scene.update(1 / 30)
        t += 1 / 30
    assert inner.done
    assert (session.achievements, session.achievement_progress, session.money) == before


# --- ordinary levels are untouched -----------------------------------------------------------------
def test_an_ordinary_level_keeps_its_full_screen_layout_and_input():
    mgr = _manager()
    mgr.session.level_id = 1
    mgr.session.fx_text, mgr.session.fy_text = "5", "0"
    game = GameScene(mgr)
    mgr.switch(game)
    assert game.camera.rect == pygame.Rect(config.PLOT_RECT)
    assert not isinstance(game, TutorialScene)
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    game.draw(surface)
    game._validate()
    game._refresh_buttons()
    _click(game, game.run_button.rect.center)
    assert game.state == FLIGHT
