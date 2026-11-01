"""The Hint button on fixed levels: pages, answer confirmation, reset, records, reminder."""

from dataclasses import replace
from types import SimpleNamespace

import pygame
import pytest

from vector_drift import config
from vector_drift.image_assets import COIN_TRADE
from vector_drift.hints import get_hint
from vector_drift.story import all_seen_keys
from vector_drift.ui import coin_price_parts
from vector_drift.scenes.base import SceneManager
from vector_drift.scenes import game as game_module
from vector_drift.scenes.game import FLIGHT, SETUP, GameScene
from vector_drift.scenes.win import WinScene

pytestmark = pytest.mark.usefixtures("pygame_display")


@pytest.fixture(autouse=True)
def no_solver(monkeypatch):
    """Record solver starts instead of running PSO in the background."""
    calls = []

    def fake_run(solver, level, **kwargs):
        calls.append(level.id)
        return SimpleNamespace(running=True, cancel=lambda: None, error=None, result=None)

    monkeypatch.setattr(game_module, "run_solver_async", fake_run)
    return calls


def _manager():
    audio = SimpleNamespace(play=lambda *a: None, start_loop=lambda *a: None,
                            stop_loop=lambda *a: None)
    manager = SceneManager(audio)
    manager.session.story_seen = all_seen_keys()     # no story dialogue in the way
    return manager


def _scene(level_id, manager=None):
    manager = manager or _manager()
    manager.session.level_id = level_id
    scene = GameScene(manager)
    manager.switch(scene)
    return scene


def _click(scene, rect):
    pos = rect.center
    scene.handle_event(pygame.event.Event(pygame.MOUSEMOTION, pos=pos, rel=(0, 0), buttons=(0, 0, 0)))
    scene.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=pos, button=1))


def _key(scene, key):
    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key, mod=0, unicode="", scancode=0))


def _draw(scene):
    scene.draw(pygame.Surface((config.WINDOW_W, config.WINDOW_H)))


def _open_hint(scene):
    _draw(scene)
    _click(scene, scene.ai_button.rect)
    assert scene.hint_popup is not None


def _to_last_step(scene):
    popup = scene.hint_popup
    while popup.page < popup.answer_page - 1:
        _key(scene, pygame.K_RIGHT)


def _show_answer(scene):
    """Open the hint and page through to the answer, confirming if asked."""
    if scene.hint_popup is None:
        _open_hint(scene)
    _to_last_step(scene)
    _key(scene, pygame.K_RIGHT)
    if scene.hint_popup.confirming:
        _click(scene, scene.hint_popup.confirm_button.rect)
    assert scene.hint_popup.on_answer_page


def _lose_a_life(scene):
    scene.editor.set_lines(["-50", "0"])           # straight out of the left edge
    scene._on_text_change(scene.editor)
    scene._try_launch()
    flight = scene.flight
    while scene.flight is flight:
        scene.update(1 / 60)


# --- 1. Hint on fixed levels, AI Solver on random levels ----------------------------

@pytest.mark.parametrize("level_id", [1, 2, 3])
def test_fixed_levels_show_hint_and_never_start_the_solver(level_id, no_solver):
    scene = _scene(level_id)
    for _ in range(5):
        scene.update(1 / 60)
    _draw(scene)

    assert scene.ai_button.label == "Hint"
    assert scene.ai_button.enabled
    assert no_solver == []


@pytest.mark.parametrize("level_id", [7, 8])
def test_random_levels_keep_the_ai_solver(level_id, no_solver):
    scene = _scene(level_id)
    _draw(scene)

    assert scene.ai_button.label in ("AI Solver", "Solving…")
    assert no_solver == [level_id]
    _click(scene, scene.ai_button.rect)
    assert scene.hint_popup is None


def test_hint_is_available_before_any_failure():
    scene = _scene(1)
    assert scene.lives == scene.level.lives

    _open_hint(scene)

    assert scene.hint_popup.page == 0


# --- 2. Steps are free, the answer page counts --------------------------------------

def test_hint_pages_go_forward_back_and_close():
    scene = _scene(2)
    _open_hint(scene)
    popup = scene.hint_popup

    assert popup.answer_page == len(get_hint(2).steps)
    _key(scene, pygame.K_RIGHT)
    assert popup.page == 1
    _click(scene, popup.prev_button.rect)
    assert popup.page == 0
    _click(scene, popup.next_button.rect)
    assert popup.page == 1
    _click(scene, popup.close_button.rect)
    assert scene.hint_popup is None


