"""The daily map's reference answer: paid once per day, then shown and applied."""

import json
from datetime import date
from types import SimpleNamespace

import pygame
import pytest

from vector_drift import config, daily_level
from vector_drift.account.integration import apply_profile_to_session, session_to_profile
from vector_drift.account.models import PlayerProfile
from vector_drift.daily_records import get_record
from vector_drift.scenes.base import SceneManager
from vector_drift.scenes.game import GameScene

pytestmark = pytest.mark.usefixtures("pygame_display")

DAY = date(2026, 11, 19)
NEXT_DAY = date(2026, 11, 20)


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    """daily_today() answers DAY until a test moves it."""
    state = SimpleNamespace(day=DAY)
    monkeypatch.setattr(daily_level, "daily_today", lambda now=None: state.day)
    return state


def _manager(coins=23):
    audio = SimpleNamespace(play=lambda *a, **k: None, start_loop=lambda *a, **k: None,
                            stop_loop=lambda *a, **k: None)
    manager = SceneManager(audio)
    manager.session.money.add(coins)
    return manager


def _daily(manager=None, day=DAY):
    """The game screen on ``day``'s map."""
    manager = manager or _manager()
    manager.session.level_id = config.DAILY_LEVEL_ID
    manager.session.daily_day = day
    manager.session.random_seed = None
    scene = GameScene(manager)
    manager.switch(scene)
    return scene


def _reloaded(manager):
    """A new game launch that loads what ``manager`` saved."""
    row = json.loads(json.dumps(session_to_profile(manager.session, "u").to_row()))
    again = SceneManager(manager.audio)
    apply_profile_to_session(again.session, PlayerProfile.from_row(row, "u"), "u")
    return again


def _click(scene, rect):
    scene.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=rect.center))


def _key(scene, key):
    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key, mod=0, unicode=""))


def _press_answer(scene):
    _click(scene, scene.ai_button.rect)
    return scene.daily_popup


def _balance(scene):
    return int(scene.session.money)


def _answer_used(scene, day=DAY):
    record = get_record(scene.session, day)
    return bool(record and record["answer_used"])


def _draw(scene):
    scene.draw(pygame.Surface((config.WINDOW_W, config.WINDOW_H)))


# --- confirm and charge (task 20) --------------------------------------------------------

def test_the_first_answer_asks_with_the_price_and_balance():
    scene = _daily()
    popup = _press_answer(scene)

    assert popup is not None and popup.mode == "confirm"
    assert popup.message == "Show today's answer for 10 coins? (You have 23)"
    assert _balance(scene) == 23 and not _answer_used(scene)
    _draw(scene)


def test_confirming_charges_once_and_marks_the_day():
    scene = _daily()
    saves = []
    scene._save_progress = lambda: saves.append(int(scene.session.money))
    popup = _press_answer(scene)
    _click(scene, popup.confirm_button.rect)

    assert _balance(scene) == 23 - config.DAILY_ANSWER_COST
    assert _answer_used(scene)
    assert saves and saves[-1] == 23 - config.DAILY_ANSWER_COST
    assert scene.daily_popup.mode == "answer"
    _draw(scene)

    _click(scene, scene.daily_popup.close_button.rect)
    assert scene.daily_popup is None
    popup = _press_answer(scene)                        # same day: straight to the answer
    assert popup.mode == "answer"
    assert _balance(scene) == 23 - config.DAILY_ANSWER_COST


def test_enter_confirms_and_escape_cancels():
    scene = _daily()
    _press_answer(scene)
    _key(scene, pygame.K_ESCAPE)
    assert scene.daily_popup is None and _balance(scene) == 23

    _press_answer(scene)
    _key(scene, pygame.K_RETURN)
    assert scene.daily_popup.mode == "answer" and _balance(scene) == 13


def test_cancel_charges_nothing():
    scene = _daily()
    popup = _press_answer(scene)
    _click(scene, popup.cancel_button.rect)

    assert scene.daily_popup is None
    assert _balance(scene) == 23 and not _answer_used(scene)


def test_too_few_coins_only_explains():
    scene = _daily(_manager(coins=9))
    popup = _press_answer(scene)

    assert popup.mode == "short"
    assert popup.message == "You need 10 coins to see today's answer."
    _draw(scene)
    assert popup.buttons() == [(popup.close_button, "close")]
    _click(scene, popup.close_button.rect)

    assert scene.daily_popup is None
    assert _balance(scene) == 9 and not _answer_used(scene)


def test_a_balance_that_dropped_before_confirming_is_not_charged():
    scene = _daily()
    popup = _press_answer(scene)
    scene.session.money.spend(20)                       # 3 left when Confirm is pressed
    _click(scene, popup.confirm_button.rect)

    assert scene.daily_popup.mode == "short"
    assert _balance(scene) == 3 and not _answer_used(scene)


def test_a_paid_day_stays_free_after_reloading_the_save():
    first = _daily()
    _click(first, _press_answer(first).confirm_button.rect)

    again = _daily(_reloaded(first.manager))
    popup = _press_answer(again)

    assert popup.mode == "answer"
    assert _balance(again) == 13 and _answer_used(again)


def test_payment_belongs_to_the_day_being_played_not_the_clock(clock):
    scene = _daily()
    clock.day = NEXT_DAY                                # midnight passed during the run
    _click(scene, _press_answer(scene).confirm_button.rect)

    assert _answer_used(scene, DAY)
    assert get_record(scene.session, NEXT_DAY) is None


