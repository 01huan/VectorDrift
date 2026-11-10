"""Pickup effects: what the player sees when the ship takes a pickup.

Presentation only. The Flight applies every rule the moment a pickup
triggers; these tests check the scene's effects on top of that, and that
the timer and coin count show the new value only once the "+N" arrives.
"""
from types import SimpleNamespace

import pygame
import pytest

from vector_drift import config
from vector_drift.data import SectionSpec, multi_section_level
from vector_drift.physics import Outcome
from vector_drift.scenes import game as game_module
from vector_drift.scenes import pickup_effects as fx
from vector_drift.scenes.base import SceneManager
from vector_drift.scenes.fail import FailScene
from vector_drift.scenes.game import FLIGHT, PANNING, GameScene

pytestmark = pytest.mark.usefixtures("pygame_display")

# Nothing in the way: Fx = Fy = 0 keeps the ship at the start. Two sections,
# so reaching the first target is a checkpoint (section switch).
CALM = multi_section_level(
    id=95, name="Calm", ship_id="ship01", lives=3,
    sections=(
        SectionSpec(start=(-7.0, 0.0), target_center=(7.0, 0.0), time_limit=10.0),
        SectionSpec(start=(-7.0, 0.0), target_center=(7.0, 0.0)),
    ),
)
FAKES = {CALM.id: CALM}
WHERE = (2.0, 1.5)          # world position of every pickup taken here


@pytest.fixture(autouse=True)
def fake_levels(monkeypatch):
    real = game_module.get_level
    monkeypatch.setattr(game_module, "get_level",
                        lambda lid, seed=None: FAKES[lid] if lid in FAKES else real(lid, seed=seed))


@pytest.fixture(autouse=True)
def no_solver(monkeypatch):
    monkeypatch.setattr(game_module, "run_solver_async", lambda *a, **k: SimpleNamespace(
        running=True, cancel=lambda: None, stop=lambda *a: True, error=None, result=None))


def _manager():
    audio = SimpleNamespace(play=lambda *a, **k: None, start_loop=lambda *a, **k: None,
                            stop_loop=lambda *a, **k: None, toggle_mute=lambda: None)
    return SceneManager(audio)


def _flying(lives=None):
    """A scene in FLIGHT on CALM (the ship sits still at the start)."""
    manager = _manager()
    manager.session.level_id = CALM.id
    manager.session.fx_text, manager.session.fy_text = "0", "0"
    scene = GameScene(manager)
    manager.switch(scene)
    scene._try_launch()
    assert scene.state == FLIGHT
    if lives is not None:
        scene.lives = lives
    return scene


def _take(scene, kind, **extra):
    """What a flight does when the ship touches a ``kind`` pickup."""
    event = {"kind": kind, "center": WHERE, **extra}
    if kind == "shockwave":
        event.setdefault("destroyed", [])
    if kind == "money":
        event.setdefault("amount", 1)
    scene.flight._apply_pickup_events([event])
    scene.flight.pickup_events.append(event)
    scene._drain_pickup_events()


def _age(scene, seconds):
    """Advance only the effects (the flight stays where it is)."""
    scene.pickup_fx.update(seconds)


def _styles(scene):
    return sorted((e.style, e.kind) for e in scene.pickup_fx.effects)


# --- every pickup makes its effect ---------------------------------------------------

@pytest.mark.parametrize("kind, style", [
    ("shockwave", "burst"), ("shield", "burst"), ("extratime", "fly"),
    ("money", "fly"), ("life", "life"), ("unbound", "edge"),
])
def test_each_pickup_makes_its_effect(kind, style):
    scene = _flying()
    _take(scene, kind)
    assert _styles(scene) == [(style, kind)]


def test_world_effects_keep_the_pickup_position_in_world_coordinates():
    scene = _flying()
    for kind in ("shockwave", "shield", "life"):
        _take(scene, kind)
    assert all(e.center == WHERE for e in scene.pickup_fx.effects)


def test_hud_effects_fly_to_the_timer_and_the_coins():
    scene = _flying()
    _take(scene, "extratime")
    _take(scene, "money", amount=4)
    targets = {e.kind: (e.target, e.text) for e in scene.pickup_fx.effects}
    assert targets == {"extratime": (fx.TIMER, "+3"), "money": (fx.COINS, "+4")}


