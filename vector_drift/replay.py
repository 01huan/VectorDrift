"""Replay storage for ship launches."""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, field
from typing import Any, List, Optional

MAX_REPLAYS = 10





@dataclass
class ReplayFrame:
    t: float = 0.0
    x: float = 0.0
    y: float = 0.0
    vx: float = 0.0
    vy: float = 0.0
    fx: float = 0.0
    fy: float = 0.0
    # The ship came out of a white hole since the previous frame: the replay
    # starts a new trail stroke here instead of joining the two holes.
    warp: bool = False

    def to_dict(self):
        data = {"t": float(self.t), "x": float(self.x), "y": float(self.y),
                "vx": float(self.vx), "vy": float(self.vy),
                "fx": float(self.fx), "fy": float(self.fy)}
        if self.warp:
            data["warp"] = True         # only when set, so ordinary frames stay as they were
        return data

    @staticmethod
    def from_dict(data):
        data = data or {}
        def _f(key, default=0.0):
            try:
                v = data.get(key, default) if isinstance(data, dict) else default
                v = float(v)
                return v if math.isfinite(v) else default
            except (TypeError, ValueError, AttributeError):
                return default
        warp = isinstance(data, dict) and data.get("warp") is True
        return ReplayFrame(t=_f("t"), x=_f("x"), y=_f("y"),
                          vx=_f("vx"), vy=_f("vy"), fx=_f("fx"), fy=_f("fy"), warp=warp)


def section_index_from(value):
    """A stored section index, or 0 when it is missing, not an int, or negative.

    Old saves have no section_index; whether the index exists in the level
    is checked where the level is known (the replay scene).
    """
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return 0
    return value


@dataclass
class ReplayRecord:
    level_id: int = 0
    ship_id: Optional[str] = None
    fx_text: str = ""
    fy_text: str = ""
    outcome: str = ""
    frames: List = field(default_factory=list)
    created_at: float = field(default_factory=lambda: time.time())
    seed: Optional[int] = None
    consumed_pickups: List = field(default_factory=list)
    obstacle_centers: List = field(default_factory=list)
    level_snapshot: Optional[dict] = None
    # Which screen of a multi-section level the launch flew (0-based, like
    # data.section_level). One-screen levels and old saves are always 0.
    section_index: int = 0

    def to_dict(self):
        data = {
            "level_id": int(self.level_id) if self.level_id is not None else 0,
            "ship_id": self.ship_id,
            "fx_text": str(self.fx_text or ""),
            "fy_text": str(self.fy_text or ""),
            "outcome": str(self.outcome or ""),
            "frames": [f.to_dict() if hasattr(f, "to_dict") else f for f in (self.frames or [])],
            "created_at": float(self.created_at),
            "seed": self.seed,
            "consumed_pickups": [list(c) if not isinstance(c, (list, tuple)) else list(c) for c in (self.consumed_pickups or [])],
            "obstacle_centers": [list(c) if not isinstance(c, (list, tuple)) else list(c) for c in (self.obstacle_centers or [])],
            "section_index": section_index_from(self.section_index),
        }
        if isinstance(self.level_snapshot, dict):
            data["level_snapshot"] = self.level_snapshot
        return data

    @staticmethod
    def from_dict(data):
        data = data or {}
        if isinstance(data, ReplayRecord):
            return data
        frames_raw = data.get("frames") if isinstance(data, dict) else None
        frames = [ReplayFrame.from_dict(f) for f in (frames_raw or [])]
        try:
            level_id = int(data.get("level_id", 0)) if isinstance(data, dict) else 0
        except (TypeError, ValueError):
            level_id = 0
        created = data.get("created_at") if isinstance(data, dict) else None
        try:
            created = float(created) if created is not None else time.time()
        except (TypeError, ValueError):
            created = time.time()
        seed = data.get("seed") if isinstance(data, dict) else None
        try:
            seed = int(seed) if seed is not None else None
        except (TypeError, ValueError):
            seed = None
        consumed = data.get("consumed_pickups") if isinstance(data, dict) else None
        obstacles = data.get("obstacle_centers") if isinstance(data, dict) else None
        return ReplayRecord(
            level_id=level_id,
            ship_id=data.get("ship_id") if isinstance(data, dict) else None,
            fx_text=data.get("fx_text", "") if isinstance(data, dict) else "",
            fy_text=data.get("fy_text", "") if isinstance(data, dict) else "",
            outcome=data.get("outcome", "") if isinstance(data, dict) else "",
            frames=frames,
            created_at=created,
            seed=seed,
            consumed_pickups=list(consumed or []),
            obstacle_centers=list(obstacles or []),
            level_snapshot=(dict(data["level_snapshot"])
                            if isinstance(data, dict) and isinstance(data.get("level_snapshot"), dict)
                            else None),
            section_index=section_index_from(data.get("section_index") if isinstance(data, dict) else None),
        )





