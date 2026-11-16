"""Field guide: the card page and every clip on the real game screen and engine."""

from types import SimpleNamespace

import pygame
import pytest

from vector_drift import config
from vector_drift.physics import Outcome
from vector_drift.scenes.base import SceneManager
from vector_drift.scenes.field_guide import HOLD, FieldGuideScene, GuideDemoScene
from vector_drift.scenes.game_layout import FLIGHT
from vector_drift.scenes.levels import LevelSelectScene
from vector_drift.tutorial import tutorial

pytestmark = pytest.mark.usefixtures("pygame_display")

ALL_ITEMS = ["Rock", "Black / white hole", "Shockwave", "Extratime", "Unbound", "Shield"]


def _manager():
    audio = SimpleNamespace(play=lambda *a, **k: None, start_loop=lambda *a, **k: None,
                            stop_loop=lambda *a, **k: None, toggle_mute=lambda: None)
    mgr = SceneManager(audio)
    mgr.screen = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    return mgr


def _item(name):
    return next(i for c in tutorial().guide for i in c.items if i.name == name)


def _open(name, mgr=None):
    mgr = mgr or _manager()
    scene = GuideDemoScene(mgr, _item(name))
    mgr.switch(scene)
    return mgr, scene


def _until_hold(scene, watch=None, limit=20.0, dt=1 / 30):
    """Run frames until the clip holds on its last frame."""
    t = 0.0
    while scene.state != HOLD and t < limit:
        scene.update(dt)
        if watch:
            watch(scene)
        t += dt
    assert scene.state == HOLD, f"clip never ended (state {scene.state})"


def _next_clip(scene):
    while scene.state == HOLD:
        scene.update(1 / 30)
    assert scene.state == FLIGHT


def _click(scene, pos):
    scene.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=pos))
    scene.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=pos))


def _esc(scene):
    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, mod=0, unicode="",
                                          scancode=0))


# --- the page ---------------------------------------------------------------------------
def test_page_lists_the_categories_and_cards():
    mgr = _manager()
    page = FieldGuideScene(mgr)
    assert [name for name, _ in page.headers] == ["Obstacles", "Portals", "Pickups"]
    assert [item.name for item, _ in page.cards] == ALL_ITEMS
    page.draw(pygame.Surface((config.WINDOW_W, config.WINDOW_H)))


def test_a_card_opens_its_clip_and_esc_goes_back_to_the_page():
    mgr = _manager()
    page = FieldGuideScene(mgr)
    mgr.switch(page)
    item, rect = page.cards[0]
    page.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=rect.center))
    assert isinstance(mgr.scene, GuideDemoScene) and mgr.scene.item is item
    _esc(mgr.scene)
    assert isinstance(mgr.scene, FieldGuideScene)
    back = mgr.scene.back_button.rect.center
    _open("Rock", mgr)
    _click(mgr.scene, back)                     # the clip's Back button sits at the same place
    assert isinstance(mgr.scene, FieldGuideScene)


def test_esc_on_the_page_leaves_to_level_select():
    mgr = _manager()
    page = FieldGuideScene(mgr)
    mgr.switch(page)
    _esc(page)
    assert isinstance(mgr.scene, LevelSelectScene)


@pytest.mark.parametrize("name", ALL_ITEMS)
def test_no_formula_is_shown_anywhere(name, monkeypatch):
    _, scene = _open(name)
    monkeypatch.setattr(scene.editor, "draw", lambda *a: pytest.fail("the editor was drawn"))
    drawn = []
    from vector_drift.scenes import field_guide
    real = field_guide.draw_text
    monkeypatch.setattr(field_guide, "draw_text", lambda s, text, *a, **k: (drawn.append(text),
                                                                           real(s, text, *a, **k)))
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    scene.draw(surface)
    _until_hold(scene)
    scene.draw(surface)
    for part in scene.item.parts:
        assert not any(f in t for t in drawn for f in ("Fx", "Fy", " = "))
        assert part.text in " ".join(drawn) or len(part.text) > 30


# --- each clip --------------------------------------------------------------------------
def test_rock_bounces_the_ship_up():
    _, scene = _open("Rock")
    seen = []
    _until_hold(scene, watch=lambda s: seen.append((s.flight.time, s.flight.bounces, s.flight.vy))
                if s.flight else None)
    first = next(t for t, b, _ in seen if b)
    assert first == pytest.approx(1.6, abs=0.06)
    assert scene.flight.running and scene.flight.time == pytest.approx(2.3, abs=0.01)
    assert scene.flight.vy > 0
    scene.draw(pygame.Surface((config.WINDOW_W, config.WINDOW_H)))


