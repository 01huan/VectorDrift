"""Active abilities: the registry, ownership rules, physics effects and HUD hints."""

import math
from types import SimpleNamespace

import pygame
import pytest

from vector_drift import config, sprites
from vector_drift.abilities import (
    all_abilities,
    ability_for_key_code,
    charge_count,
    consume_ability,
    get_ability,
    owned_ability_ids,
    use_ability,
)
from vector_drift.data import SHIPS, LevelSpec, ObstacleSpec, get_level
from vector_drift.physics import Flight, ForceField, Outcome

LEVEL = get_level(1)
SHIP = SHIPS[LEVEL.ship_id]


class FakeSession:
    def __init__(self, charges=None, purchased=None, money=0):
        self.ability_charges = dict(charges or {})
        self.purchased_items = set(purchased or set())
        self.money = money


def make_flight(level=None, field=None):
    return Flight(field or ForceField(), SHIP, level or LEVEL)


def bump_level(**kwargs):
    args = dict(
        id=991, name="Ability test", start=(-5.0, 0.0), target_center=(5.0, 0.0),
        target_radius=0.5, ship_id=SHIP.id,
        obstacles=(ObstacleSpec(center=(0.0, 0.0), radius=1.0),),
    )
    args.update(kwargs)
    return LevelSpec(**args)


def fly_until_done(flight):
    while flight.running:
        flight.step()
    return flight


def test_registry_has_unique_ids_and_keys():
    ids = [a.id for a in all_abilities()]
    keys = [a.key_code for a in all_abilities()]
    assert len(ids) == len(set(ids))
    assert len(keys) == len(set(keys))
    assert get_ability("ability_boost") is not None
    assert ability_for_key_code(pygame.K_b).id == "ability_boost"
    assert ability_for_key_code(pygame.K_F1) is None


def test_charge_count_only_counts_uses_left():
    session = FakeSession(charges={"ability_boost": 2})
    assert charge_count(session, "ability_boost") == 2
    assert charge_count(session, "ability_magnet") == 0
    assert owned_ability_ids(session) == ["ability_boost"]


def test_consumable_purchase_alone_does_not_grant_ownership():
    session = FakeSession(charges={"ability_boost": 1}, purchased={"ability_boost"})
    assert charge_count(session, "ability_boost") == 1
    assert consume_ability(session, "ability_boost") is True
    assert charge_count(session, "ability_boost") == 0
    assert owned_ability_ids(session) == []


def test_permanent_unlock_is_owned_without_charges():
    from vector_drift.abilities import Ability, register_ability, unregister_ability

    aid = "__test_permanent__"
    register_ability(Ability(
        id=aid, name="Test Permanent", key="P", key_code=pygame.K_p,
        description="permanent test ability", price=1, consumable=False,
        activate=lambda flight: True,
    ))
    try:
        session = FakeSession(purchased={aid})
        assert charge_count(session, aid) == 1
        assert owned_ability_ids(session) == [aid]
        assert consume_ability(session, aid) is False   # never spent
    finally:
        unregister_ability(aid)


def test_use_ability_spends_a_charge_only_when_it_fires():
    session = FakeSession(charges={"ability_boost": 1})
    flight = make_flight()
    flight.set_ability_charges(session.ability_charges)
    assert use_ability(session, "ability_boost", flight) is True
    assert charge_count(session, "ability_boost") == 0
    assert use_ability(session, "ability_boost", flight) is False


def test_set_ability_charges_maps_ids_to_counters():
    flight = make_flight()
    flight.set_ability_charges({"ability_boost": 2, "ability_blink": 3, "junk": 9})
    assert flight.boost_charges == 2
    assert flight.blink_charges == 3
    assert flight.phase_charges == 0
    assert flight.magnet_charges == 0


def test_boost_uses_a_charge_and_adds_speed():
    flight = make_flight()
    flight.set_ability_charges({"ability_boost": 1})
    flight.vx, flight.vy = 2.0, 0.0
    speed = math.hypot(flight.vx, flight.vy)
    assert flight.boost() is True
    assert math.hypot(flight.vx, flight.vy) > speed
    assert flight.boost_charges == 0
    assert flight.boost() is False


