"""Playing a community level must not turn it into one of the player's own.

A community level belongs to the player who uploaded it: playing it only
plays it.  It must not show up in the level editor list, it must not be
written to the profile, and it must keep the custom-level rules (no money
pickup payout, no clear reward, AI solver instead of authored hints).
"""

from types import SimpleNamespace

import pytest

from vector_drift import data
from vector_drift.account import community as community_module
from vector_drift.account.integration import session_to_profile
from vector_drift.data import LevelSpec, PickupSpec
from vector_drift.physics import Outcome
from vector_drift.scenes.base import SceneManager, back_scene_for_level
from vector_drift.scenes.community_levels import CommunityLevelsScene
from vector_drift.scenes.game import GameScene
from vector_drift.scenes.level_editor_menu import LevelEditorMenuScene

pytestmark = pytest.mark.usefixtures("pygame_display")


@pytest.fixture(autouse=True)
def _clean_registries():
    data.CUSTOM_LEVELS.clear()
    data.COMMUNITY_LEVELS.clear()
    yield
    data.CUSTOM_LEVELS.clear()
    data.COMMUNITY_LEVELS.clear()


@pytest.fixture(autouse=True)
def no_solver(monkeypatch):
    import vector_drift.scenes.game as game_module

    monkeypatch.setattr(game_module, "run_solver_async", lambda *a, **k: SimpleNamespace(
        running=True, cancel=lambda: None, stop=lambda *a: True, error=None, result=None))


def _audio():
    return SimpleNamespace(play=lambda *a, **k: None, start_loop=lambda *a, **k: None,
                            stop_loop=lambda *a, **k: None, toggle_mute=lambda: None)


def _manager(account=None):
    return SceneManager(_audio(), account_manager=account)


def _row(row_id="row-1", name="Community"):
    return {"id": row_id, "level_data": {"name": name, "start": [-7.0, 0.0],
                                         "target_center": [7.0, 0.0], "target_radius": 1.0}}


def _open_card(monkeypatch, mgr, row):
    """Open a community level card the way the player does."""
    def fetch(on_success=None, on_error=None):
        if on_success:
            on_success([row])

    monkeypatch.setattr(community_module, "fetch_community_levels", fetch)
    import vector_drift.scenes.game as game_module

    class FakeGame:
        music = None

        def __init__(self, manager):
            self.manager = manager

    monkeypatch.setattr(game_module, "GameScene", FakeGame)
    scene = CommunityLevelsScene(mgr)
    scene.busy = False
    scene.levels = [row]
    scene._rebuild()
    scene._open(row)
    return scene


def _community_spec(level_id, name="Community", pickups=()):
    return LevelSpec(id=level_id, name=name, start=(-7.0, 0.0), target_center=(7.0, 0.0),
                     target_radius=1.0, ship_id="ship01", pickups=tuple(pickups))


# --------------------------------------------------------------- the bug itself

def test_playing_a_community_level_does_not_add_it_to_the_custom_levels(monkeypatch):
    mgr = _manager()
    row = _row()
    _open_card(monkeypatch, mgr, row)

    level_id = mgr.session.level_id
    assert level_id < 0                       # a community level has its own id space
    assert mgr.session.custom_levels == []
    assert mgr.session.custom_level_ids == set()
    assert level_id not in data.CUSTOM_LEVELS
    # It is registered as a community level, so the game can still load it.
    assert data.is_community_level(level_id)
    assert data.get_level(level_id).id == level_id


def test_the_player_keeps_their_own_custom_levels(monkeypatch):
    mgr = _manager()
    mine = _community_spec(1001, name="Mine")
    data.register_custom_level(mine)
    mgr.session.custom_levels = [mine]
    mgr.session.custom_level_ids = {mine.id}

    _open_card(monkeypatch, mgr, _row())

    assert [lv.id for lv in mgr.session.custom_levels] == [mine.id]
    assert mgr.session.custom_level_ids == {mine.id}


def test_a_community_level_is_not_written_to_the_profile(monkeypatch):
    mgr = _manager()
    _open_card(monkeypatch, mgr, _row())

    profile = session_to_profile(mgr.session, "guest")
    assert profile.stats["custom_levels"] == []


def test_a_community_level_is_not_listed_in_the_level_editor(monkeypatch):
    mgr = _manager()
    _open_card(monkeypatch, mgr, _row())

    menu = LevelEditorMenuScene(mgr)
    assert menu.cards == []
    assert mgr.session.custom_levels == []


def test_a_legacy_profile_with_a_community_level_drops_it():
    """An older version saved the played community levels with the profile."""
    from vector_drift.account.integration import _restore_custom_levels
    from vector_drift.scenes.base import Session

    community_id = data.community_level_id("legacy-row")
    spec = _community_spec(community_id)
    session = Session()
    _restore_custom_levels(session, [spec.to_row()])

    assert session.custom_levels == []
    assert session.custom_level_ids == set()
    assert community_id not in data.CUSTOM_LEVELS


# ------------------------------------------------------- the level stays playable

def test_a_community_level_can_be_played(monkeypatch):
    mgr = _manager()
    row = _row()
    _open_card(monkeypatch, mgr, row)

    mgr.session.fx_text = "0"
    mgr.session.fy_text = "0"
    scene = GameScene(mgr)
    assert scene.level.id == mgr.session.level_id
    # A community level is a custom map: it uses the AI solver, not the hints.
    assert scene.hint_mode is False
    scene._try_launch()
    assert scene.flight is not None


def test_leaving_a_community_level_returns_to_the_browser(monkeypatch):
    mgr = _manager()
    _open_card(monkeypatch, mgr, _row())
    assert back_scene_for_level(mgr.session) is CommunityLevelsScene


def test_a_replay_of_a_community_level_keeps_the_level(monkeypatch):
    """The replay needs the level itself: it is saved with the launch."""
    mgr = _manager()
    level_id = data.community_level_id("replay-row")
    data.register_community_level(_community_spec(level_id))
    mgr.session.level_id = level_id
    mgr.session.fx_text = "0"
    mgr.session.fy_text = "0"

    scene = GameScene(mgr)
    scene._try_launch()
    scene._end_flight(Outcome.TIMEOUT)

    record = mgr.session.replays[0]
    assert record["level_snapshot"] is not None
    assert record["level_snapshot"]["id"] == level_id


# --------------------------------------------- the custom-level rules still apply

def test_the_money_pickups_of_a_community_level_do_not_pay(monkeypatch):
    mgr = _manager()
    level_id = data.community_level_id("coin-row")
    data.register_community_level(_community_spec(
        level_id, pickups=(PickupSpec(center=(1.0, 0.0), radius=0.4, kind="money"),)))
    mgr.session.level_id = level_id
    mgr.session.fx_text = "0"
    mgr.session.fy_text = "0"

    scene = GameScene(mgr)
    pickup = [p for p in scene.pickups if p.kind == "money"][0]
    pickup.consumed = True
    scene.flight = SimpleNamespace(pickup_events=[
        {"kind": "money", "center": pickup.center, "amount": 1}])
    scene._drain_pickup_events()

    assert int(mgr.session.money) == 0


def test_a_community_level_gets_no_clear_reward():
    mgr = _manager()
    level_id = data.community_level_id("reward-row")
    data.register_community_level(_community_spec(level_id))
    mgr.session.level_id = level_id
    mgr.session.fx_text = "0"
    mgr.session.fy_text = "0"

    scene = GameScene(mgr)
    scene._pay_clear_reward()
    assert int(mgr.session.money) == 0
    assert scene._clear_reward == 0
