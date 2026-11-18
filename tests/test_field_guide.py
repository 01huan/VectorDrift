"""Field guide clips (shown in the tutorial screen's popup) on the real game screen and engine."""

from types import SimpleNamespace

import pygame
import pytest

from vector_drift import config
from vector_drift.physics import Outcome
from vector_drift.scenes.base import SceneManager
from vector_drift.scenes import field_guide
from vector_drift.scenes.field_guide import HOLD, GuideDemoScene
from vector_drift.scenes.game_layout import FLIGHT
from vector_drift.scenes.tutorial_play import give_back_session
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


# --- no page of its own ------------------------------------------------------------------
def test_there_is_no_card_page_any_more():
    assert not hasattr(field_guide, "FieldGuideScene")
    assert not hasattr(field_guide, "back_to_tutorial_menu")
    assert [i.name for c in tutorial().guide for i in c.items] == ALL_ITEMS


@pytest.mark.parametrize("name", ALL_ITEMS)
def test_no_formula_is_shown_anywhere(name, monkeypatch):
    """A clip draws its map only: never the editor or the left panel with the formulas."""
    _, scene = _open(name)
    monkeypatch.setattr(scene.editor, "draw", lambda *a: pytest.fail("the editor was drawn"))
    monkeypatch.setattr(scene, "_draw_panel", lambda *a: pytest.fail("the left panel was drawn"))
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    scene.draw(surface)
    _until_hold(scene)
    scene.draw(surface)


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
    """Each clip in turn, all its parts, then the session given back (as the popup does)."""
    for name in ALL_ITEMS:
        scene = GuideDemoScene(mgr, _item(name))
        mgr.switch(scene)
        for _ in scene.item.parts:
            _until_hold(scene)
            _next_clip(scene)
        scene.on_exit()
        give_back_session(mgr.session, scene.restore)


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
    assert (session.money, session.records, list(session.replays or [])) == before
    assert saves == []
    assert (session.fx_text, session.fy_text, session.level_id) == ("x", "y", 3)
