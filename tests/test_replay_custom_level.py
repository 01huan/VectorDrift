from types import SimpleNamespace

import pytest

from vector_drift import data
from vector_drift.data import LevelSpec, ObstacleSpec, PickupSpec
from vector_drift.physics import Outcome
from vector_drift.replay import ReplayRecord
from vector_drift.scenes.base import SceneManager
from vector_drift.scenes.game import GameScene
from vector_drift.scenes.replay import ReplayScene


pytestmark = pytest.mark.usefixtures("pygame_display")


def _audio():
    return SimpleNamespace(
        play=lambda *args, **kwargs: None,
        start_loop=lambda *args, **kwargs: None,
        stop_loop=lambda *args, **kwargs: None,
        toggle_mute=lambda: None,
    )


def _custom_level(level_id=98765, name="Snapshot"):
    return LevelSpec(
        id=level_id,
        name=name,
        start=(-6.0, 1.0),
        target_center=(6.0, -1.0),
        target_radius=1.5,
        ship_id="ship01",
        time_limit=17.0,
        lives=3,
        obstacles=(ObstacleSpec(center=(0.0, 2.0), radius=0.8),),
        pickups=(PickupSpec(center=(1.0, -2.0), radius=0.6, kind="shield"),),
    )


def test_custom_level_launch_captures_replay_snapshot(monkeypatch):
    monkeypatch.setattr(data, "LEVELS", list(data.LEVELS))
    monkeypatch.setattr(data, "CUSTOM_LEVELS", dict(data.CUSTOM_LEVELS))
    level = _custom_level()
    data.register_custom_level(level)

    manager = SceneManager(_audio())
    manager.session.level_id = level.id
    manager.session.custom_level_ids.add(level.id)
    scene = GameScene(manager)
    scene._try_launch()
    scene._end_flight(Outcome.TIMEOUT)

    snapshot = data.custom_level_to_snapshot(level)
    assert manager.session.replays[0]["level_snapshot"] == snapshot
    assert ReplayRecord.from_dict(manager.session.replays[0]).to_dict()["level_snapshot"] == snapshot


@pytest.mark.parametrize("registry_state", ["modified", "deleted"])
def test_replay_uses_saved_level_snapshot_not_current_registry(monkeypatch, registry_state):
    monkeypatch.setattr(data, "LEVELS", list(data.LEVELS))
    monkeypatch.setattr(data, "CUSTOM_LEVELS", dict(data.CUSTOM_LEVELS))
    original = _custom_level()
    data.register_custom_level(original)
    snapshot = data.custom_level_to_snapshot(original)
    if registry_state == "modified":
        data.register_custom_level(_custom_level(name="Edited later"))
    else:
        data.CUSTOM_LEVELS.pop(original.id)
        data.LEVELS[:] = [level for level in data.LEVELS if level.id != original.id]

    record = ReplayRecord(level_id=original.id, level_snapshot=snapshot).to_dict()
    manager = SceneManager(_audio())
    manager.session.replays = [record]
    scene = ReplayScene(manager)

    assert scene._level.name == original.name
    assert scene._level.start == original.start
    assert scene._level.target_center == original.target_center
    assert scene._level.obstacles == original.obstacles
    assert scene._level.pickups == original.pickups