def test_extratime_text_shows_the_seconds_actually_added():
    scene = _flying()
    _take(scene, "extratime", extratime_duration=2.5)
    assert [e.text for e in scene.pickup_fx.effects] == ["+2.5"]


def test_several_effects_play_at_once_and_the_game_keeps_running():
    scene = _flying()
    for kind in ("shockwave", "shield", "extratime", "money", "life", "unbound"):
        _take(scene, kind)
    assert len(scene.pickup_fx.effects) == 6
    steps = scene.flight.steps
    scene.update(0.1)
    assert scene.state == FLIGHT and scene.flight.steps > steps


# --- each effect ends on time --------------------------------------------------------

@pytest.mark.parametrize("kind, duration", [
    ("shockwave", fx.BURST_S), ("shield", fx.BURST_S), ("extratime", fx.FLY_S),
    ("money", fx.FLY_S), ("life", fx.LIFE_S), ("unbound", fx.EDGE_S),
])
def test_effect_is_removed_when_its_time_is_up(kind, duration):
    assert (fx.BURST_S, fx.FLY_S, fx.LIFE_S, fx.EDGE_S) == (0.5, 0.6, 0.8, 0.4)
    scene = _flying()
    _take(scene, kind)
    _age(scene, duration - 0.05)
    assert scene.pickup_fx.effects
    _age(scene, 0.1)
    assert not scene.pickup_fx.effects


def test_effects_wait_while_the_game_is_paused():
    scene = _flying()
    _take(scene, "shield")
    scene._open_pause()
    scene.update(1.0)
    assert scene.pickup_fx.effects
    scene._close_pause()


# --- money: only a coin that pays --------------------------------------------------

def test_money_that_pays_nothing_makes_no_effect():
    scene = _flying()
    _take(scene, "money")
    _age(scene, fx.FLY_S + 0.1)
    assert not scene.pickup_fx.effects
    _take(scene, "money")                       # the same coin again: already paid
    assert not scene.pickup_fx.effects


def test_coin_count_shows_the_old_balance_until_the_text_arrives():
    scene = _flying()
    before = int(scene.session.money)
    _take(scene, "money", amount=3)
    assert int(scene.session.money) == before + 3      # paid at once
    assert scene._shown_money() == before
    _age(scene, fx.FLY_S - 0.05)
    assert scene._shown_money() == before
    assert scene.pickup_fx.pop_scale(fx.COINS) == 1.0
    _age(scene, 0.1)
    assert scene._shown_money() == before + 3
    assert scene.pickup_fx.pop_scale(fx.COINS) > 1.0   # the count jumps
    _age(scene, fx.HUD_POP_S)
    assert scene.pickup_fx.pop_scale(fx.COINS) == 1.0


# --- extratime: the timer shows the new time once the text arrives ---------------

def test_timer_shows_the_old_time_until_the_text_arrives():
    scene = _flying()
    flight = scene.flight
    old_limit = flight.time_left
    _take(scene, "extratime")
    assert flight.time_left == pytest.approx(old_limit + 3.0)   # the limit grew at once
    assert scene._shown_time_left() == pytest.approx(old_limit)
    _age(scene, fx.FLY_S - 0.05)
    assert scene._shown_time_left() == pytest.approx(old_limit)
    assert scene.pickup_fx.pop_scale(fx.TIMER) == 1.0
    _age(scene, 0.1)
    assert scene._shown_time_left() == pytest.approx(old_limit + 3.0)
    assert scene.pickup_fx.pop_scale(fx.TIMER) > 1.0   # it flashes and grows


def test_timer_keeps_counting_down_while_the_text_flies():
    scene = _flying()
    _take(scene, "extratime")
    shown = scene._shown_time_left()
    scene.update(0.25)                          # the flight runs on
    assert scene._shown_time_left() == pytest.approx(scene.flight.time_left - 3.0)
    assert scene._shown_time_left() < shown


def test_extratime_does_not_change_the_flight():
    scene = _flying()
    plain = _flying()
    _take(scene, "extratime")
    plain.flight._apply_pickup_events([{"kind": "extratime", "center": WHERE}])
    assert scene.flight.max_steps == plain.flight.max_steps


