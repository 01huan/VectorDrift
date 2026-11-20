"""Achievements give XP once per unlock key: 10/20/30/40 for tiers I-IV, 40 for a single one."""

from types import SimpleNamespace

import pytest

from vector_drift import achievements as ach
from vector_drift import config
from vector_drift.scenes.base import SceneManager

pytestmark = pytest.mark.usefixtures("pygame_display")


def _manager(tutorial=False):
    audio = SimpleNamespace(play=lambda *a, **k: None, start_loop=lambda *a, **k: None,
                            stop_loop=lambda *a, **k: None)
    manager = SceneManager(audio)
    manager.scene = SimpleNamespace(counts_for_progress=not tutorial)
    return manager


def test_a_single_achievement_gives_40():
    manager = _manager()
    assert ach.unlock(manager, "chain_reaction")
    assert manager.session.xp_total == 40
    assert manager.session.xp_achievements == {"chain_reaction"}


def test_each_tier_gives_its_own_xp():
    manager = _manager()
    ach.unlock(manager, "bounce_house.1")
    assert manager.session.xp_total == 10
    ach.unlock(manager, "bounce_house.4")
    assert manager.session.xp_total == 50
    assert manager.session.xp_achievements == {"bounce_house.1", "bounce_house.4"}


def test_unlocking_the_same_key_again_gives_nothing():
    manager = _manager()
    ach.unlock(manager, "chain_reaction")
    assert not ach.unlock(manager, "chain_reaction")
    assert manager.session.xp_total == 40


def test_a_key_that_already_paid_its_xp_gives_nothing():
    manager = _manager()
    manager.session.xp_achievements = {"chain_reaction"}
    assert ach.unlock(manager, "chain_reaction")
    assert manager.session.xp_total == 0


def test_two_tiers_at_once_give_both():
    manager = _manager()
    ach.count(manager, ach.BOUNCES, 100)                     # tiers I (25) and II (100)
    assert {"bounce_house.1", "bounce_house.2"} <= set(manager.session.achievements)
    assert manager.session.xp_total == 30


def test_an_achievement_in_the_tutorial_still_gives_xp():
    manager = _manager(tutorial=True)
    ach.unlock(manager, "is_anyone_out_there")               # watching the intro story
    assert manager.session.xp_total == 40


def test_an_achievement_can_level_up():
    manager = _manager()
    manager.session.xp_total = 90
    ach.unlock(manager, "chain_reaction")
    assert manager.session.xp_total == 130
    assert manager.session.xp_rewarded_level == 2
    assert int(manager.session.money) == config.LEVEL_UP_COINS


def test_the_xp_is_saved_with_the_unlock(monkeypatch):
    from vector_drift.account import integration
    saved = []
    monkeypatch.setattr(integration, "save_progress", lambda account, session: saved.append(
        (session.xp_total, set(session.xp_achievements), session.xp_rewarded_level)))
    manager = _manager()
    manager.session.xp_total = 90
    ach.unlock(manager, "chain_reaction")
    assert saved == [(130, {"chain_reaction"}, 2)]


def test_a_clears_xp_includes_the_achievements_it_unlocked():
    """The win screen's XP earned matches what the XP bar grows by."""
    from tests.test_progression import _scene, _win
    from vector_drift.xp import xp_for_achievement_key
    manager = _manager()
    stats = _win(_scene(1, manager))
    session = manager.session
    from_achievements = sum(xp_for_achievement_key(k) for k in session.xp_achievements)
    assert "beginners_luck.1" in session.xp_achievements     # cleared on the first launch
    assert stats["xp_gained"] == 100 + from_achievements == session.xp_total
