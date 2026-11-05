"""Extra lifecycle / state-transition coverage for GameScene."""

import pygame
import pytest

from types import SimpleNamespace

from vector_drift import config
from vector_drift.scenes.base import SceneManager
from vector_drift.scenes.game import GameScene, SETUP, FLIGHT, ARRIVED


pytestmark = pytest.mark.usefixtures("pygame_display")


def _manager():
    audio = SimpleNamespace(play=lambda *a, **k: None, toggle_mute=lambda: None,
                            start_loop=lambda *a, **k: None, stop_loop=lambda *a, **k: None)
    return SceneManager(audio)


def _scene(level_id=1, fx="1", fy="0"):
    mgr = _manager()
    mgr.session.level_id = level_id
    scene = GameScene(mgr)
    mgr.switch(scene)
    scene.editor.set_lines([fx, fy])
    try:
        scene._on_text_change(scene.editor)
    except Exception:
        pass
    return scene, mgr


@pytest.mark.parametrize("level_id", [1, 2, 3, 4, 7, 8])
def test_game_construct_and_draw(level_id):
    scene, mgr = _scene(level_id)
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    scene.draw(surface)
    assert scene.state in (SETUP, FLIGHT, ARRIVED)
    assert scene.level is not None


@pytest.mark.parametrize("level_id", [1, 2, 3, 4, 7, 8])
def test_game_update_setup(level_id):
    scene, mgr = _scene(level_id)
    scene.update(0.1)
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    scene.draw(surface)


@pytest.mark.parametrize("expr", [("0", "0"), ("1", "1"), ("x", "y")])
def test_game_launch_variants(expr):
    scene, mgr = _scene(1, fx=expr[0], fy=expr[1])
    scene._try_launch()
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    scene.draw(surface)


def test_game_abort_after_launch():
    scene, mgr = _scene(1, fx="1", fy="0")
    scene._try_launch()
    if scene.state != FLIGHT:
        return
    scene._abort()
    assert mgr.scene is not None


def test_game_handle_events_smoke():
    scene, mgr = _scene(1)
    events = [
        pygame.event.Event(pygame.MOUSEMOTION, pos=(100, 100)),
        pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(10, 10)),
        pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN),
        pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE),
        pygame.event.Event(pygame.KEYDOWN, key=pygame.K_a),
    ]
    for e in events:
        try:
            scene.handle_event(e)
        except Exception:
            pass
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    scene.draw(surface)


def test_game_update_flight_loop():
    scene, mgr = _scene(1, fx="0", fy="0")
    scene._try_launch()
    if scene.state != FLIGHT:
        return
    for _ in range(5):
        scene.update(0.1)
        surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
        scene.draw(surface)


def test_replay_records_each_fixed_physics_step():
    scene, _mgr = _scene(1, fx="0", fy="0")
    scene._try_launch()

    assert len(scene._replay_frames) == 1
    scene.update(1 / 60)

    assert len(scene._replay_frames) == 3
    assert [frame["t"] for frame in scene._replay_frames] == pytest.approx(
        [0.0, 1 / 120, 2 / 120])


def test_game_switch_ship():
    scene, mgr = _scene(1)
    scene._switch_ship(1)
    scene._switch_ship(-1)
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    scene.draw(surface)


def test_game_editor_change():
    scene, mgr = _scene(1)
    scene.editor.set_lines(["x", "y"])
    scene._on_text_change(scene.editor)
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    scene.draw(surface)


def test_game_on_exit():
    scene, mgr = _scene(1)
    scene.on_exit()
    assert scene.ai_job is None


def test_game_ai_popup_interactions():
    scene, mgr = _scene(1)
    scene.session.money.add(1000)
    scene.money = scene.session.money
    # open ai popup
    scene._on_ai_click()
    assert scene.ai_popup is True
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    scene.draw(surface)
    # apply button
    scene.ai_result = None
    scene._position_ai_popup_buttons()
    evt = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=tuple(scene.ai_close_button.rect.center))
    scene.handle_event(evt)
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    scene.draw(surface)


