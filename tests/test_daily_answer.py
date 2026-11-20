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
