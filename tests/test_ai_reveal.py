"""AI Solver on random levels: free to open, the answer is revealed once per map."""

from types import SimpleNamespace

import pygame
import pytest

from vector_drift import config
from vector_drift.physics import Outcome
from vector_drift.scenes import base as base_module, game as game_module, win as win_module
from vector_drift.scenes.base import SceneManager
from vector_drift.scenes.game import GameScene
from vector_drift.scenes.win import WinScene
from vector_drift.solver.interface import SimulationSpec, SolveResult
from vector_drift.story import all_seen_keys

pytestmark = pytest.mark.usefixtures("pygame_display")

FX, FY = "1.25*(7-x)", "-0.5*y"


@pytest.fixture(autouse=True)
def no_solver(monkeypatch):
    monkeypatch.setattr(game_module, "run_solver_async", lambda *a, **k: SimpleNamespace(
        running=True, cancel=lambda: None, stop=lambda *a: True, error=None, result=None))


def _manager(coins=0):
    audio = SimpleNamespace(play=lambda *a, **k: None, start_loop=lambda *a, **k: None,
                            stop_loop=lambda *a, **k: None)
    manager = SceneManager(audio)
    manager.session.story_seen = all_seen_keys()
    manager.session.money.add(coins)
    return manager


def _scene(manager, seed=123):
    manager.session.level_id = 7
    manager.session.random_seed = seed
    scene = GameScene(manager)
    manager.switch(scene)
    return scene


def _found(scene):
    """Pretend the background solver has found an answer."""
    scene.ai_result = SolveResult(solver_name="pso", solver_version="1", level_id=7,
                                  level_seed=None, success=True, best_score=1.8,
                                  best=SimulationSpec(template="t", fx_text=FX, fy_text=FY))


def _click(scene, rect):
    pos = rect.center
    scene.handle_event(pygame.event.Event(pygame.MOUSEMOTION, pos=pos, rel=(0, 0), buttons=(0, 0, 0)))
    scene.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=pos, button=1))


def _draw(scene, monkeypatch=None):
    texts = []
    if monkeypatch is not None:
        real = game_module.draw_text
        monkeypatch.setattr(game_module, "draw_text", lambda surface, text, *a, **k:
                            (texts.append(text), real(surface, text, *a, **k))[1])
    scene.draw(pygame.Surface((config.WINDOW_W, config.WINDOW_H)))
    return texts


def _open(scene):
    _draw(scene)
    _click(scene, scene.ai_button.rect)
    assert scene.ai_popup
    _found(scene)
    scene.update(1 / 60)


def _reveal(scene):
    _draw(scene)
    assert scene.ai_reveal_button.enabled
    _click(scene, scene.ai_reveal_button.rect)


def _collect(scene, pickup):
    pickup.consumed = True
    scene.flight = SimpleNamespace(pickup_events=[
        {"kind": "money", "center": pickup.center, "amount": 1}])
    scene._drain_pickup_events()
    scene.flight = None


def test_reveal_label_uses_the_config_price():
    scene = _scene(_manager())
    assert config.AI_SOLVER_COST == 10
    assert scene.ai_reveal_button.label == "Reveal (10 coins)"


def test_no_coins_opens_the_window_but_hides_the_answer(monkeypatch):
    scene = _scene(_manager())
    _draw(scene)
    assert scene.ai_button.enabled
    _open(scene)
    texts = _draw(scene, monkeypatch)

    assert FX not in texts and FY not in texts
    assert not scene.ai_reveal_button.enabled
    assert "Need 10 coins (you have 0)." in texts
    _click(scene, scene.ai_apply_button.rect)               # hidden Apply does nothing
    assert scene.editor.lines == ["", ""]
    assert int(scene.session.money) == 0 and not scene.solution_used


def test_revealing_charges_once_per_map(monkeypatch):
    manager = _manager(coins=12)
    scene = _scene(manager)
    _open(scene)
    _reveal(scene)

    assert int(manager.session.money) == 2 and scene.solution_used
    assert FX in _draw(scene, monkeypatch)
    _click(scene, scene.ai_apply_button.rect)
    assert scene.editor.lines == [FX, FY]

    # Reopen, and reopen from another launch point: shown, no charge.
    _open(scene)
    assert FX in _draw(scene, monkeypatch)
    _click(scene, scene.ai_close_button.rect)
    scene.launch_pos = (-3.0, 1.0)
    _open(scene)
    assert FX in _draw(scene, monkeypatch)
    retry = _scene(manager)                                 # same map, new attempt
    assert not retry.solution_used
    _open(retry)
    assert FX in _draw(retry, monkeypatch)
    assert retry.solution_used                              # seeing it again counts
    assert int(manager.session.money) == 2


def test_new_map_needs_a_new_payment(monkeypatch):
    manager = _manager(coins=10)
    _reveal_scene = _scene(manager)
    _open(_reveal_scene)
    _reveal(_reveal_scene)
    other = _scene(manager, seed=456)
    _open(other)
    texts = _draw(other, monkeypatch)
    assert FX not in texts
    assert not other.ai_reveal_button.enabled
    assert "Need 10 coins (you have 0)." in texts


def test_reveal_takes_back_this_runs_coins_without_respawning_them():
    manager = _manager(coins=10)
    scene = _scene(manager)
    coin = next(p for p in scene.pickups if p.kind == "money")
    _collect(scene, coin)
    assert int(manager.session.money) == 11
    _open(scene)
    _reveal(scene)

    assert int(manager.session.money) == 0                  # 11 - 1 returned - 10 paid
    assert coin.consumed                                    # map is not reset
    assert not manager.session.collected_random_coins
    assert not next(p for p in _scene(manager).pickups if p.kind == "money").consumed


def test_this_runs_coins_do_not_count_toward_the_price(monkeypatch):
    manager = _manager(coins=9)
    scene = _scene(manager)
    _collect(scene, next(p for p in scene.pickups if p.kind == "money"))
    _open(scene)
    texts = _draw(scene, monkeypatch)
    assert not scene.ai_reveal_button.enabled
    assert "Need 10 coins (you have 9)." in texts


def test_a_win_after_the_reveal_is_marked_and_not_recorded(monkeypatch):
    manager = _manager(coins=10)
    manager.session.records[7] = 99.0
    scene = _scene(manager)
    _open(scene)
    _reveal(scene)
    _click(scene, scene.ai_close_button.rect)

    scene.flight = SimpleNamespace(time=2.0, trail=[])
    scene._end_flight(Outcome.REACHED)
    for _ in range(120):
        if not isinstance(manager.scene, GameScene):
            break
        scene.update(1 / 60)
    assert isinstance(manager.scene, WinScene)
    assert manager.session.records == {7: 99.0}
    assert manager.session.stats["solution_used"]

    texts = []
    for module in (base_module, win_module):
        real = module.draw_text
        monkeypatch.setattr(module, "draw_text", lambda surface, text, *a, _real=real, **k:
                            (texts.append(text), _real(surface, text, *a, **k))[1])
    manager.scene.draw(pygame.Surface((config.WINDOW_W, config.WINDOW_H)))
    assert any("Solution used" in t for t in texts)