# --- life ------------------------------------------------------------------------

def test_a_restored_life_makes_its_icon_jump():
    scene = _flying(lives=1)
    _take(scene, "life")
    assert scene.lives == 2
    assert scene.pickup_fx.pop_scale(fx.LIFE, 1) > 1.0     # the icon that lit up
    assert scene.pickup_fx.pop_scale(fx.LIFE, 0) == 1.0


def test_life_at_full_lives_floats_but_no_icon_jumps():
    scene = _flying()
    assert scene.lives == scene.level.lives
    _take(scene, "life")
    assert _styles(scene) == [("life", "life")]
    assert all(scene.pickup_fx.pop_scale(fx.LIFE, i) == 1.0 for i in range(scene.level.lives))


# --- everything is cleared --------------------------------------------------------

def _busy():
    scene = _flying(lives=1)                    # so the life lights an icon too
    for kind in ("shockwave", "extratime", "money", "life", "unbound"):
        _take(scene, kind)
    assert scene.pickup_fx.effects and scene.pickup_fx.pops
    return scene


def _assert_cleared(scene):
    assert not scene.pickup_fx.effects and not scene.pickup_fx.pops


def test_retry_after_a_fail_starts_without_effects():
    scene = _busy()
    fail = FailScene(scene.manager)
    scene.manager.switch(fail)
    _assert_cleared(scene)                      # leaving the scene clears them
    fail.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN, mod=0,
                                         unicode="\r", scancode=0))
    retry = scene.manager.scene
    assert isinstance(retry, GameScene) and retry is not scene
    _assert_cleared(retry)


def test_restart_from_the_pause_menu_clears_effects():
    scene = _busy()
    scene._open_pause()
    scene.pause_menu.handle_event = lambda event: "restart"
    scene._handle_pause_event(None)
    _assert_cleared(scene)
    _assert_cleared(scene.manager.scene)


def test_next_launch_clears_effects():
    scene = _busy()
    scene._abort()
    scene._try_launch()
    _assert_cleared(scene)
    assert scene._shown_time_left() == pytest.approx(scene.flight.time_left)


def test_reaching_a_checkpoint_clears_effects():
    scene = _flying()
    _take(scene, "shield")
    scene.flight.x, scene.flight.y = CALM.sections[0].target_center
    scene._end_flight(Outcome.REACHED)
    assert scene.state == PANNING
    _assert_cleared(scene)


def test_resetting_the_level_clears_effects():
    scene = _busy()
    scene._reset_level()
    _assert_cleared(scene)


# --- drawing ------------------------------------------------------------------------

def test_every_effect_draws_without_errors_through_its_whole_life():
    scene = _busy()
    _take(scene, "shield")
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    for _ in range(12):
        scene.draw(surface)
        _age(scene, 0.08)
    assert not scene.pickup_fx.effects


def _plot_pixels(scene):
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    scene._draw_plot(surface)
    return pygame.surfarray.array3d(surface)


def test_burst_is_drawn_at_the_pickup_position():
    scene = _flying()
    bare = _plot_pixels(scene)
    _take(scene, "shockwave")
    with_burst = _plot_pixels(scene)
    sx, sy = (round(v) for v in scene.camera.to_screen(*WHERE))
    r = round(scene.camera.length(0.45))
    changed = (with_burst != bare).any(axis=2)
    assert changed[sx - r:sx + r, sy - r:sy + r].any()


def test_unbound_flash_lights_the_map_edge_in_the_unbound_colour():
    scene = _flying()
    _take(scene, "unbound")
    pixels = _plot_pixels(scene)
    plot = pygame.Rect(scene.camera.rect)
    inset = plot.inflate(-2 * config.px(fx.EDGE_FLASH_IN), -2 * config.px(fx.EDGE_FLASH_IN))
    # At the start the flash is EDGE_FLASH_IN inside the edge, on the left side.
    column = pixels[inset.left - 3:inset.left + 5, plot.centery]
    target = game_module.UNBOUND_EDGE
    assert any(abs(int(c[0]) - target[0]) < 30 and abs(int(c[2]) - target[2]) < 30 for c in column)