def test_shield_pulse_uses_a_charge():
    flight = make_flight()
    flight.set_ability_charges({"ability_shield_pulse": 1})
    assert flight.shield_pulse() is True
    assert flight.shield_remaining == pytest.approx(3.0)
    assert flight.shield_pulse() is False


def test_magnet_pulse_uses_a_charge():
    flight = make_flight()
    flight.set_ability_charges({"ability_magnet": 1})
    assert flight.magnet_pulse() is True
    assert flight.magnet_remaining == pytest.approx(3.0)
    assert flight.magnet_pulse() is False


def test_time_freeze_holds_the_clock():
    flight = make_flight()
    flight.set_ability_charges({"ability_time_freeze": 1})
    assert flight.time_freeze() is True
    for _ in range(60):
        flight.step()
    assert flight.time == 0.0
    assert flight.time_freeze_remaining > 0.0
    assert flight.running


def test_time_freeze_expires_and_the_clock_resumes():
    flight = make_flight()
    flight.set_ability_charges({"ability_time_freeze": 1})
    assert flight.time_freeze(duration=0.2) is True
    for _ in range(30):
        flight.step()
    assert flight.time > 0.0


def test_phase_shift_passes_through_obstacles():
    field = ForceField.from_exprs(lambda x, y: 2.0, lambda x, y: 0.0)
    flight = make_flight(bump_level(), field)
    flight.set_ability_charges({"ability_phase": 1})
    assert flight.phase_shift() is True
    fly_until_done(flight)
    assert flight.outcome is Outcome.REACHED
    assert flight.bounces == 0


def test_bumper_bounces_without_phase_shift():
    field = ForceField.from_exprs(lambda x, y: 2.0, lambda x, y: 0.0)
    flight = fly_until_done(make_flight(bump_level(), field))
    assert flight.bounces > 0
    assert flight.outcome is Outcome.TIMEOUT


def test_retro_burn_cuts_speed():
    flight = make_flight()
    flight.set_ability_charges({"ability_brake": 1})
    flight.vx, flight.vy = 10.0, 0.0
    assert flight.retro_burn() is True
    assert flight.vx == pytest.approx(4.0)
    assert flight.vy == pytest.approx(0.0)
    assert flight.retro_burn() is False


def test_blink_teleports_along_the_heading_and_breaks_the_trail():
    flight = make_flight()
    flight.set_ability_charges({"ability_blink": 1})
    flight.vx, flight.vy = 3.0, 0.0
    before = (flight.x, flight.y)
    trail_before = len(flight.trail)
    assert flight.blink() is True
    assert flight.x == pytest.approx(before[0] + 2.5)
    assert flight.y == pytest.approx(before[1])
    assert len(flight.trail) == trail_before + 2
    assert len(flight.trail_breaks) == 1
    assert flight.blink() is False


def test_blink_at_rest_heads_for_the_target():
    level = LevelSpec(id=992, name="Blink rest", start=(0.0, 0.0),
                      target_center=(4.0, 0.0), target_radius=0.5, ship_id=SHIP.id)
    flight = make_flight(level)
    flight.set_ability_charges({"ability_blink": 1})
    assert flight.blink() is True
    assert flight.x == pytest.approx(2.5)
    assert flight.y == pytest.approx(0.0)
    assert flight.outcome is Outcome.RUNNING


def test_blink_off_the_map_ends_the_flight():
    flight = make_flight()
    flight.set_ability_charges({"ability_blink": 1})
    flight.x = 9.0
    flight.vx, flight.vy = 5.0, 0.0
    assert flight.blink(distance=2.5) is True
    assert flight.x == pytest.approx(11.5)
    assert flight.outcome is Outcome.OUT_OF_BOUNDS


def test_shop_registers_every_ability():
    from vector_drift import shop as shop_module

    for ability in all_abilities():
        item = shop_module.get_item(ability.id)
        assert item is not None
        assert item.category == "ability"
        assert item.price == ability.price