def test_reading_the_steps_does_not_count_as_using_the_solution():
    scene = _scene(2)
    _open_hint(scene)
    _to_last_step(scene)
    _key(scene, pygame.K_ESCAPE)

    assert scene.hint_popup is None
    assert not scene.solution_used


def test_reaching_the_answer_page_counts_even_without_apply():
    scene = _scene(2)
    _show_answer(scene)

    assert scene.solution_used
    assert scene.editor.lines == ["", ""]          # nothing applied


def test_apply_fills_the_editor_with_that_answer():
    scene = _scene(3)
    scene.session.money.add(config.HINT_ANSWER_COST)      # level 3's answer is paid
    _show_answer(scene)
    _click(scene, scene.hint_popup.apply_buttons[1].rect)

    answer = get_hint(3).answers[1]
    assert scene.editor.lines == [answer.fx, answer.fy]
    assert scene.hint_popup is None


# --- 3. Confirmation once per game launch -------------------------------------------

def test_answer_confirmation_is_asked_once_per_game_launch():
    manager = _manager()
    scene = _scene(2, manager)
    _open_hint(scene)
    _to_last_step(scene)
    _key(scene, pygame.K_RIGHT)
    popup = scene.hint_popup
    assert popup.confirming and not popup.on_answer_page
    assert not scene.solution_used

    _click(scene, popup.cancel_button.rect)         # backing out shows nothing
    assert not popup.confirming and not popup.on_answer_page
    assert not scene.solution_used

    _key(scene, pygame.K_RIGHT)
    _click(scene, popup.confirm_button.rect)
    assert popup.on_answer_page and scene.solution_used

    # Later in the same game launch, on any level: no question.
    for level_id in (2, 1):
        again = _scene(level_id, manager)
        _open_hint(again)
        _to_last_step(again)
        _key(again, pygame.K_RIGHT)
        assert again.hint_popup.on_answer_page and not again.hint_popup.confirming

    # A new game launch asks again.
    fresh = _scene(2)
    _open_hint(fresh)
    _to_last_step(fresh)
    _key(fresh, pygame.K_RIGHT)
    assert fresh.hint_popup.confirming


# --- 4. Showing the answer resets the level, lives stay -----------------------------

def test_showing_the_answer_resets_the_level_but_keeps_the_lives():
    scene = _scene(3)
    scene.session.money.add(config.HINT_ANSWER_COST)      # level 3's answer is paid
    start, specs = scene.level.start, scene.level.obstacles
    scene.lives = 3
    scene.launch_pos = (-2.0, 1.0)
    scene.pickups[0].consumed = True
    scene.level = replace(scene.level, obstacles=specs[3:])

    _show_answer(scene)

    assert scene.lives == 3
    assert scene.launch_pos == start
    assert scene.level.obstacles == specs
    assert not any(p.consumed for p in scene.pickups)
    assert scene.state == SETUP


def test_showing_the_answer_during_a_flight_ends_it_without_losing_a_life():
    scene = _scene(1)
    scene.editor.set_lines(["0.1", "0"])
    scene._on_text_change(scene.editor)
    scene._try_launch()
    scene.update(0.5)
    assert scene.state == FLIGHT

    _show_answer(scene)

    assert scene.state == SETUP and scene.flight is None
    assert scene.lives == scene.level.lives
    assert scene.launch_pos == scene.level.start


# --- 5. A win with the solution is marked and not recorded --------------------------

def _win(scene):
    answer = get_hint(scene.level.id).answers[0]
    scene.editor.set_lines([answer.fx, answer.fy])
    scene._on_text_change(scene.editor)
    scene._try_launch()
    for _ in range(60 * 20):
        if not isinstance(scene.manager.scene, GameScene):
            break
        scene.update(1 / 60)
    assert isinstance(scene.manager.scene, WinScene)


def test_a_win_without_the_answer_sets_the_record():
    scene = _scene(1)
    _win(scene)

    assert 1 in scene.session.records
    assert not scene.session.stats["solution_used"]


def test_a_win_after_the_answer_is_marked_and_not_recorded(monkeypatch):
    from vector_drift.scenes import base as base_module, win as win_module
    scene = _scene(1)
    scene.session.records[1] = 99.0
    _show_answer(scene)
    _key(scene, pygame.K_ESCAPE)
    _win(scene)

    assert scene.session.records == {1: 99.0}
    assert scene.session.stats["solution_used"]

    texts = []
    for module in (base_module, win_module):
        real = module.draw_text
        monkeypatch.setattr(module, "draw_text", lambda surface, text, *a, _real=real, **k:
                            (texts.append(text), _real(surface, text, *a, **k))[1])
    scene.manager.scene.draw(pygame.Surface((config.WINDOW_W, config.WINDOW_H)))
    assert any("Solution used" in t for t in texts)


