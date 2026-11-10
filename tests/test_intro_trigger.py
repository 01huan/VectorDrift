"""When the intro story plays: the first Start, and the Tutorial button on level select.

seen_intro is saved with the coins and progress (guest save and cloud
profile, inside stats) the moment the story starts.
"""
import json
from types import SimpleNamespace

import pygame
import pytest

from vector_drift.account.integration import (
    SEEN_INTRO_KEY,
    apply_guest_profile_to_session,
    apply_profile_to_session,
    clear_guest_profile,
    load_guest_profile_into_session,
    profiles_equal,
    reset_session_to_guest,
    save_guest_profile,
    session_to_profile,
)
from vector_drift.account.local_profile_manager import LocalProfileManager
from vector_drift.account.models import PlayerProfile
from vector_drift.scenes import levels as levels_module
from vector_drift.scenes.base import SceneManager, Session
from vector_drift.scenes.levels import LevelSelectScene
from vector_drift.scenes.menu import MenuScene
from vector_drift.scenes.story import StoryScene

pytestmark = pytest.mark.usefixtures("pygame_display")


def _manager(account=None):
    audio = SimpleNamespace(play=lambda *a, **k: None, start_loop=lambda *a, **k: None,
                            stop_loop=lambda *a, **k: None, toggle_mute=lambda: None)
    return SceneManager(audio, account)


def _menu(seen_intro=False, account=None):
    manager = _manager(account)
    manager.session.seen_intro = seen_intro
    menu = MenuScene(manager)
    manager.switch(menu)
    return menu


def _click(scene, button):
    scene.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=button.rect.center))


def _enter(scene):
    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN, mod=0,
                                          unicode="\r", scancode=0))


def _escape(scene):
    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, mod=0,
                                          unicode="", scancode=0))


# --- the first Start ----------------------------------------------------------------

def test_a_new_session_has_not_seen_the_intro():
    assert Session().seen_intro is False


@pytest.mark.parametrize("press", [lambda m: _click(m, m.start_button), _enter])
def test_the_first_start_plays_the_story(press):
    menu = _menu(seen_intro=False)
    press(menu)
    assert isinstance(menu.manager.scene, StoryScene)


@pytest.mark.parametrize("press", [lambda m: _click(m, m.start_button), _enter])
def test_start_after_the_story_goes_to_level_select(press):
    menu = _menu(seen_intro=True)
    press(menu)
    assert isinstance(menu.manager.scene, LevelSelectScene)


def test_the_intro_counts_as_seen_and_is_saved_as_soon_as_it_starts():
    menu = _menu(seen_intro=False)
    _click(menu, menu.start_button)
    story = menu.manager.scene
    assert isinstance(story, StoryScene) and story.index == 0      # not played through
    assert menu.session.seen_intro is True
    saved = LocalProfileManager().load()
    assert saved is not None and saved.stats[SEEN_INTRO_KEY] is True


def test_the_cloud_profile_is_saved_too_when_signed_in():
    sent = []
    account = SimpleNamespace(
        is_authenticated=lambda: True, current_user=SimpleNamespace(id="u1"), is_busy=False,
        save_profile_async=lambda profile, on_success=None, on_error=None: sent.append(profile))
    menu = _menu(seen_intro=False, account=account)
    _click(menu, menu.start_button)
    assert sent and sent[-1].stats[SEEN_INTRO_KEY] is True


def test_skipping_the_first_story_ends_at_level_select_and_start_skips_it_next_time():
    menu = _menu(seen_intro=False)
    manager = menu.manager
    _click(menu, menu.start_button)
    _escape(manager.scene)
    assert isinstance(manager.scene, LevelSelectScene)
    again = MenuScene(manager)
    manager.switch(again)
    _enter(again)
    assert isinstance(manager.scene, LevelSelectScene)


# --- the Tutorial button on level select -------------------------------------------

def _level_select(seen_intro=True):
    manager = _manager()
    manager.session.seen_intro = seen_intro
    scene = LevelSelectScene(manager)
    manager.switch(scene)
    return scene