def test_another_day_must_be_paid_again():
    scene = _daily()
    _click(scene, _press_answer(scene).confirm_button.rect)

    other = _daily(scene.manager, day=NEXT_DAY)
    assert _press_answer(other).mode == "confirm"


def test_the_popup_is_modal():
    scene = _daily()
    _press_answer(scene)
    _click(scene, scene.lab_button.rect)
    assert not scene.lab_popup


# --- show and apply (task 21) --------------------------------------------------------------

def _pay(scene):
    _click(scene, _press_answer(scene).confirm_button.rect)
    return scene.daily_popup


def test_the_answer_shows_the_day_s_reference_formulas():
    scene = _daily()
    popup = _pay(scene)
    answer = daily_level.daily_map(DAY)

    assert popup.mode == "answer"
    assert (popup.fx, popup.fy) == (answer.fx, answer.fy)
    assert popup.answer_text() == f"Fx = {answer.fx}    Fy = {answer.fy}"
    assert [action for _b, action in popup.buttons()] == ["apply", "close"]
    _draw(scene)


def test_showing_the_answer_resets_the_map_but_keeps_the_lives():
    from vector_drift.scenes.game import SETUP
    scene = _daily()
    scene.lives -= 2
    scene.launch_pos = (1.0, 1.0)                       # where a time-up left the ship
    _pay(scene)

    assert scene.state == SETUP
    assert scene.launch_pos == scene.level.start
    assert scene.lives == scene.level.lives - 2
    assert scene.solution_used


def test_showing_a_paid_answer_again_resets_again():
    scene = _daily()
    _pay(scene)
    _click(scene, scene.daily_popup.close_button.rect)
    scene.launch_pos = (1.0, 1.0)
    _press_answer(scene)
    assert scene.launch_pos == scene.level.start


def test_the_answer_during_a_flight_ends_it_without_losing_a_life():
    from vector_drift.scenes.game import FLIGHT, SETUP
    scene = _daily()
    _pay(scene)
    _click(scene, scene.daily_popup.close_button.rect)
    scene.editor.set_lines(["1", "0"])
    scene._on_text_change(scene.editor)
    scene._try_launch()
    assert scene.state == FLIGHT
    lives = scene.lives

    _press_answer(scene)

    assert scene.state == SETUP and scene.flight is None
    assert scene.lives == lives
    assert scene.launch_pos == scene.level.start


def test_apply_fills_the_editor_and_closes():
    scene = _daily()
    scene.editor.set_lines(["2", "3"])
    popup = _pay(scene)
    answer = daily_level.daily_map(DAY)
    _click(scene, popup.apply_button.rect)

    assert scene.editor.lines == [answer.fx, answer.fy]
    assert scene.daily_popup is None


def test_the_applied_answer_reaches_the_target():
    from vector_drift.scenes.game import ARRIVED
    scene = _daily()
    _click(scene, _pay(scene).apply_button.rect)
    scene._try_launch()
    for _ in range(60 * 20):
        if scene.state == ARRIVED or scene.flight is None:
            break
        scene.update(1 / 60)
    assert scene.state == ARRIVED


# --- the price is the only cost (task 22) ----------------------------------------------------

def _coins(scene):
    return [p for p in scene.pickups if p.kind == "money"]


def _collect(scene, pickup):
    """What a flight does when the ship touches a coin."""
    pickup.consumed = True
    scene.flight = SimpleNamespace(pickup_events=[
        {"kind": "money", "center": pickup.center, "amount": 1}])
    scene._drain_pickup_events()
    scene.flight = None


def _win_with_the_answer(scene):
    """Pay (or reopen) the answer, apply it, fly to the Win screen."""
    from vector_drift.scenes.win import WinScene
    popup = _press_answer(scene)
    if popup.mode == "confirm":
        _click(scene, popup.confirm_button.rect)
    _click(scene, scene.daily_popup.apply_button.rect)
    scene._try_launch()
    for _ in range(60 * 25):
        if isinstance(scene.manager.scene, WinScene):
            break
        scene.update(1 / 60)
    assert isinstance(scene.manager.scene, WinScene)


def test_coins_still_pay_after_the_answer_once_per_spot():
    scene = _daily()
    _pay(scene)
    coins = _coins(scene)
    assert coins
    _collect(scene, coins[0])
    assert _balance(scene) == 13 + 1
    assert get_record(scene.session, DAY)["coins"] == 1

    again = _daily(scene.manager)                       # the same spot later that day
    _collect(again, SimpleNamespace(center=coins[0].center, consumed=False))
    assert _balance(again) == 14
    assert get_record(again.session, DAY)["coins"] == 1


def test_the_first_clear_after_the_answer_still_pays_its_reward():
    scene = _daily()
    _win_with_the_answer(scene)
    stats = scene.session.stats

    assert stats["clear_reward"] == config.CLEAR_REWARD
    assert _balance(scene) >= 13 + config.CLEAR_REWARD
    record = get_record(scene.session, DAY)
    assert record["cleared"] and record["clear_rewarded"] and record["answer_used"]
    assert record["best_time"] == pytest.approx(stats["total_time"])
    assert record["first_clear_lives_used"] == 0


def test_a_faster_clear_after_the_answer_still_updates_the_best_time():
    scene = _daily()
    record = get_record(scene.session, DAY, create=True)
    record.update(cleared=True, best_time=999.0, first_clear_lives_used=3, clear_rewarded=True)
    _win_with_the_answer(scene)

    assert record["best_time"] < 999.0
    assert record["first_clear_lives_used"] == 3          # only the first clear's run counts
    assert scene.session.stats["clear_reward"] == 0       # the day's reward was paid before