def test_replaying_clears_the_solution_mark():
    manager = _manager()
    scene = _scene(1, manager)
    _show_answer(scene)
    _key(scene, pygame.K_ESCAPE)
    _win(scene)

    _key(manager.scene, pygame.K_RETURN)            # Replay
    replay = manager.scene
    assert isinstance(replay, GameScene) and replay is not scene
    assert not replay.solution_used
    _win(replay)
    assert 1 in manager.session.records
    assert not manager.session.stats["solution_used"]


def test_reentering_the_level_clears_the_solution_mark():
    manager = _manager()
    scene = _scene(2, manager)
    _show_answer(scene)
    assert scene.solution_used

    assert not _scene(2, manager).solution_used


# --- 6. No "try Hint" reminder after lost lives ------------------------------------

@pytest.mark.parametrize("level_id", [1, 7])
def test_losing_lives_never_pops_a_hint_reminder(monkeypatch, level_id):
    texts = []
    real = game_module.draw_text
    monkeypatch.setattr(game_module, "draw_text", lambda surface, text, *a, **k:
                        (texts.append(text), real(surface, text, *a, **k))[1])
    scene = _scene(level_id)
    for _ in range(4):
        _lose_a_life(scene)
        scene.update(1 / 60)
        _draw(scene)

    assert scene.hint_popup is None
    assert not any("Hint" in t and t != "Hint" for t in texts)


# --- 7. Paying for the answer -------------------------------------------------------

def _collect(scene, pickup):
    """What a flight does when the ship touches a coin."""
    pickup.consumed = True
    scene.flight = SimpleNamespace(pickup_events=[
        {"kind": "money", "center": pickup.center, "amount": 1}])
    scene._drain_pickup_events()
    scene.flight = None


def _coin(scene):
    return next(p for p in scene.pickups if p.kind == "money")


def _ask_for_answer(scene):
    if scene.hint_popup is None:
        _open_hint(scene)
    _to_last_step(scene)
    _key(scene, pygame.K_RIGHT)
    return scene.hint_popup


def _rows_drawn(scene, monkeypatch):
    """Every icon row (text and coin pictures) drawn in one frame."""
    from vector_drift import ui
    from vector_drift.scenes import hint_popup as popup_module
    rows = []
    real = ui.draw_icon_row

    def spy(surface, parts, *a, **k):
        rows.append(list(parts))
        return real(surface, parts, *a, **k)

    monkeypatch.setattr(ui, "draw_icon_row", spy)
    monkeypatch.setattr(popup_module, "draw_icon_row", spy)
    _draw(scene)
    return rows


def _texts_drawn(scene, monkeypatch):
    from vector_drift.scenes import hint_popup as popup_module
    texts = []
    real = popup_module.draw_text
    monkeypatch.setattr(popup_module, "draw_text", lambda surface, text, *a, **k:
                        (texts.append(text), real(surface, text, *a, **k))[1])
    _draw(scene)
    return " ".join(texts)


def test_answer_settings_live_in_config():
    assert config.FREE_ANSWER_LEVELS == (1, 2)
    assert config.HINT_ANSWER_COST == 10


@pytest.mark.parametrize("level_id", [1, 2, 3])
def test_hint_button_works_with_no_coins(level_id):
    scene = _scene(level_id)
    _draw(scene)
    assert int(scene.session.money) == 0
    assert scene.ai_button.enabled
    _open_hint(scene)
    assert int(scene.session.money) == 0


def test_new_player_sees_every_step_and_the_free_answer_on_level_one():
    scene = _scene(1)
    _open_hint(scene)
    popup = scene.hint_popup
    seen = {popup.page}
    while popup.page < popup.answer_page - 1:
        _key(scene, pygame.K_RIGHT)
        seen.add(popup.page)
    assert seen == set(range(popup.answer_page))
    _show_answer(scene)
    assert int(scene.session.money) == 0


def test_no_coins_on_level_three_shows_steps_but_not_the_answer(monkeypatch):
    scene = _scene(3)
    popup = _ask_for_answer(scene)

    assert not popup.on_answer_page and not popup.confirming
    assert popup.page == popup.answer_page - 1
    assert int(scene.session.money) == 0
    assert not scene.solution_used
    assert coin_price_parts(10, 0, "Need", config.WARNING) in _rows_drawn(scene, monkeypatch)


