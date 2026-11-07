"""Replays of multi-section levels: each launch replays over the section it flew (no window)."""

from types import SimpleNamespace

import pygame
import pytest

from vector_drift import config, sprites
from vector_drift.data import SHIPS, all_levels, get_level, section_count, section_level
from vector_drift.level_presets import is_dynamic_level
from vector_drift.scenes import replay as replay_module
from vector_drift.scenes.base import SceneManager
from vector_drift.scenes.game import FLIGHT, PANNING, GameScene
from vector_drift.scenes.replay import ReplayScene

pytestmark = pytest.mark.usefixtures("pygame_display")
SEED = 1234                                     # fixed layout for the random levels


def _manager():
    audio = SimpleNamespace(play=lambda *a, **k: None, start_loop=lambda *a, **k: None,
                            stop_loop=lambda *a, **k: None, toggle_mute=lambda: None)
    manager = SceneManager(audio)
    return manager


def _record(level_id, section_index=0, seed=None, start=(-7.0, 0.0), ship_id="ship02", **extra):
    x, y = start
    rec = {"level_id": level_id, "ship_id": ship_id, "fx_text": "0", "fy_text": "0",
           "outcome": "Outcome.TIMEOUT", "seed": seed, "section_index": section_index,
           "frames": [{"t": i * 0.1, "x": x, "y": y, "vx": 0.0, "vy": 0.0, "fx": 0.0, "fy": 0.0}
                      for i in range(3)]}
    rec.update(extra)
    return rec


def _replay(*records):
    manager = _manager()
    manager.session.replays = list(records)
    scene = ReplayScene(manager)
    manager.switch(scene)
    return scene


def _surface():
    return pygame.Surface((config.WINDOW_W, config.WINDOW_H))


@pytest.fixture
def drawn(monkeypatch):
    """Which sprite painters the replay called, with their screen centers (and ship)."""
    calls = {"checkpoint": [], "target": [], "start": [], "life": []}
    # name -> (key, takes a ship as its 5th argument)
    for name, (key, has_ship) in {"draw_checkpoint": ("checkpoint", True),
                                  "draw_checkpoint_life": ("life", True),
                                  "draw_target": ("target", False),
                                  "draw_start_marker": ("start", False)}.items():
        real = getattr(sprites, name)

        def spy(surface, center, radius, t, *args, _real=real, _key=key, _has_ship=has_ship, **kwargs):
            ship = (args[0] if args else kwargs.get("ship")) if _has_ship else None
            calls[_key].append((tuple(center), ship))
            return _real(surface, center, radius, t, *args, **kwargs)
        monkeypatch.setattr(sprites, name, spy)
    return calls


# --- saving ----------------------------------------------------------------------------
def test_a_launch_in_section_two_is_saved_with_its_section():
    manager = _manager()
    manager.session.level_id = 9
    manager.session.fx_text, manager.session.fy_text = "5", "0"
    scene = GameScene(manager)
    manager.switch(scene)
    scene._try_launch()
    while scene.state == FLIGHT:
        scene.update(0.05)
    assert manager.session.replays[0]["section_index"] == 0     # the checkpoint flight
    while scene.state == PANNING:
        scene.update(0.05)
    manager.session.replays = []

    scene._try_launch()
    while scene.state == FLIGHT:
        scene.update(0.05)

    (rec,) = manager.session.replays
    assert rec["level_id"] == 9 and rec["section_index"] == 1


def test_one_screen_launches_are_saved_as_section_zero():
    manager = _manager()
    manager.session.level_id = 1
    manager.session.fx_text, manager.session.fy_text = "-5", "0"
    scene = GameScene(manager)
    manager.switch(scene)
    scene._try_launch()
    while scene.state == FLIGHT:
        scene.update(0.05)
    assert [r["section_index"] for r in manager.session.replays] == [0]


# --- replaying -------------------------------------------------------------------------
def test_a_section_two_record_replays_over_section_two():
    scene = _replay(_record(9, section_index=1))
    second = section_level(get_level(9), 1)
    assert scene._section_index == 1
    assert scene._start == second.start == (-7.0, 0.0)
    assert scene._target_center == second.target_center == (7.0, 0.0)
    assert scene._target_radius == second.target_radius


@pytest.mark.parametrize("speed", [0.1, 1.0, 2.0])
def test_playback_interpolates_between_saved_frames_at_every_speed(speed):
    record = _record(1)
    record["frames"] = [
        {"t": 0.0, "x": 0.0, "y": 0.0, "vx": 0.0, "vy": 0.0, "fx": 0.0, "fy": 0.0},
        {"t": 1.0, "x": 10.0, "y": 0.0, "vx": 10.0, "vy": 0.0, "fx": 2.0, "fy": 0.0},
    ]
    scene = _replay(record)
    scene.player.set_speed(speed)
    scene.paused = False

    scene.update(0.05 / speed)

    frame = scene._current_frame()
    assert scene.player.index == 0
    assert frame["t"] == pytest.approx(0.05)
    assert frame["x"] == pytest.approx(0.5)
    assert frame["vx"] == pytest.approx(0.5)
    assert frame["fx"] == pytest.approx(0.1)


