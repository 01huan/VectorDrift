"""The tutorial screen: the Basics walkthrough shrunk into a frame, the header and the element list."""

from types import SimpleNamespace

import pygame
import pytest

from vector_drift import config
from vector_drift.config import px
from vector_drift.scenes import tutorial_screen as ts
from vector_drift.scenes.base import SceneManager
from vector_drift.scenes.field_guide import GuideDemoScene
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


# --- the demo popup --------------------------------------------------------------------------------
BORROWED = ("fx_text", "fy_text", "editor_history", "ship_id", "level_id", "random_seed")


def _row(scene, name):
    return next(rect for item, rect in scene.items if item.name == name)


def _item(scene, name):
    return next(item for item, _ in scene.items if item.name == name)


def _session_values(session):
    return {k: getattr(session, k) for k in BORROWED}


def test_clicking_a_list_item_opens_its_demo_popup():
    _, scene = _open()
    assert scene.popup is None
    _click(scene, _row(scene, "Shockwave").center)
    assert scene.popup is not None and scene.popup.item is _item(scene, "Shockwave")
    assert isinstance(scene.popup.demo, GuideDemoScene)
    _draw(scene)


def test_the_element_guide_is_titled_and_marked_until_its_first_demo(monkeypatch):
    drawn = []
    real = ts.draw_text
    monkeypatch.setattr(ts, "draw_text", lambda s, text, *a, **k: drawn.append(text) or real(s, text, *a, **k))
    _, scene = _open()
    _draw(scene)
    assert "ELEMENT GUIDE" in drawn and "Click a row to watch" in drawn
    assert not scene.seen_popup
    _click(scene, _row(scene, "Rock").center)
    assert scene.seen_popup


def test_the_list_works_on_every_step():
    for index in range(4):
        _, scene = _open(index)
        _click(scene, _row(scene, "Rock").center)
        assert scene.popup is not None and scene.popup.item.name == "Rock"


def test_another_item_replaces_the_popup():
    _, scene = _open()
    _click(scene, _row(scene, "Rock").center)
    first = scene.popup
    _click(scene, _row(scene, "Shield").center)
    assert scene.popup is not first and scene.popup.item.name == "Shield"


@pytest.mark.parametrize("how", ["x", "esc", "same item", "main view"])
def test_the_popup_closes(how):
    mgr, scene = _open()
    _click(scene, _row(scene, "Rock").center)
    popup = scene.popup
    if how == "x":
        _click(scene, popup.close_rect.center)
    elif how == "esc":
        _key(scene, pygame.K_ESCAPE)
    elif how == "same item":
        _click(scene, _row(scene, "Rock").center)
    else:
        spot = (scene.frame.x + px(40), scene.frame.bottom - px(40))
        assert not popup.rect.collidepoint(spot)
        _click(scene, spot)
    assert scene.popup is None
    assert mgr.scene is scene                           # still in the tutorial


def test_a_click_on_the_dimmed_view_only_closes_the_popup():
    _, scene = _open()
    inner = scene.inner
    _type(inner, "5", "0")
    _click(scene, _row(scene, "Rock").center)
    play = _outer(scene, inner.run_button.rect.center)
    assert not scene.popup.rect.collidepoint(play)
    _click(scene, play)
    assert scene.popup is None and inner.state == SETUP  # the click did not reach Play


def test_esc_with_a_popup_only_closes_it_then_leaves():
    mgr, scene = _open()
    _click(scene, _row(scene, "Rock").center)
    _key(scene, pygame.K_ESCAPE)
    assert mgr.scene is scene and scene.popup is None
    _key(scene, pygame.K_ESCAPE)
    assert isinstance(mgr.scene, LevelSelectScene)


