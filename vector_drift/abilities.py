"""Active abilities: one registry for the shop, the hotkeys and the HUD hints."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import pygame


@dataclass(frozen=True)
class Ability:
    id: str
    name: str
    key: str
    key_code: int
    description: str
    price: int
    consumable: bool = True
    sound: str = "click"
    activate: Callable[[object], bool] | None = None


ABILITIES: dict[str, Ability] = {}


def register_ability(ability: Ability) -> Ability:
    ABILITIES[ability.id] = ability
    return ability


def unregister_ability(ability_id: str) -> None:
    ABILITIES.pop(ability_id, None)


def get_ability(ability_id: str) -> Ability | None:
    return ABILITIES.get(ability_id)


def all_abilities() -> list[Ability]:
    return list(ABILITIES.values())


def ability_for_key_code(code) -> Ability | None:
    for ability in ABILITIES.values():
        if ability.key_code == code:
            return ability
    return None


def charge_count(session, ability_id: str) -> int:
    ability = ABILITIES.get(ability_id)
    if ability is None:
        return 0
    if not ability.consumable:
        return 1 if ability_id in getattr(session, "purchased_items", set()) else 0
    charges = getattr(session, "ability_charges", {}) or {}
    if not isinstance(charges, dict):
        return 0
    try:
        return max(0, int(charges.get(ability_id, 0)))
    except (TypeError, ValueError):
        return 0


def owned_ability_ids(session) -> list[str]:
    return [aid for aid in ABILITIES if charge_count(session, aid) > 0]


def consume_ability(session, ability_id: str) -> bool:
    ability = ABILITIES.get(ability_id)
    if ability is None or not ability.consumable:
        return False
    charges = getattr(session, "ability_charges", None)
    if not isinstance(charges, dict):
        return False
    try:
        left = int(charges.get(ability_id, 0))
    except (TypeError, ValueError):
        return False
    if left <= 0:
        return False
    charges[ability_id] = left - 1
    try:
        session.ability_charges = charges
    except Exception:
        pass
    return True


def use_ability(session, ability_id: str, flight) -> bool:
    ability = ABILITIES.get(ability_id)
    if ability is None or ability.activate is None:
        return False
    if charge_count(session, ability_id) <= 0:
        return False
    if not ability.activate(flight):
        return False
    if not ability.consumable:
        return True
    return consume_ability(session, ability_id)


def _activate_boost(flight):
    return flight.boost()


def _activate_shield_pulse(flight):
    return flight.shield_pulse()


def _activate_magnet(flight):
    return flight.magnet_pulse()


def _activate_time_freeze(flight):
    return flight.time_freeze()


def _activate_phase(flight):
    return flight.phase_shift()


def _activate_brake(flight):
    return flight.retro_burn()


def _activate_blink(flight):
    return flight.blink()


register_ability(Ability(
    id="ability_boost", name="Boost", key="B", key_code=pygame.K_b,
    description="Instant speed burst along your heading (B).",
    price=3, sound="launch", activate=_activate_boost,
))

register_ability(Ability(
    id="ability_shield_pulse", name="Shield Pulse", key="V", key_code=pygame.K_v,
    description="Instant 3 s shield (V): the next bumper is passed.",
    price=5, sound="shield", activate=_activate_shield_pulse,
))

register_ability(Ability(
    id="ability_magnet", name="Magnet", key="M", key_code=pygame.K_m,
    description="Pull toward the target for 3 s during a flight (M).",
    price=8, sound="unbound", activate=_activate_magnet,
))

register_ability(Ability(
    id="ability_time_freeze", name="Time Freeze", key="T", key_code=pygame.K_t,
    description="Pause the flight clock for 3 s (T).",
    price=6, sound="extratime", activate=_activate_time_freeze,
))

register_ability(Ability(
    id="ability_phase", name="Phase Shift", key="G", key_code=pygame.K_g,
    description="Pass through obstacles for 2.5 s (G).",
    price=7, sound="warp", activate=_activate_phase,
))

register_ability(Ability(
    id="ability_brake", name="Retro Burn", key="X", key_code=pygame.K_x,
    description="Instantly cut speed to 40% (X).",
    price=4, sound="bounce", activate=_activate_brake,
))

register_ability(Ability(
    id="ability_blink", name="Blink", key="Q", key_code=pygame.K_q,
    description="Teleport 2.5 m along your heading (Q).",
    price=9, sound="warp", activate=_activate_blink,
))
