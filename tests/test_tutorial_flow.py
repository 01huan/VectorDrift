"""How the tutorial is reached: first Start -> story -> Basics -> level select,
and the Tutorial menu (Story, Basics, Field guide) on level select."""

from types import SimpleNamespace

import pygame
import pytest

from vector_drift import config
from vector_drift.scenes.base import SceneManager
from vector_drift.scenes.field_guide import FieldGuideScene, GuideDemoScene
from vector_drift.scenes.levels import LevelSelectScene
from vector_drift.scenes.menu import MenuScene
from vector_drift.scenes.story import StoryScene
from vector_drift.scenes.tutorial_basics import BasicsScene

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
        story.update(1.0)
        story.update(1.0)
        story.next()


def _open_tutorial_menu(manager):
    scene = LevelSelectScene(manager)
    manager.switch(scene)
    _click(manager, scene.tutorial_button.rect)
    assert scene.tutorial_menu
    return scene


# --- the first Start ----------------------------------------------------------------------
def test_first_start_plays_the_story_then_basics_then_level_select():
    manager = _manager()
    _start(manager)
    _play_story_through(manager)
    assert isinstance(manager.scene, BasicsScene) and manager.scene.index == 0
    _key(manager, pygame.K_ESCAPE)
    assert isinstance(manager.scene, LevelSelectScene) and not manager.scene.tutorial_menu


def test_skipping_the_first_story_still_opens_basics():
    manager = _manager()
    _start(manager)
    _click(manager, manager.scene.skip_button.rect)
    assert isinstance(manager.scene, BasicsScene)


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


def test_the_story_replayed_from_the_tutorial_menu_unlocks_it_too():
    manager = _manager(seen_intro=True)
    scene = _open_tutorial_menu(manager)
    _click(manager, scene.tutorial_items[0].rect)
    _play_story_through(manager)
    assert "is_anyone_out_there" in manager.session.achievements
    assert isinstance(manager.scene, LevelSelectScene) and manager.scene.tutorial_menu


def test_a_skipped_story_unlocks_nothing():
    manager = _manager()
    _start(manager)
    _key(manager, pygame.K_ESCAPE)
    assert "is_anyone_out_there" not in manager.session.achievements


# --- the Tutorial menu --------------------------------------------------------------------------
def test_tutorial_menu_items_open_story_basics_and_field_guide():
    for k, kind in enumerate((StoryScene, BasicsScene, FieldGuideScene)):
        manager = _manager(seen_intro=True)
        scene = _open_tutorial_menu(manager)
        _click(manager, scene.tutorial_items[k].rect)
        assert isinstance(manager.scene, kind)


def test_basics_from_the_tutorial_menu_starts_at_step_one():
    manager = _manager(seen_intro=True)
    scene = _open_tutorial_menu(manager)
    _click(manager, scene.tutorial_items[1].rect)
    assert manager.scene.index == 0


def test_esc_closes_the_tutorial_menu_on_level_select():
    manager = _manager(seen_intro=True)
    scene = _open_tutorial_menu(manager)
    _key(manager, pygame.K_ESCAPE)
    assert manager.scene is scene and not scene.tutorial_menu
    _key(manager, pygame.K_ESCAPE)                  # closed: Esc goes back to the main menu as before
    assert isinstance(manager.scene, MenuScene)


def test_the_open_menu_takes_all_input():
    manager = _manager(seen_intro=True)
    scene = _open_tutorial_menu(manager)
    _key(manager, pygame.K_RETURN)                  # would start a level
    assert manager.scene is scene and scene.tutorial_menu
    scene.draw(pygame.Surface((config.WINDOW_W, config.WINDOW_H)))


def test_field_guide_back_returns_to_level_select_with_the_menu_open():
    manager = _manager(seen_intro=True)
    scene = _open_tutorial_menu(manager)
    _click(manager, scene.tutorial_items[2].rect)
    page = manager.scene
    page.open(page.cards[0][0])
    assert isinstance(manager.scene, GuideDemoScene)
    _key(manager, pygame.K_ESCAPE)
    assert isinstance(manager.scene, FieldGuideScene)
    _key(manager, pygame.K_ESCAPE)
    assert isinstance(manager.scene, LevelSelectScene) and manager.scene.tutorial_menu