def test_tutorial_button_plays_the_story_and_returns_to_level_select():
    scene = _level_select()
    assert scene.tutorial_button.label == levels_module.TUTORIAL_LABEL == "Tutorial"
    _click(scene, scene.tutorial_button)
    story = scene.manager.scene
    assert isinstance(story, StoryScene)
    for _ in range(len(story.panels)):          # play it through
        story.update(1.0)
        story.update(1.0)
        story.next()
    assert isinstance(story.manager.scene, LevelSelectScene)


def test_tutorial_button_sits_with_shop_and_level_editor_without_overlap():
    scene = _level_select()
    top = [scene.tutorial_button.rect, scene.editor_button.rect, scene.shop_button.rect]
    assert len({r.y for r in top}) == 1                     # one row
    for i, a in enumerate(top):
        for b in top[i + 1:]:
            assert not a.colliderect(b)
    assert scene.tutorial_button.rect.right < scene.editor_button.rect.left


def test_tutorial_button_highlights_on_hover():
    scene = _level_select()
    scene.handle_event(pygame.event.Event(pygame.MOUSEMOTION, pos=scene.tutorial_button.rect.center,
                                          rel=(0, 0), buttons=(0, 0, 0)))
    assert scene.tutorial_button.hover


# --- saving seen_intro ----------------------------------------------------------------

def _session(seen_intro=False):
    session = Session()
    session.seen_intro = seen_intro
    return session


def test_seen_intro_rides_in_the_profile_stats():
    profile = session_to_profile(_session(True), "u1")
    assert profile.stats[SEEN_INTRO_KEY] is True
    assert session_to_profile(_session(False), "u1").stats[SEEN_INTRO_KEY] is False


def test_seen_intro_survives_a_guest_save_and_load():
    save_guest_profile(_session(True))
    loaded = _session(False)
    assert load_guest_profile_into_session(loaded) is True
    assert loaded.seen_intro is True
    assert SEEN_INTRO_KEY not in loaded.stats                # kept apart from win/fail stats


def test_seen_intro_survives_a_cloud_profile_round_trip():
    # Through JSON, the way the cloud row is stored and read back.
    row = json.loads(json.dumps(session_to_profile(_session(True), "u1").to_row()))
    loaded = _session(False)
    apply_profile_to_session(loaded, PlayerProfile.from_row(row, "u1"), "u1")
    assert loaded.seen_intro is True


def test_an_old_save_without_seen_intro_reads_as_not_seen():
    old = PlayerProfile(user_id="guest", money=3, stats={"reason": "TIME UP"})
    session = _session(False)
    apply_guest_profile_to_session(session, old)
    assert session.seen_intro is False
    cloud = _session(False)
    apply_profile_to_session(cloud, PlayerProfile(user_id="u1", stats={}), "u1")
    assert cloud.seen_intro is False


@pytest.mark.parametrize("before, saved, after", [
    (False, False, False), (True, False, True), (False, True, True), (True, True, True),
])
def test_applying_a_save_keeps_seen_intro_if_either_side_saw_it(before, saved, after):
    profile = PlayerProfile(user_id="u1", stats={SEEN_INTRO_KEY: saved})
    cloud = _session(before)
    apply_profile_to_session(cloud, profile, "u1")          # signing in
    assert cloud.seen_intro is after
    guest = _session(before)
    apply_guest_profile_to_session(guest, profile)          # loading the guest save
    assert guest.seen_intro is after


def test_seen_intro_alone_never_makes_local_and_cloud_data_differ():
    # Merged by "either side", so signing in never asks which copy to keep over it.
    local = session_to_profile(_session(True), "guest")
    cloud = PlayerProfile(user_id="u1", stats={k: v for k, v in local.stats.items()
                                               if k != SEEN_INTRO_KEY})
    assert profiles_equal(local, cloud)
    cloud.stats[SEEN_INTRO_KEY] = False
    assert profiles_equal(local, cloud)
    cloud.stats["reason"] = "TIME UP"                       # real progress still counts
    assert not profiles_equal(local, cloud)


def test_deleting_local_data_forgets_the_intro():
    session = _session(True)
    reset_session_to_guest(session)
    assert session.seen_intro is False
    session = _session(True)
    save_guest_profile(session)
    clear_guest_profile(session)
    assert session.seen_intro is False
