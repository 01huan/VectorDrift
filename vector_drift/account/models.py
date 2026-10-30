"""Data models for the account subsystem."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Set


@dataclass
class AccountUser:
    id: str
    email: Optional[str] = None
    email_confirmed: bool = False
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None


@dataclass
class PlayerProfile:
    user_id: str
    display_name: Optional[str] = None
    money: int = 0
    owned_ships: Set[str] = field(default_factory=lambda: {"ship01"})
    purchased_items: Set[str] = field(default_factory=set)
    records: Dict[int, float] = field(default_factory=dict)
    collected_money_pickups: Set[tuple[int, tuple[float, float]]] = field(default_factory=set)
    stats: Dict[str, Any] = field(default_factory=dict)
    updated_at: Optional[str] = None

    def to_row(self) -> dict:
        return {
            "id": self.user_id,
            "display_name": self.display_name,
            "money": int(self.money),
            "owned_ships": sorted(self.owned_ships),
            "purchased_items": sorted(self.purchased_items),
            "records": {str(k): float(v) for k, v in self.records.items()},
            "collected_money_pickups": [
                [int(lid), [float(c[0]), float(c[1])]] for (lid, c) in self.collected_money_pickups
            ],
            "stats": self.stats,
            "updated_at": self.updated_at,
        }

    @staticmethod
    def from_row(row: dict, user_id: str) -> "PlayerProfile":
        records_raw = row.get("records") or {}
        records: Dict[int, float] = {}
        for k, v in records_raw.items():
            try:
                records[int(k)] = float(v)
            except (TypeError, ValueError):
                continue

        pickups_raw = row.get("collected_money_pickups") or []
        pickups: Set[tuple[int, tuple[float, float]]] = set()
        for item in pickups_raw:
            try:
                lid = int(item[0])
                coord = item[1]
                pickups.add((lid, (float(coord[0]), float(coord[1]))))
            except (TypeError, ValueError, IndexError, KeyError):
                continue

        owned = row.get("owned_ships")
        owned_set = set(owned) if owned else {"ship01"}

        purchased = row.get("purchased_items")
        purchased_set = set(purchased) if purchased else set()

        return PlayerProfile(
            user_id=user_id,
            display_name=row.get("display_name"),
            money=int(row.get("money") or 0),
            owned_ships=owned_set,
            purchased_items=purchased_set,
            records=records,
            collected_money_pickups=pickups,
            stats=row.get("stats") or {},
            updated_at=row.get("updated_at"),
        )