def test_paying_on_level_three_charges_once_per_game_launch(monkeypatch):
    manager = _manager()
    manager.session.money.add(12)
    scene = _scene(3, manager)
    popup = _ask_for_answer(scene)
    assert popup.confirming
    assert coin_price_parts(10, 12) in _rows_drawn(scene, monkeypatch)
    assert "coins?" not in _texts_drawn(scene, monkeypatch)
    assert int(manager.session.money) == 12                # nothing taken yet

    _click(scene, popup.confirm_button.rect)
    assert popup.on_answer_page and scene.solution_used
    assert int(manager.session.money) == 2

    _key(scene, pygame.K_ESCAPE)                            # close, reopen: no charge, no question
    again = _ask_for_answer(scene)
    assert again.on_answer_page and not again.confirming
    later = _ask_for_answer(_scene(3, manager))             # also on a new attempt
    assert later.on_answer_page and not later.confirming
    assert int(manager.session.money) == 2


def test_cancelling_the_payment_takes_nothing():
    manager = _manager()
    manager.session.money.add(10)
    scene = _scene(3, manager)
    popup = _ask_for_answer(scene)
    _click(scene, popup.cancel_button.rect)
    assert int(manager.session.money) == 10 and not scene.solution_used


def test_revealing_takes_back_this_runs_coins_and_they_return():
    manager = _manager()
    scene = _scene(2, manager)                              # free answer, one coin
    coin_center = _coin(scene).center
    _collect(scene, _coin(scene))
    assert int(manager.session.money) == 1

    _show_answer(scene)

    assert int(manager.session.money) == 0
    assert (2, coin_center) not in manager.session.collected_money_pickups
    assert not _coin(scene).consumed                        # back on the reset map

    _collect(scene, _coin(scene))                           # after the reveal: no pay
    assert int(manager.session.money) == 0
    assert (2, coin_center) not in manager.session.collected_money_pickups
    assert not _coin(_scene(2, manager)).consumed           # still there next time


def test_this_runs_coins_do_not_count_toward_the_price(monkeypatch):
    manager = _manager()
    manager.session.money.add(9)
    scene = _scene(4, manager)
    _collect(scene, _coin(scene))                           # 10 on screen, 9 to spend
    popup = _ask_for_answer(scene)
    assert not popup.on_answer_page and not popup.confirming
    assert coin_price_parts(10, 9, "Need", config.WARNING) in _rows_drawn(scene, monkeypatch)
    assert int(manager.session.money) == 10


def test_paying_with_this_runs_coins_counts_only_earlier_coins():
    manager = _manager()
    manager.session.money.add(10)
    scene = _scene(4, manager)
    _collect(scene, _coin(scene))
    popup = _ask_for_answer(scene)
    assert popup.confirming
    _click(scene, popup.confirm_button.rect)
    assert int(manager.session.money) == 0                  # 11 - 1 returned - 10 paid
    assert not _coin(scene).consumed


# --- the answer's price on the last step -----------------------------------------

@pytest.mark.parametrize("coins, short", [(12, False), (0, True)])
def test_answer_button_shows_the_price_red_when_short(monkeypatch, coins, short):
    manager = _manager()
    manager.session.money.add(coins)
    scene = _scene(3, manager)
    _open_hint(scene)
    _to_last_step(scene)
    rows = _rows_drawn(scene, monkeypatch)
    button = scene.hint_popup.next_button
    assert (button.label, button.price, button.price_short) == ("Answer", 10, short)
    colour = config.DANGER if short else (255, 255, 255)
    assert [("Answer", (255, 255, 255)), COIN_TRADE, (10, colour)] in rows


def test_free_or_paid_answer_shows_no_price():
    manager = _manager()
    scene = _scene(1, manager)                              # free level
    _open_hint(scene)
    _to_last_step(scene)
    _draw(scene)
    assert scene.hint_popup.next_button.price is None

    manager.session.paid_answer_levels.add(3)               # already paid this launch
    scene = _scene(3, manager)
    _open_hint(scene)
    _to_last_step(scene)
    _draw(scene)
    assert scene.hint_popup.next_button.price is None


def test_steps_before_the_last_show_no_price():
    scene = _scene(3)
    _open_hint(scene)
    _draw(scene)
    assert scene.hint_popup.page < scene.hint_popup.answer_page - 1
    assert scene.hint_popup.next_button.price is None
