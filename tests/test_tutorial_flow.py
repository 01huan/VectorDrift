"""How the tutorial is reached: first Start -> story -> tutorial screen -> level select,
and the Tutorial button on level select (story -> tutorial screen, no menu)."""

from types import SimpleNamespace

import pygame
import pytest

from vector_drift import config
from vector_drift.scenes.base import SceneManager
from vector_drift.scenes import levels as levels_module
from vector_drift.scenes.levels import LevelSelectScene
from vector_drift.scenes.menu import MenuScene
from vector_drift.scenes.story import StoryScene
from vector_drift.scenes.tutorial_basics import BasicsScene
from vector_drift.scenes.tutorial_screen import TutorialScene

pytestmark = pytest.mark.usefixtures("pygame_display")


def _manager(seen_intro=False):
    audio = SimpleNamespace(play=lambda *a, **k: None, start_loop=lambda *a, **k: None,
                            stop_loop=lambda *a, **k: None, toggle_mute=lambda: None)
    manager = SceneManager(audio)
    manager.screen = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    manager.session.seen_intro = seen_intro
    return manager


def _key(manager, key):
    manager.scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key, mod=0, unicode="",
                                                  scancode=0))


def _click(manager, rect):
    for kind in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
        manager.scene.handle_event(pygame.event.Event(kind, button=1, pos=rect.center))


def _start(manager):
    manager.switch(MenuScene(manager))
    _key(manager, pygame.K_RETURN)


def _play_story_through(manager):
    story = manager.scene
    assert isinstance(story, StoryScene)
    for _ in range(len(story.panels)):
        story.update(3.0)               # long enough for the ship's line to be typed out
        story.update(3.0)
        story.next()


def _press_tutorial(manager):
    scene = LevelSelectScene(manager)
    manager.switch(scene)
    _click(manager, scene.tutorial_button.rect)
    assert isinstance(manager.scene, StoryScene)
    return manager.scene


def _on_tutorial_screen(manager, step=0):
    scene = manager.scene
    return isinstance(scene, TutorialScene) and scene.inner.index == step


# --- the first Start ----------------------------------------------------------------------
def test_first_start_plays_the_story_then_basics_then_level_select():
    manager = _manager()
    _start(manager)
    _play_story_through(manager)
    assert _on_tutorial_screen(manager)
    _key(manager, pygame.K_ESCAPE)
    assert isinstance(manager.scene, LevelSelectScene)


def test_skipping_the_first_story_still_opens_basics():
    manager = _manager()
    _start(manager)
    _click(manager, manager.scene.skip_button.rect)
    assert isinstance(manager.scene, TutorialScene)


def test_after_basics_start_goes_straight_to_level_select():
    manager = _manager()
    _start(manager)
    _key(manager, pygame.K_ESCAPE)                  # skip the story
    _key(manager, pygame.K_ESCAPE)                  # leave Basics half way
    _start(manager)
    assert isinstance(manager.scene, LevelSelectScene)


def test_finishing_basics_ends_at_level_select():
    manager = _manager(seen_intro=True)
    manager.switch(BasicsScene(manager, 3))
    _click(manager, manager.scene.card_button.rect)
    assert isinstance(manager.scene, LevelSelectScene)


# --- the story achievement -------------------------------------------------------------------
def test_the_first_story_watched_through_unlocks_is_anyone_out_there():
    manager = _manager()
    _start(manager)
    _play_story_through(manager)
    assert "is_anyone_out_there" in manager.session.achievements


def test_the_story_from_the_tutorial_button_unlocks_it_too():
    manager = _manager(seen_intro=True)
    _press_tutorial(manager)
    _play_story_through(manager)
    assert "is_anyone_out_there" in manager.session.achievements
    assert _on_tutorial_screen(manager)


def test_a_skipped_story_unlocks_nothing():
    manager = _manager()
    _start(manager)
    _key(manager, pygame.K_ESCAPE)
    assert "is_anyone_out_there" not in manager.session.achievements


# --- the Tutorial button ----------------------------------------------------------------------
def test_the_tutorial_button_plays_the_story_with_no_menu():
    manager = _manager(seen_intro=True)
    story = _press_tutorial(manager)
    assert story.index == 0


@pytest.mark.parametrize("how", ["played through", "skip", "esc"])
def test_the_story_from_the_tutorial_button_always_ends_on_the_tutorial_screen(how):
    manager = _manager(seen_intro=True)
    story = _press_tutorial(manager)
    if how == "played through":
        _play_story_through(manager)
    elif how == "skip":
        _click(manager, story.skip_button.rect)
    else:
        _key(manager, pygame.K_ESCAPE)
    assert _on_tutorial_screen(manager)
    assert ("is_anyone_out_there" in manager.session.achievements) == (how == "played through")


def test_the_tutorial_screen_exit_goes_back_to_level_select():
    manager = _manager(seen_intro=True)
    _press_tutorial(manager)
    _key(manager, pygame.K_ESCAPE)                  # skip the story
    _click(manager, manager.scene.exit_button.rect)
    assert isinstance(manager.scene, LevelSelectScene)


def test_level_select_has_no_tutorial_menu():
    manager = _manager(seen_intro=True)
    scene = LevelSelectScene(manager)
    for name in ("tutorial_menu", "tutorial_items", "tutorial_card"):
        assert not hasattr(scene, name)
    for name in ("TUTORIAL_ITEMS", "TUTORIAL_CARD"):
        assert not hasattr(levels_module, name)
    with pytest.raises(TypeError):
        LevelSelectScene(manager, tutorial_menu=True)
    manager.switch(scene)
    _key(manager, pygame.K_ESCAPE)                  # Esc goes back to the main menu as before
    assert isinstance(manager.scene, MenuScene)
