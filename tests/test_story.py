"""Story: story.toml, the dialogue box, when Poland speaks, the crawl, planets, saving."""

from types import SimpleNamespace

import pygame
import pytest

from vector_drift import config, sprites
from vector_drift.data import LEVELS
from vector_drift.story import (INTRO_SEEN, PLANET_KINDS, StoryFormatError, get_story,
                                level_intro_key, level_win_key, parse_story)
from vector_drift.scenes import game as game_module
from vector_drift.scenes.base import SceneManager
from vector_drift.scenes.dialogue import DialogueBox
from vector_drift.scenes.game import ARRIVED, GameScene
from vector_drift.physics import Outcome

pytestmark = pytest.mark.usefixtures("pygame_display")


def _manager():
    audio = SimpleNamespace(play=lambda *a: None, start_loop=lambda *a: None,
                            stop_loop=lambda *a: None)
    return SceneManager(audio)


def _scene(level_id, manager=None):
    manager = manager or _manager()
    manager.session.level_id = level_id
    scene = GameScene(manager)
    manager.switch(scene)
    return scene


def _key(target, key):
    target.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key, mod=0, unicode="", scancode=0))


def _read_all(scene):
    """Click through the open dialogue until it closes."""
    for _ in range(50):
        if scene.dialogue is None:
            return
        _key(scene, pygame.K_RETURN)
    raise AssertionError("dialogue never closed")


# --- story.toml ------------------------------------------------------------------
def test_every_fixed_level_has_a_story_with_a_drawable_planet():
    story = get_story()
    for level in LEVELS:
        assert level.id in story.levels, f"level {level.id} has no [level.{level.id}] in story.toml"
        assert story.levels[level.id].planet in sprites.PLANETS
    assert set(PLANET_KINDS) == set(sprites.PLANETS)


def test_the_four_levels_are_moon_mars_saturn_exoplanet():
    planets = [get_story().levels[i].planet for i in (1, 2, 3, 4)]
    assert planets == ["moon", "mars", "saturn", "exoplanet"]


def test_intro_text():
    intro = get_story().intro
    assert intro.title == "VECTOR DRIFT"
    assert intro.subtitle == "Cannot Into Space"
    assert len(intro.paragraphs) == 3


@pytest.mark.parametrize("data, message", [
    ({"level": {}, "fail": {"lines": ["x"]}}, r"missing \[intro\]"),
    ({"intro": {"title": "T", "subtitle": "S", "paragraphs": ["p"]}, "level": {"1": {
        "planet": "pluto", "intro": ["a"], "win": ["b"]}}, "fail": {"lines": ["x"]}}, "'planet'"),
    ({"intro": {"title": "T", "subtitle": "S", "paragraphs": ["p"]}, "level": {"1": {
        "planet": "moon", "intro": [], "win": ["b"]}}, "fail": {"lines": ["x"]}}, "'intro'"),
    ({"intro": {"title": "T", "subtitle": "S", "paragraphs": ["p"]}, "fail": {}}, "'lines'"),
])
def test_bad_story_files_are_rejected_with_a_reason(data, message):
    with pytest.raises(StoryFormatError, match=message):
        parse_story(data)


# --- dialogue box ----------------------------------------------------------------
def test_dialogue_first_press_finishes_the_line_then_moves_on():
    box = DialogueBox(("Hello there.", "Second."), (0, 0, 800, 600))
    box.update(0.05)
    assert box.typing
    box.advance()
    assert not box.typing and box.index == 0
    box.advance()
    assert box.index == 1 and box.typing
    box.advance()
    box.advance()
    assert box.done


def test_escape_skips_every_line():
    box = DialogueBox(("a", "b", "c"), (0, 0, 800, 600))
    _key(box, pygame.K_ESCAPE)
    assert box.done


def test_dialogue_draws():
    box = DialogueBox(("They say Poland cannot into space.",), (0, 0, 800, 600))
    box.update(0.3)
    box.draw(pygame.Surface((config.WINDOW_W, config.WINDOW_H)))