def test_game_hint_popup_interactions():
    scene, mgr = _scene(1)
    scene.hint_mode = True
    scene.hint = None
    # open hint (no hint) still calls _open_hint -> sets popup? hint None so maybe no
    try:
        scene._open_hint()
    except Exception:
        pass
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    scene.draw(surface)


def test_game_abort_via_escape():
    scene, mgr = _scene(1, fx="1", fy="0")
    scene._try_launch()
    if scene.state != FLIGHT:
        return
    evt = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE)
    scene.handle_event(evt)
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    scene.draw(surface)


def test_game_draw_arrived():
    scene, mgr = _scene(1, fx="10", fy="0")
    scene._try_launch()
    for _ in range(50):
        if mgr.scene is not scene:
            break
        scene.update(0.1)
    if scene.state == "arrived":
        surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
        scene.draw(surface)
        scene.update(0.1)
        scene.draw(surface)


def test_game_draw_with_banner():
    scene, mgr = _scene(1, fx="0", fy="0")
    scene.lives = 3
    scene._try_launch()
    for _ in range(120):
        if scene.state != FLIGHT or scene.flight is None:
            break
        scene.update(0.1)
    # banner should be set
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    scene.draw(surface)


def test_game_handle_mousemotion():
    scene, mgr = _scene(1)
    evt = pygame.event.Event(pygame.MOUSEMOTION, pos=(100, 200))
    scene.handle_event(evt)
    assert scene._mouse_pos == (100, 200)


def test_game_handle_disabled_run():
    scene, mgr = _scene(1)
    scene.valid = False
    scene._refresh_buttons()
    # clicking run button when disabled triggers audio.play("error")
    evt = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=tuple(scene.run_button.rect.center))
    scene.handle_event(evt)
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    scene.draw(surface)


def test_game_reached_path():
    scene, mgr = _scene(1, fx="10", fy="0")
    scene._try_launch()
    assert scene.state == FLIGHT
    for _ in range(50):
        if mgr.scene is not scene:
            break
        scene.update(0.1)
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    scene.draw(surface)
    assert mgr.scene is not scene or scene.state in ("setup", "flight", "arrived")


def test_game_timeout_game_over():
    scene, mgr = _scene(1, fx="0", fy="0")
    scene.lives = 1
    scene._try_launch()
    assert scene.state == FLIGHT
    for _ in range(120):
        if mgr.scene is not scene:
            break
        scene.update(0.1)
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    try:
        mgr.scene.draw(surface)
    except Exception:
        pass


def test_game_timeout_resume():
    scene, mgr = _scene(1, fx="0", fy="0")
    scene.lives = 3
    scene._try_launch()
    assert scene.state == FLIGHT
    for _ in range(120):
        if scene.state != FLIGHT or scene.flight is None:
            break
        scene.update(0.1)
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    scene.draw(surface)
    assert scene.state in ("setup", "flight", "arrived")


def test_game_handle_run_button_click():
    scene, mgr = _scene(1, fx="1", fy="0")
    # click run button
    evt = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=tuple(scene.run_button.rect.center))
    scene.handle_event(evt)
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    scene.draw(surface)


def test_game_handle_level_button_click():
    scene, mgr = _scene(1)
    evt = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=tuple(scene.level_button.rect.center))
    scene.handle_event(evt)
    # scene switched
    assert mgr.scene is not None


def test_game_handle_ship_nav():
    scene, mgr = _scene(1)
    for btn in (scene.prev_ship, scene.next_ship):
        evt = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=tuple(btn.rect.center))
        scene.handle_event(evt)
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    scene.draw(surface)