def test_one_popup_at_a_time(monkeypatch):
    opened, closed = [], []
    real_open, real_close = ts.DemoPopup.__init__, ts.DemoPopup.close
    monkeypatch.setattr(ts.DemoPopup, "__init__",
                        lambda self, *a, **k: opened.append(self) or real_open(self, *a, **k))
    monkeypatch.setattr(ts.DemoPopup, "close", lambda self: closed.append(self) or real_close(self))
    _, scene = _open()
    for name in ("Rock", "Shockwave", "Unbound", "Shield"):
        _click(scene, _row(scene, name).center)
        assert len(opened) - len(closed) == 1           # never two open
    assert scene.popup is opened[-1] and scene.popup.item.name == "Shield"


def test_a_popup_sits_left_of_the_list_beside_its_row_and_on_screen():
    _, scene = _open()
    for item, row in scene.items:
        _click(scene, row.center)
        popup = scene.popup
        assert popup.item is item
        assert popup.rect.right < scene.list_rect.left
        assert popup.rect.w == px(440)
        assert popup.demo_rect.size == (px(404), px(303))
        assert popup.rect.top >= 0 and popup.rect.bottom <= config.WINDOW_H
        assert popup.rect.top <= row.centery <= popup.rect.bottom
        assert abs(popup.pointer_y - row.centery) <= 1
        _draw(scene)


def test_the_popup_shows_the_name_text_and_part_but_never_the_formula(monkeypatch):
    drawn = []
    real = ts.draw_text
    monkeypatch.setattr(ts, "draw_text", lambda s, text, *a, **k: drawn.append(text) or real(s, text, *a, **k))
    _, scene = _open()
    _click(scene, _row(scene, "Shield").center)
    monkeypatch.setattr(scene.popup.demo.editor, "draw", lambda *a: pytest.fail("the editor was drawn"))
    drawn.clear()
    _draw(scene)
    shown = " ".join(drawn)
    assert "Shield" in drawn and "1 / 2" in drawn and "Paused" in drawn
    assert scene.popup.demo.part.text.split()[0] in shown
    assert not any(f in shown for f in ("Fx", "Fy"))


def test_the_popup_demo_loops_its_parts():
    _, scene = _open()
    _click(scene, _row(scene, "Shield").center)
    demo = scene.popup.demo
    for _ in range(20 * 30):
        scene.update(1 / 30)
        if demo.part_index == 1:
            break
    assert demo.part_index == 1


def test_extratime_shows_its_timer_in_the_popup(monkeypatch):
    drawn = []
    real = ts.draw_text
    monkeypatch.setattr(ts, "draw_text", lambda s, text, *a, **k: drawn.append(text) or real(s, text, *a, **k))
    _, scene = _open()
    _click(scene, _row(scene, "Extratime").center)
    _draw(scene)
    assert "03:00" in drawn
    demo = scene.popup.demo
    assert pygame.Rect(demo.camera.rect).collidepoint(demo._fly_target("timer"))   # "+3" flies to the shown clock


# --- the walkthrough waits while a popup is open -----------------------------------------------------
def test_the_walkthrough_is_paused_while_a_popup_is_open():
    _, scene = _open(1)                                 # a demo step: it launches by itself
    inner = scene.inner
    scene.update(0.3)
    wait = inner.auto_wait
    _click(scene, _row(scene, "Rock").center)
    for _ in range(90):
        scene.update(1 / 30)
    assert inner.auto_wait == wait and inner.flight is None
    _click(scene, scene.popup.close_rect.center)
    for _ in range(60):
        scene.update(1 / 30)
    assert inner.flight is not None                     # it carried on


def test_a_flight_stands_still_while_a_popup_is_open():
    _, scene = _open(0)
    inner = scene.inner
    _type(inner, "5", "0")
    _click(scene, _outer(scene, inner.run_button.rect.center))
    for _ in range(10):
        scene.update(1 / 30)
    assert inner.state == FLIGHT
    time, pos, t = inner.flight.time, (inner.flight.x, inner.flight.y), inner.t
    _click(scene, _row(scene, "Unbound").center)
    for _ in range(60):
        scene.update(1 / 30)
    assert (inner.flight.time, (inner.flight.x, inner.flight.y), inner.t) == (time, pos, t)
    _key(scene, pygame.K_ESCAPE)
    scene.update(1 / 30)
    assert inner.flight.time > time


