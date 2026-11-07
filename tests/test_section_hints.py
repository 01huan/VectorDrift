"""Hints on a multi-section level: one per section, and the answer page resets only that section."""

from dataclasses import replace
from types import SimpleNamespace

import pygame
import pytest

from vector_drift import config
from vector_drift.data import ObstacleSpec, PickupSpec, SectionSpec, multi_section_level
from vector_drift.hints import HintAnswer, LevelHint
from vector_drift.scenes import game as game_module
from vector_drift.scenes.base import SceneManager
from vector_drift.scenes.game import FLIGHT, PANNING, SETUP, GameScene

pytestmark = pytest.mark.usefixtures("pygame_display")

ROCK = ObstacleSpec(center=(0.0, 5.0), radius=0.8)
SHIELD = PickupSpec(center=(0.0, -5.0), radius=0.45, kind="shield")
TWO = multi_section_level(
    id=90, name="Two Screens", ship_id="ship01", lives=3,
    sections=(
        SectionSpec(start=(-7.0, 0.0), target_center=(7.0, 0.0)),
        SectionSpec(start=(-7.0, 0.0), target_center=(7.0, 0.0), time_limit=4.0,
                    obstacles=(ROCK,), pickups=(SHIELD,)),
    ),
)
HINTS = {
    0: LevelHint(level_id=90, steps=("One A.", "One B.", "One C."), answer_note="Right.",
                 answers=(HintAnswer("5", "0"),), section=1),
    1: LevelHint(level_id=90, steps=("Two A.", "Two B."), answer_note="Right again.",
                 answers=(HintAnswer("6", "0"),), section=2),
}


@pytest.fixture(autouse=True)
def fake_level(monkeypatch):
    real_level, real_hint = game_module.get_level, game_module.get_hint
    monkeypatch.setattr(game_module, "get_level",
                        lambda lid, seed=None: TWO if lid == TWO.id else real_level(lid, seed=seed))
    monkeypatch.setattr(game_module, "get_hint",
                        lambda lid, section=0: HINTS.get(section) if lid == TWO.id
                        else real_hint(lid, section))
    monkeypatch.setattr(config, "FREE_ANSWER_LEVELS", config.FREE_ANSWER_LEVELS + (TWO.id,))


def _scene():
    audio = SimpleNamespace(play=lambda *a, **k: None, start_loop=lambda *a, **k: None,
                            stop_loop=lambda *a, **k: None)
    manager = SceneManager(audio)
    manager.session.level_id = TWO.id
    manager.session.fx_text, manager.session.fy_text = "5", "0"
    manager.session.hint_answer_confirmed = True        # free answer, no question in the way
    scene = GameScene(manager)
    manager.switch(scene)
    return scene


def _click(scene, rect):
    scene.handle_event(pygame.event.Event(pygame.MOUSEMOTION, pos=rect.center, rel=(0, 0), buttons=(0, 0, 0)))
    scene.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=rect.center, button=1))


def _key(scene, key):
    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key, mod=0, unicode="", scancode=0))


def _open_hint(scene):
    scene.draw(pygame.Surface((config.WINDOW_W, config.WINDOW_H)))
    _click(scene, scene.ai_button.rect)
    assert scene.hint_popup is not None
    return scene.hint_popup


def _show_answer(scene):
    popup = scene.hint_popup or _open_hint(scene)
    while not popup.on_answer_page:
        _key(scene, pygame.K_RIGHT)
    return popup


def _fly(scene, fx, fy):
    scene.editor.set_lines([fx, fy])
    scene._on_text_change(scene.editor)
    scene._try_launch()
    while scene.state == FLIGHT:
        scene.update(0.05)


def _to_section_two(scene):
    _fly(scene, "5", "0")
    while scene.state == PANNING:
        scene.update(0.05)
    assert scene.section_index == 1 and scene.state == SETUP


def test_each_section_shows_its_own_hint():
    scene = _scene()
    assert _open_hint(scene).hint is HINTS[0]
    _key(scene, pygame.K_ESCAPE)

    _to_section_two(scene)

    popup = _open_hint(scene)
    assert popup.hint is HINTS[1]
    assert popup.answer_page == len(HINTS[1].steps)


def test_hint_progress_does_not_carry_into_the_next_section():
    scene = _scene()
    popup = _open_hint(scene)
    _key(scene, pygame.K_RIGHT)
    _key(scene, pygame.K_RIGHT)
    assert popup.page == 2
    _key(scene, pygame.K_ESCAPE)

    _to_section_two(scene)

    assert _open_hint(scene).page == 0


def test_reaching_a_checkpoint_closes_the_hint():
    scene = _scene()
    scene._try_launch()
    _open_hint(scene)                                   # usable during flight
    assert scene.state == FLIGHT
    while scene.state == FLIGHT:
        scene.update(0.05)

    assert scene.state == PANNING
    assert scene.hint_popup is None


def test_the_answer_page_in_section_two_resets_only_section_two():
    scene = _scene()
    _to_section_two(scene)
    _fly(scene, "0.5", "0")                             # TIME UP: resume further right
    assert scene.launch_pos != TWO.sections[1].start
    lives = scene.lives
    scene.pickups[0].consumed = True                    # the shield was taken ...
    scene.level = replace(scene.level, obstacles=())    # ... and a shockwave cleared the rock

    _show_answer(scene)

    assert scene.section_index == 1                     # section 1 is not flown again
    assert scene.launch_pos == TWO.sections[1].start    # back to the checkpoint
    assert scene.lives == lives
    assert scene.solution_used
    assert scene.level.obstacles == (ROCK,)
    assert [p.consumed for p in scene.pickups] == [False]
    assert scene.state == SETUP


def test_applying_a_section_answer_fills_the_editor():
    scene = _scene()
    _to_section_two(scene)
    popup = _show_answer(scene)
    scene.draw(pygame.Surface((config.WINDOW_W, config.WINDOW_H)))
    _click(scene, popup.apply_buttons[0].rect)

    assert scene.editor.lines == ["6", "0"]
    assert scene.hint_popup is None


def test_the_answer_page_on_a_one_screen_level_still_resets_that_level():
    audio = SimpleNamespace(play=lambda *a, **k: None, start_loop=lambda *a, **k: None,
                            stop_loop=lambda *a, **k: None)
    manager = SceneManager(audio)
    manager.session.level_id = 1
    manager.session.hint_answer_confirmed = True
    scene = GameScene(manager)
    manager.switch(scene)
    scene.launch_pos = (-2.0, 0.0)

    _show_answer(scene)

    assert scene.launch_pos == (-7.0, 0.0) and scene.section_index == 0
    assert scene.solution_used