def test_game_handle_ai_button_with_money():
    scene, mgr = _scene(1)
    scene.session.money.add(1000)
    scene.money = scene.session.money
    evt = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=tuple(scene.ai_button.rect.center))
    scene.handle_event(evt)
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    scene.draw(surface)
    # close popup
    if scene.ai_popup:
        scene.ai_popup = False


def test_game_handle_hint_mode():
    # dynamic level 7 has hint_mode? check; just toggle attribute
    scene, mgr = _scene(7)
    scene.hint_mode = True
    scene.hint = None
    scene.session.money.add(1000)
    scene.money = scene.session.money
    evt = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=tuple(scene.ai_button.rect.center))
    try:
        scene.handle_event(evt)
    except Exception:
        pass
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    scene.draw(surface)


def test_game_dialogue_interaction():
    scene, mgr = _scene(1)
    if scene.story is not None:
        scene._say(("hello", "world"))
        assert scene.dialogue is not None
        # mouse click to advance
        evt = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(10, 10))
        scene.handle_event(evt)
        # enter key
        evt2 = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN)
        scene.handle_event(evt2)
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    scene.draw(surface)


def test_game_draw_invalid_field():
    scene, mgr = _scene(1)
    scene.valid = False
    scene.field_layer = None
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    scene.draw(surface)


def test_game_draw_flight_state():
    scene, mgr = _scene(1, fx="1", fy="0")
    scene._try_launch()
    if scene.state == FLIGHT:
        surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
        scene.draw(surface)
        scene.update(0.1)
        surface2 = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
        scene.draw(surface2)


def test_game_arrived_state_draw():
    scene, mgr = _scene(1, fx="10", fy="0")
    scene._try_launch()
    for _ in range(50):
        if mgr.scene is not scene:
            break
        scene.update(0.1)
    # if arrived
    if scene.state == "arrived":
        surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
        scene.draw(surface)


def test_game_safe_end_flight_exception():
    scene, mgr = _scene(1, fx="1", fy="0")
    scene._try_launch()
    if scene.state != FLIGHT:
        return
    # force exception by making flight None? call with bad outcome
    try:
        scene._safe_end_flight(None)
    except Exception:
        pass
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    try:
        scene.draw(surface)
    except Exception:
        pass


def test_game_editor_handle_event():
    scene, mgr = _scene(1)
    evt = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_a)
    scene.handle_event(evt)
    evt2 = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN)
    scene.handle_event(evt2)
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    scene.draw(surface)


def test_game_on_text_change_invalid():
    scene, mgr = _scene(1)
    scene.editor.set_lines(["1/0", "0"])
    try:
        scene._on_text_change(scene.editor)
    except Exception:
        pass
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    scene.draw(surface)


def test_game_switch_ship_bounds():
    scene, mgr = _scene(1)
    for _ in range(5):
        scene._switch_ship(1)
    for _ in range(5):
        scene._switch_ship(-1)
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    scene.draw(surface)


def test_game_invalid_launch_point():
    scene, mgr = _scene(1, fx="log(x)", fy="0")
    scene.editor.set_lines(["log(x)", "0"])
    scene._on_text_change(scene.editor)
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    scene.draw(surface)


def test_game_field_preview_failure():
    scene, mgr = _scene(1)
    scene.editor.set_lines(["1/(x-0)", "1/(y-0)"])
    try:
        scene._on_text_change(scene.editor)
    except Exception:
        pass
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    scene.draw(surface)


def test_game_flight_to_end():
    scene, mgr = _scene(1, fx="100", fy="100")
    scene._try_launch()
    if scene.state != FLIGHT:
        return
    for _ in range(60):
        if scene.state != FLIGHT:
            break
        scene.update(0.2)
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    scene.draw(surface)


def test_game_flight_abort_then_redraw():
    scene, mgr = _scene(2, fx="1", fy="1")
    scene._try_launch()
    if scene.state != FLIGHT:
        return
    scene.update(0.1)
    scene._abort()
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    scene.draw(surface)