def test_shop_purchase_grants_an_ability_charge():
    from vector_drift import shop as shop_module

    session = FakeSession(money=100)
    item = shop_module.get_item("ability_blink")
    assert shop_module.purchase_item(item, session) is True
    assert charge_count(session, "ability_blink") == 1


def test_use_ability_key_spends_the_charge():
    from vector_drift.scenes.game_flight import GameFlightMixin

    session = FakeSession(charges={"ability_boost": 1})
    scene = SimpleNamespace(
        session=session,
        flight=SimpleNamespace(boost=lambda: True),
        audio=SimpleNamespace(play=lambda *a, **k: None),
        _save_progress=lambda: None,
    )
    assert GameFlightMixin._use_ability_key(scene, pygame.K_b) is True
    assert charge_count(session, "ability_boost") == 0
    assert GameFlightMixin._use_ability_key(scene, pygame.K_b) is False
    assert GameFlightMixin._use_ability_key(scene, pygame.K_F1) is False


@pytest.mark.usefixtures("pygame_display")
def test_hud_only_shows_owned_abilities(monkeypatch):
    from vector_drift.scenes import game as game_module
    from vector_drift.scenes.base import SceneManager
    from vector_drift.scenes.game import GameScene

    manager = SceneManager(SimpleNamespace(
        play=lambda *a, **k: None,
        start_loop=lambda *a, **k: None,
        stop_loop=lambda *a, **k: None,
    ))
    manager.session.level_id = 1
    manager.session.fx_text = "0"
    manager.session.fy_text = "0"
    manager.session.purchased_items = {"ability_boost"}
    manager.session.ability_charges = {"ability_boost": 0, "ability_blink": 2}
    scene = GameScene(manager)
    manager.switch(scene)

    calls = []
    real = game_module.draw_text

    def spy(surface, text, *args, **kwargs):
        calls.append(text)
        return real(surface, text, *args, **kwargs)

    monkeypatch.setattr(game_module, "draw_text", spy)
    scene.draw(pygame.Surface((config.WINDOW_W, config.WINDOW_H)))

    prefixes = ("Boost (", "Shield Pulse (", "Magnet (", "Time Freeze (",
                "Phase Shift (", "Retro Burn (", "Blink (")
    labels = [c for c in calls if isinstance(c, str) and c.startswith(prefixes)]
    assert "Blink (Q) x2" in labels
    assert "Boost (B)" not in labels
    assert "Magnet (M)" not in labels


@pytest.mark.usefixtures("pygame_display")
def test_inventory_popup_lists_only_owned_abilities(monkeypatch):
    from vector_drift.scenes import game as game_module
    from vector_drift.scenes.base import SceneManager
    from vector_drift.scenes.game import GameScene

    manager = SceneManager(SimpleNamespace(
        play=lambda *a, **k: None,
        start_loop=lambda *a, **k: None,
        stop_loop=lambda *a, **k: None,
    ))
    manager.session.level_id = 1
    manager.session.fx_text = "0"
    manager.session.fy_text = "0"
    manager.session.purchased_items = {"ability_boost"}
    manager.session.ability_charges = {"ability_boost": 0, "ability_blink": 1}
    scene = GameScene(manager)
    manager.switch(scene)
    scene.inventory_open = True

    calls = []
    real = game_module.draw_text

    def spy(surface, text, *args, **kwargs):
        calls.append(text)
        return real(surface, text, *args, **kwargs)

    monkeypatch.setattr(game_module, "draw_text", spy)
    scene.draw(pygame.Surface((config.WINDOW_W, config.WINDOW_H)))

    assert "Blink (Q)" in calls
    assert "Boost (B)" not in calls


@pytest.mark.usefixtures("pygame_display")
def test_draw_phase_is_safe():
    surface = pygame.Surface((200, 200))
    sprites.draw_phase(surface, (100, 100), 20, 0.0)
    sprites.draw_phase(surface, (100, 100), 20, 1.5)
    sprites.draw_phase(surface, (float("nan"), 0.0), 20, 0.0)
    sprites.draw_phase(surface, (100, 100), 0, 0.0)