# --- when Poland speaks ----------------------------------------------------------
def test_level_intro_plays_once_and_blocks_launch_until_read(monkeypatch):
    manager = _manager()
    scene = _scene(1, manager)
    assert scene.dialogue is not None
    assert list(scene.dialogue.lines) == list(get_story().levels[1].intro)
    _key(scene, pygame.K_RETURN)        # finishes typing, does not launch
    assert scene.flight is None
    _read_all(scene)
    assert level_intro_key(1) in manager.session.story_seen
    assert _scene(1, manager).dialogue is None


def test_random_levels_have_no_story(monkeypatch):
    monkeypatch.setattr(game_module, "run_solver_async",
                        lambda *a, **k: SimpleNamespace(running=True, cancel=lambda: None,
                                                        error=None, result=None))
    scene = _scene(7)
    assert scene.story is None and scene.dialogue is None and scene.planet is None


def test_losing_a_life_says_a_fail_line():
    scene = _scene(1)
    _read_all(scene)
    scene.editor.set_lines(["0", "0"])
    scene._on_text_change(scene.editor)
    scene._try_launch()
    scene.flight.abort()
    scene._end_flight(Outcome.ABORTED)
    assert scene.dialogue is not None
    assert scene.dialogue.lines[0] in get_story().fail_lines


def test_first_clear_says_the_win_line_before_the_win_screen():
    manager = _manager()
    scene = _scene(2, manager)
    _read_all(scene)
    scene.editor.set_lines(["3", "0"])
    scene._on_text_change(scene.editor)
    scene._try_launch()
    scene._end_flight(Outcome.REACHED)
    assert scene.state == ARRIVED
    scene.update(config.WIN_DELAY + 0.1)
    assert scene.dialogue is not None
    assert list(scene.dialogue.lines) == list(get_story().levels[2].win)
    scene.update(1.0)
    assert manager.scene is scene                    # still waiting on Poland
    _read_all(scene)
    scene.update(0.01)
    assert manager.scene is not scene                # now the win screen
    assert level_win_key(2) in manager.session.story_seen


# --- crawl, planets, saving ------------------------------------------------------
def test_start_plays_the_crawl_only_the_first_time():
    from vector_drift.scenes.intro import IntroScene
    from vector_drift.scenes.levels import LevelSelectScene
    from vector_drift.scenes.menu import MenuScene

    manager = _manager()
    manager.switch(MenuScene(manager))
    _key(manager.scene, pygame.K_RETURN)
    intro = manager.scene
    assert isinstance(intro, IntroScene)
    intro.update(0.5)
    intro.draw(pygame.Surface((config.WINDOW_W, config.WINDOW_H)))
    _key(intro, pygame.K_SPACE)
    assert isinstance(manager.scene, LevelSelectScene)
    assert INTRO_SEEN in manager.session.story_seen

    manager.switch(MenuScene(manager))
    _key(manager.scene, pygame.K_RETURN)
    assert isinstance(manager.scene, LevelSelectScene)


def test_crawl_ends_by_itself():
    from vector_drift.scenes.intro import IntroScene
    from vector_drift.scenes.levels import LevelSelectScene

    manager = _manager()
    manager.switch(IntroScene(manager))
    for _ in range(600):
        if not isinstance(manager.scene, IntroScene):
            break
        manager.scene.update(0.25)
    assert isinstance(manager.scene, LevelSelectScene)


@pytest.mark.parametrize("kind", PLANET_KINDS)
def test_each_planet_draws(kind):
    surface = pygame.Surface((300, 300), pygame.SRCALPHA)
    sprites.draw_target(surface, (150, 150), 40, 0.0, planet=kind)
    assert surface.get_at((150, 150)).a == 255


def test_story_seen_survives_a_save_and_load():
    from vector_drift.account.integration import (load_guest_profile_into_session,
                                                  save_guest_profile)
    manager = _manager()
    manager.session.story_seen = {INTRO_SEEN, level_intro_key(1)}
    manager.session.stats = {"reason": "TIME UP", "attempts": 2}
    save_guest_profile(manager.session)

    fresh = _manager().session
    assert load_guest_profile_into_session(fresh)
    assert fresh.story_seen == {INTRO_SEEN, level_intro_key(1)}
    assert "story_seen" not in fresh.stats