def test_playback_does_not_interpolate_through_a_wormhole():
    record = _record(1)
    record["frames"] = [
        {"t": 0.0, "x": 0.0, "y": 0.0, "vx": 0.0, "vy": 0.0, "fx": 0.0, "fy": 0.0},
        {"t": 1.0, "x": 100.0, "y": 0.0, "vx": 0.0, "vy": 0.0, "fx": 0.0, "fy": 0.0,
         "warp": True},
    ]
    scene = _replay(record)
    scene.paused = False

    scene.update(0.5)

    assert scene._current_frame()["x"] == 0.0
    assert scene.player.index == 0


def test_section_one_aims_at_a_checkpoint(drawn):
    scene = _replay(_record(9, section_index=0))
    scene.draw(_surface())
    vp = scene._viewport
    assert drawn["checkpoint"] == [(vp.to_screen(7.0, 0.0), SHIPS["ship02"])]
    assert drawn["life"] == [(vp.to_screen(7.0, 0.0), SHIPS["ship02"])]
    assert drawn["target"] == []
    assert [c for c, _ in drawn["start"]] == [vp.to_screen(-7.0, 0.0)]


def test_section_two_starts_on_a_checkpoint_and_aims_at_the_planet(drawn):
    scene = _replay(_record(9, section_index=1))
    scene.draw(_surface())
    vp = scene._viewport
    assert drawn["checkpoint"] == [(vp.to_screen(-7.0, 0.0), SHIPS["ship02"])]   # the record's ship
    assert drawn["start"] == [] and drawn["life"] == []
    assert [c for c, _ in drawn["target"]] == [vp.to_screen(7.0, 0.0)]


def test_the_checkpoint_life_is_gone_once_the_replay_reaches_it(drawn):
    scene = _replay(_record(9, section_index=0, outcome="Outcome.REACHED"))
    scene.player.seek(2)
    scene.draw(_surface())
    assert drawn["checkpoint"] and drawn["life"] == []


@pytest.mark.parametrize("bad", [5, -1, "2", None, 1.0])
def test_a_bad_section_index_replays_section_one(bad, drawn):
    scene = _replay(_record(9, section_index=bad))
    scene.draw(_surface())
    assert scene._section_index == 0
    assert drawn["target"] == [] and drawn["checkpoint"]           # section 1: checkpoint target


def test_a_record_without_section_index_replays_section_one():
    rec = _record(9)
    del rec["section_index"]
    scene = _replay(rec)
    scene.draw(_surface())
    assert scene._section_index == 0


def test_the_level_row_names_the_section(monkeypatch):
    texts = []
    real = replay_module.draw_text
    monkeypatch.setattr(replay_module, "draw_text",
                        lambda surface, text, *a, **k: (texts.append(text), real(surface, text, *a, **k))[1])
    scene = _replay(_record(9, section_index=1), _record(1))
    scene.draw(_surface())
    assert "9 · section 2/2" in texts

    texts.clear()
    scene._load(1)
    scene.draw(_surface())
    assert "1" in texts and not any("section" in t for t in texts)


def test_prev_next_switch_between_sections():
    scene = _replay(_record(9, section_index=1), _record(9, section_index=0))
    assert scene._section_index == 1
    scene._load(1)
    assert scene._section_index == 0
    scene._load(0)
    assert scene._section_index == 1


# --- every level, every section (cases come from the level data) ---------------------
def _cases():
    cases = []
    for card in all_levels():
        seed = SEED if is_dynamic_level(card.id) else None
        level = get_level(card.id, seed=seed) if seed is not None else get_level(card.id)
        for k in range(section_count(level)):
            cases.append(pytest.param(card.id, seed, k, id=f"level{card.id}-section{k + 1}"))
    return cases


def _hole_key(hole):
    if hasattr(hole, "black_center"):
        return (tuple(hole.black_center), tuple(hole.white_center), hole.radius)
    black, white, radius = hole
    return (tuple(black), tuple(white), radius)


@pytest.mark.parametrize("level_id, seed, k", _cases())
def test_every_section_of_every_level_replays_over_the_right_screen(level_id, seed, k):
    level = get_level(level_id, seed=seed) if seed is not None else get_level(level_id)
    expected = section_level(level, k)
    scene = _replay(_record(level_id, section_index=k, seed=seed, start=expected.start))

    assert scene._section_index == k
    assert tuple(scene._start) == tuple(expected.start)
    assert tuple(scene._target_center) == tuple(expected.target_center)
    assert scene._target_radius == expected.target_radius
    assert tuple(scene._obstacles) == tuple(expected.obstacles)
    assert [(tuple(p.center), p.radius, p.kind) for p in scene._pickups] == [
        (tuple(p.center), p.radius, p.kind) for p in expected.pickups]
    assert [_hole_key(h) for h in scene._holes] == [_hole_key(h) for h in expected.holes]

    surface = _surface()
    scene.draw(surface)
    scene.player.seek(2)
    scene.draw(surface)


def test_the_case_list_covers_every_level_and_section():
    ids = {p.id for p in _cases()}
    assert "level9-section2" in ids and "level1-section1" in ids
    assert len(ids) == sum(section_count(get_level(c.id, seed=SEED) if is_dynamic_level(c.id)
                                         else get_level(c.id)) for c in all_levels())