class ReplayBuffer:
    def __init__(self, capacity=MAX_REPLAYS):
        self.capacity = max(1, int(capacity))
        self.records = []

    def add(self, record):
        r = record if isinstance(record, ReplayRecord) else ReplayRecord.from_dict(record)
        self.records.append(r)
        if len(self.records) > self.capacity:
            self.records = self.records[-self.capacity:]

    def append(self, record):
        self.add(record)

    def push(self, record):
        self.add(record)

    def extend(self, records):
        for r in (records or []):
            self.add(r)

    def clear(self):
        self.records = []

    def __len__(self):
        return len(self.records)

    def __iter__(self):
        return iter(self.records)

    def __getitem__(self, index):
        return self.records[index]

    def to_list(self):
        return [r.to_dict() for r in self.records]

    @classmethod
    def from_list(cls, data, capacity=MAX_REPLAYS):
        buf = cls(capacity=capacity)
        buf.extend(data or [])
        return buf





def normalize_records(data, capacity=MAX_REPLAYS):
    if data is None:
        data = []
    if isinstance(data, ReplayBuffer):
        data = data.to_list()
    if isinstance(data, (str, bytes)):
        try:
            data = json.loads(data)
        except Exception:
            data = []
    out = []
    for item in (data if isinstance(data, (list, tuple)) else [data]):
        try:
            out.append(ReplayRecord.from_dict(item).to_dict())
        except Exception:
            continue
    # Sort by created_at descending so newest records appear first
    out.sort(key=lambda r: r.get("created_at", 0), reverse=True)
    if len(out) > capacity:
        out = out[:capacity]  # Keep only the first `capacity` (newest) records
    return out





def record_launch(frames, level_id=0, ship_id=None, fx_text="", fy_text="",
                 outcome="", seed=None, capacity=MAX_REPLAYS, existing=None):
    rec = ReplayRecord(level_id=level_id, ship_id=ship_id, fx_text=fx_text,
                       fy_text=fy_text, outcome=str(outcome),
                       frames=list(frames or []), seed=seed)
    if isinstance(existing, ReplayBuffer):
        existing.add(rec)
        return existing
    records = list(existing or [])
    records.append(rec.to_dict())
    return normalize_records(records, capacity)


class ReplayPlayer:
    def __init__(self, record=None, frames=None):
        self.record = ReplayRecord.from_dict(record) if record is not None else None
        if frames is not None:
            if self.record is None:
                self.record = ReplayRecord(frames=list(frames))
            else:
                self.record.frames = [f if isinstance(f, ReplayFrame) else ReplayFrame.from_dict(f) for f in frames]
        self.index = 0
        self.paused = False
        self.playing = True
        self.speed = 1.0
        self.MIN_SPEED = 0.1
        self.MAX_SPEED = 2.0

    def pause(self):
        self.paused = True
        self.playing = False

    def resume(self, play=True):
        self.paused = False
        self.playing = bool(play)

    def play(self):
        self.resume(True)

    def stop(self):
        self.playing = False

    def step(self, delta=1):
        if self.record is None or not self.record.frames:
            return None
        self.index = max(0, min(len(self.record.frames) - 1, self.index + int(delta)))
        return self.current()

    def seek(self, index):
        if self.record is None or not self.record.frames:
            self.index = 0
            return None
        self.index = max(0, min(len(self.record.frames) - 1, int(index)))
        return self.current()

    def current(self):
        if self.record is None or not self.record.frames:
            return None
        idx = max(0, min(len(self.record.frames) - 1, self.index))
        f = self.record.frames[idx]
        return f.to_dict() if hasattr(f, "to_dict") else f

    @property
    def frame(self):
        return self.current()

    @property
    def position(self):
        c = self.current()
        return (c["x"], c["y"]) if c else None

    @property
    def velocity(self):
        c = self.current()
        return (c["vx"], c["vy"]) if c else None

    @property
    def force(self):
        c = self.current()
        return (c["fx"], c["fy"]) if c else None

    def update(self, dt):
        return None

    def set_speed(self, speed):
        self.speed = max(self.MIN_SPEED, min(self.MAX_SPEED, speed))

    def increase_speed(self):
        self.set_speed(min(self.MAX_SPEED, self.speed + 0.1))

    def decrease_speed(self):
        self.set_speed(max(self.MIN_SPEED, self.speed - 0.1))