def test_holes_teleport_and_break_the_trail():
    _, scene = _open("Black / white hole")
    _until_hold(scene)
    flight = scene.flight
    assert flight.teleports == 1 and flight.bounces == 0 and flight.running
    assert flight.trail_breaks and flight.x > 3.0
    assert flight.time == pytest.approx(1.9, abs=0.01)


def test_shockwave_clears_the_near_rocks_and_the_next_clip_puts_them_back():
    _, scene = _open("Shockwave")
    _until_hold(scene)
    assert [o.center for o in scene.level.obstacles] == [(5.5, 2.5)]
    assert all(p.consumed for p in scene.pickups)
    assert scene.flight.x > 2.2 and scene.flight.y == pytest.approx(0.0)
    _next_clip(scene)
    assert len(scene.level.obstacles) == 4
    assert not any(p.consumed for p in scene.pickups)
    assert scene.flight.trail[0] == (-7.0, 0.0)


def test_extratime_adds_three_seconds_to_the_shown_timer():
    _, scene = _open("Extratime")
    assert scene.part.show_timer and scene._shown_time_left() == pytest.approx(3.0)
    flies = []

    def watch(s):
        flies.extend(e for e in s.pickup_fx.effects if getattr(e, "style", "") == "fly")
    _until_hold(scene, watch=watch)
    assert flies                                    # the "+3" flew to the timer
    assert scene._fly_target("timer") == scene._fly_target(flies[0].target)
    flight = scene.flight
    assert flight.running and flight.time == pytest.approx(3.5, abs=0.01)
    assert flight.max_steps * flight.dt == pytest.approx(6.0)
    assert scene._shown_time_left() == pytest.approx(2.5, abs=0.05)


def test_unbound_flies_off_the_map_and_the_camera_zooms_out():
    _, scene = _open("Unbound")
    _until_hold(scene)
    flight = scene.flight
    assert flight.unbound and flight.running and flight.outcome is not Outcome.OUT_OF_BOUNDS
    assert flight.y > config.WORLD_HALF_H
    assert scene.camera.zoom < 1.0


def test_shield_plays_both_parts_in_turn():
    _, scene = _open("Shield")
    _until_hold(scene)
    trail = scene.flight.trail
    crossings = [b[1] for a, b in zip(trail, trail[1:]) if a[0] < 0 <= b[0]]
    assert scene.part_index == 0
    assert scene.flight.bounces == 0 and crossings and crossings[0] == pytest.approx(0.0)
    _next_clip(scene)
    assert scene.part_index == 1 and scene.editor.lines == ["0", "5"]
    flips = []

    def edge(s):
        f = s.flight
        if f and f.vy < 0 and not flips:
            flips.append((f.time, f.y))
    _until_hold(scene, watch=edge)
    assert flips and flips[0][0] == pytest.approx(1.73, abs=0.05)
    assert flips[0][1] > config.WORLD_HALF_H - 0.5
    assert scene.flight.running and scene.flight.vy < 0
    _next_clip(scene)
    assert scene.part_index == 0                    # and round again


# --- nothing counts --------------------------------------------------------------------------
def _play_every_clip(mgr):
    """From the page: open each card, play all its parts, Esc back to the page."""
    page = FieldGuideScene(mgr)
    mgr.switch(page)
    for item, _rect in page.cards:
        mgr.scene.open(item)
        scene = mgr.scene
        for _ in scene.item.parts:
            _until_hold(scene)
            _next_clip(scene)
        _esc(scene)
        assert isinstance(mgr.scene, FieldGuideScene)


def test_the_clips_change_no_achievements_or_counters():
    mgr = _manager()
    session = mgr.session
    before = (dict(session.achievements), dict(session.achievement_progress))
    _play_every_clip(mgr)
    assert (session.achievements, session.achievement_progress) == before


def test_the_same_clips_would_earn_achievements_outside_the_tutorial(monkeypatch):
    """Shows the check above is real: counted play would unlock hole_in_one, kaboom, ..."""
    monkeypatch.setattr(GuideDemoScene, "counts_for_progress", True)
    mgr = _manager()
    _play_every_clip(mgr)
    assert {"hole_in_one", "kaboom", "not_a_scratch"} <= set(mgr.session.achievements)


def test_the_clips_change_no_coins_records_replays_or_saves(monkeypatch):
    from vector_drift.account import integration
    saves = []
    monkeypatch.setattr(integration, "save_progress", lambda *a, **k: saves.append(a))
    mgr = _manager()
    session = mgr.session
    session.fx_text, session.fy_text, session.level_id = "x", "y", 3
    before = (session.money, dict(session.records), list(session.replays or []))
    _play_every_clip(mgr)
    _esc(mgr.scene)
    assert (session.money, session.records, list(session.replays or [])) == before
    assert saves == []
    assert (session.fx_text, session.fy_text, session.level_id) == ("x", "y", 3)