def test_input_goes_only_to_the_popup_list_and_exit():
    _, scene = _open()
    inner = scene.inner
    _type(inner, "5", "0")
    _click(scene, _row(scene, "Rock").center)
    _key(scene, pygame.K_RETURN)                        # would launch
    scene.handle_event(pygame.event.Event(pygame.TEXTINPUT, text="7"))
    assert inner.state == SETUP and inner.editor.lines == ["5", "0"]
    _click(scene, _row(scene, "Shield").center)         # the list still works
    assert scene.popup.item.name == "Shield"


def test_exit_with_a_popup_open_leaves():
    mgr, scene = _open()
    _click(scene, _row(scene, "Rock").center)
    _click(scene, scene.exit_button.rect.center)
    assert isinstance(mgr.scene, LevelSelectScene)


# --- the session is borrowed once and given back -----------------------------------------------------
def _fresh_session(mgr):
    session = mgr.session
    session.fx_text, session.fy_text, session.level_id = "x", "y", 4
    session.ship_id, session.random_seed, session.editor_history = "ship02", 1234, None
    return _session_values(session)


def test_a_popup_leaves_the_walkthrough_its_own_session_values():
    mgr = _manager()
    _fresh_session(mgr)
    _, scene = _open(0, mgr)
    _type(scene.inner, "5", "0")
    during = _session_values(mgr.session)
    _click(scene, _row(scene, "Shield").center)
    assert (mgr.session.fx_text, mgr.session.fy_text) == tuple(scene.popup.demo.part.force)
    _click(scene, _row(scene, "Rock").center)           # replaced: given back, borrowed again
    _key(scene, pygame.K_ESCAPE)                        # closed
    assert _session_values(mgr.session) == during


@pytest.mark.parametrize("how", ["closed first", "exit with popup", "esc twice"])
def test_leaving_gives_the_session_back_even_after_popups(how):
    mgr = _manager()
    before = _fresh_session(mgr)
    _, scene = _open(0, mgr)
    _click(scene, _row(scene, "Shockwave").center)
    for _ in range(30):
        scene.update(1 / 30)
    _click(scene, _row(scene, "Extratime").center)
    if how == "closed first":
        _click(scene, scene.popup.close_rect.center)
        _click(scene, scene.exit_button.rect.center)
    elif how == "exit with popup":
        _click(scene, scene.exit_button.rect.center)
    else:
        _key(scene, pygame.K_ESCAPE)
        _key(scene, pygame.K_ESCAPE)
    assert isinstance(mgr.scene, LevelSelectScene)
    assert _session_values(mgr.session) == before


# --- nothing counts in the popup -------------------------------------------------------------------
def _watch_every_demo(scene):
    for item, row in scene.items:
        _click(scene, row.center)
        demo = scene.popup.demo
        for _ in range(len(item.parts) * 150):
            scene.update(1 / 30)
        assert scene.popup.demo is demo


def test_popup_demos_count_for_nothing():
    mgr, scene = _open()
    session = mgr.session
    before = (dict(session.achievements), dict(session.achievement_progress), session.money,
              dict(session.records))
    _watch_every_demo(scene)
    assert (session.achievements, session.achievement_progress, session.money, session.records) == before


def test_the_same_demos_would_count_outside_the_tutorial(monkeypatch):
    """Shows the check above is real: counted, the clips count black holes and rocks blown up."""
    from vector_drift import achievements as ach
    monkeypatch.setattr(TutorialScene, "counts_for_progress", True)
    mgr, scene = _open()
    _watch_every_demo(scene)
    progress = mgr.session.achievement_progress
    assert progress.get(ach.TELEPORTS, 0) > 0 and progress.get(ach.ROCKS_DESTROYED, 0) > 0


def test_the_help_card_points_at_the_list():
    help_card = tutorial().basics[3]
    assert ("Want to know what a rock, portal or pickup does? Click it in the **Element guide** on the right."
            in help_card.text)
    assert "Tutorial menu" not in help_card.text and "Field guide" not in help_card.text
