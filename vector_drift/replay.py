"""Replay storage for ship launches."""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, field
from typing import Any, List, Optional

MAX_REPLAYS = 10
REPLAY_CAPACITY = MAX_REPLAYS
MAX_LAUNCH_RECORDS = MAX_REPLAYS
FIXED_REPLAY_COUNT = MAX_REPLAYS


@dataclass
class ReplayFrame:
    t: float = 0.0
    x: float = 0.0
    y: float = 0.0
    vx: float = 0.0
    vy: float = 0.0
    fx: float = 0.0
    fy: float = 0.0

    def to_dict(self):
        return {"t": float(self.t), "x": float(self.x), "y": float(self.y),
                "vx": float(self.vx), "vy": float(self.vy),
                "fx": float(self.fx), "fy": float(self.fy)}

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
        return ReplayFrame(t=_f("t"), x=_f("x"), y=_f("y"),
                          vx=_f("vx"), vy=_f("vy"), fx=_f("fx"), fy=_f("fy"))


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

    def to_dict(self):
        return {
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
        }

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
        )


LaunchRecord = ReplayRecord
FlightRecord = ReplayRecord
LaunchReplay = ReplayRecord
Replay = ReplayRecord


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


ReplayStore = ReplayBuffer
LaunchStore = ReplayBuffer
ReplayManager = ReplayBuffer
LaunchManager = ReplayBuffer
ReplayHistory = ReplayBuffer


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


trim_records = normalize_records


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


ReplayViewer = ReplayPlayer
ReplayController = ReplayPlayer
ReplayPlayback = ReplayPlayer
ReplaySession = ReplayPlayer
ReplayEngine = ReplayPlayer
ReplayRunner = ReplayPlayer
