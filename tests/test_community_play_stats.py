"""Tests for the community statistics recorded while playing a level.

A play is counted when a community level is launched, a clear when the ship
reaches the target.  Only community levels are counted.
"""

from types import SimpleNamespace

import pytest

from vector_drift import data
from vector_drift.account import community as community_module
from vector_drift.scenes.base import SceneManager

pytestmark = pytest.mark.usefixtures("pygame_display")


def _manager():
    audio = SimpleNamespace(play=lambda *a, **k: None, toggle_mute=lambda: None,
                             start_loop=lambda *a, **k: None, stop_loop=lambda *a, **k: None)
    return SceneManager(audio)


@pytest.fixture
def recorded(monkeypatch):
    """Collect the statistics the game records."""
    calls = []

    def play(level_id, on_success=None, on_error=None):
        calls.append(("play", level_id))

    def clear(level_id, player_key=None, on_success=None, on_error=None):
        calls.append(("clear", level_id, player_key))

    monkeypatch.setattr(community_module, "record_community_play", play)
    monkeypatch.setattr(community_module, "record_community_clear", clear)
    return calls


def _community_level(name="Community Level"):
    """Register a community level and return its local id."""
    level_id = data.community_level_id("row-for-stats")
    spec = data.LevelSpec(id=level_id, name=name, start=(-7.0, 0.0),
                           target_center=(7.0, 0.0), target_radius=1.0, ship_id="ship01")
    data.register_custom_level(spec)
    return level_id


def test_launching_a_community_level_counts_a_play(monkeypatch, recorded):
    from vector_drift.scenes.game import GameScene

    level_id = _community_level()
    mgr = _manager()
    mgr.session.level_id = level_id
    mgr.session.custom_level_ids.add(level_id)
    mgr.session.fx_text = "0"
    mgr.session.fy_text = "0"
    scene = GameScene(mgr)
    scene._try_launch()
    assert ("play", "row-for-stats") in recorded


def test_a_fixed_level_is_not_counted(monkeypatch, recorded):
    from vector_drift.scenes.game import GameScene

    mgr = _manager()
    mgr.session.level_id = 1
    mgr.session.fx_text = "0"
    mgr.session.fy_text = "0"
    scene = GameScene(mgr)
    scene._try_launch()
    assert recorded == []


def test_clearing_a_community_level_counts_a_clear(monkeypatch, recorded):
    from vector_drift.scenes.game import GameScene
    from vector_drift.physics import Outcome

    level_id = _community_level()
    mgr = _manager()
    mgr.session.level_id = level_id
    mgr.session.custom_level_ids.add(level_id)
    mgr.session.fx_text = "0"
    mgr.session.fy_text = "0"
    scene = GameScene(mgr)
    scene._try_launch()
    scene.flight.outcome = Outcome.REACHED
    scene._end_flight(Outcome.REACHED)
    clears = [call for call in recorded if call[0] == "clear"]
    assert clears
    assert clears[0][1] == "row-for-stats"
    assert clears[0][2]           # the player key is filled in


def test_the_statistics_never_break_the_flight(monkeypatch):
    from vector_drift.scenes.game import GameScene

    def boom(*_args, **_kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr(community_module, "record_community_play", boom)
    monkeypatch.setattr(community_module, "record_community_clear", boom)

    level_id = _community_level()
    mgr = _manager()
    mgr.session.level_id = level_id
    mgr.session.custom_level_ids.add(level_id)
    mgr.session.fx_text = "0"
    mgr.session.fy_text = "0"
    scene = GameScene(mgr)
    scene._try_launch()          # must not raise
    assert scene.flight is not None
