"""Story: story.toml, planets, saving."""

from types import SimpleNamespace

import pygame
import pytest

from vector_drift import sprites
from vector_drift.data import LEVELS
from vector_drift.story import (INTRO_SEEN, PLANET_KINDS, StoryFormatError, get_story,
                                level_intro_key, parse_story)
from vector_drift.scenes.base import SceneManager

pytestmark = pytest.mark.usefixtures("pygame_display")


def _manager():
    audio = SimpleNamespace(play=lambda *a: None, start_loop=lambda *a: None,
                            stop_loop=lambda *a: None)
    return SceneManager(audio)


# --- story.toml ------------------------------------------------------------------
STORY_PENDING = {9}                 # story.toml gets these levels later


def _story_case(level):
    if level.id in STORY_PENDING:
        return pytest.param(level, id=f"level{level.id}", marks=pytest.mark.xfail(
            reason=f"level {level.id} story pending", strict=True))
    return pytest.param(level, id=f"level{level.id}")


@pytest.mark.parametrize("level", [_story_case(lv) for lv in LEVELS])
def test_every_fixed_level_has_a_story_with_a_drawable_planet(level):
    story = get_story()
    assert level.id in story.levels, f"level {level.id} has no [level.{level.id}] in story.toml"
    assert story.levels[level.id].planet in sprites.PLANETS


def test_every_planet_kind_has_a_painter():
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
