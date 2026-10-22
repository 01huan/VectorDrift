"""Persistent storage for simulation records.

Design goals:
* Append-only JSONL so crashes never corrupt earlier records.
* Summary records (no trajectory) live alongside full records; callers choose
  which to read.  This avoids unbounded growth from full trajectories.
* Configurable record cap with FIFO eviction and score-based retention.
* Schema version recorded per file; readers can detect old schemas.
* Fully offline: standard library only.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

from .data import (
    SCHEMA_NAME,
    SCHEMA_VERSION,
    SimulationRecord,
    dict_to_record,
    record_to_dict,
)


@dataclass
class StoreConfig:
    """Configuration for :class:`JSONLStore`."""

    path: Path | str = Path("solver_data") / "simulations.jsonl"
    max_records: int = 50_000
    keep_best_n: int = 500
    keep_success_n: int = 200
    summary_only_after: int = 10_000
    auto_compact: bool = True


class JSONLStore:
    """Append-only JSONL store of :class:`SimulationRecord` objects."""

    def __init__(self, config: StoreConfig | None = None):
        self.config = config or StoreConfig()
        self.path = Path(self.config.path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._written_this_session: int = 0
        self._header_written = False

    def add(self, record: SimulationRecord, include_trajectory: bool = True) -> None:
        line = json.dumps(record.to_dict(include_trajectory=include_trajectory),
                          ensure_ascii=False)
        with self.path.open("a", encoding="utf-8") as fh:
            if not self._header_written:
                fh.write(json.dumps({
                    "_header": {
                        "schema_name": SCHEMA_NAME,
                        "schema_version": SCHEMA_VERSION,
                    }
                }, ensure_ascii=False) + "\n")
                self._header_written = True
            fh.write(line + "\n")
        self._written_this_session += 1

    def add_many(self, records: list[SimulationRecord],
                 include_trajectory: bool = True) -> None:
        for r in records:
            self.add(r, include_trajectory=include_trajectory)

    def iter_records(self, include_trajectory: bool = False) -> Iterator[SimulationRecord]:
        """Yield records from disk.  Skips the header line and malformed lines."""
        if not self.path.exists():
            return
        with self.path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if "_header" in obj:
                    continue
                try:
                    yield dict_to_record(obj)
                except Exception:
                    continue

    def all_records(self, include_trajectory: bool = False) -> list[SimulationRecord]:
        return list(self.iter_records(include_trajectory=include_trajectory))

    def successful(self, include_trajectory: bool = False) -> list[SimulationRecord]:
        return [r for r in self.iter_records(include_trajectory=include_trajectory)
                if r.success]

    def failures(self, include_trajectory: bool = False) -> list[SimulationRecord]:
        return [r for r in self.iter_records(include_trajectory=include_trajectory)
                if not r.success and r.outcome != "running"]

    def near_success(self, threshold: float = 0.5,
                     include_trajectory: bool = False) -> list[SimulationRecord]:
        return [r for r in self.iter_records(include_trajectory=include_trajectory)
                if not r.success and 0 < r.min_dist_to_target <= threshold]

    def count(self) -> int:
        return sum(1 for _ in self.iter_records())

    def success_count(self) -> int:
        return sum(1 for r in self.iter_records() if r.success)

    def schema_info(self) -> dict | None:
        if not self.path.exists():
            return None
        with self.path.open("r", encoding="utf-8") as fh:
            first = fh.readline().strip()
        if not first:
            return None
        try:
            obj = json.loads(first)
        except json.JSONDecodeError:
            return None
        return obj.get("_header")

    def compact(self) -> int:
        """Enforce record caps and trajectory pruning.  Returns records removed."""
        records = self.all_records(include_trajectory=True)
        if not records:
            return 0

        removed = 0
        ordered = sorted(records, key=lambda r: r.timestamp)
        cutoff_idx = max(0, len(ordered) - self.config.summary_only_after)
        rewritten: list[SimulationRecord] = []
        for i, r in enumerate(ordered):
            if i < cutoff_idx and r.trajectory is not None:
                r.trajectory = None
                removed += 1
            rewritten.append(r)

        keep_ids = set()
        scored = sorted(rewritten, key=lambda r: r.score, reverse=True)
        for r in scored[: self.config.keep_best_n]:
            keep_ids.add(r.record_id)
        for r in rewritten:
            if r.success:
                keep_ids.add(r.record_id)

        evict_candidates = [r for r in ordered if r.record_id not in keep_ids]
        while len(rewritten) - removed > self.config.max_records and evict_candidates:
            victim = evict_candidates.pop(0)
            rewritten.remove(victim)
            removed += 1

        self._rewrite(rewritten)
        return removed

    def _rewrite(self, records: list[SimulationRecord]) -> None:
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            fh.write(json.dumps({
                "_header": {
                    "schema_name": SCHEMA_NAME,
                    "schema_version": SCHEMA_VERSION,
                }
            }, ensure_ascii=False) + "\n")
            for r in records:
                fh.write(json.dumps(r.to_dict(include_trajectory=r.trajectory is not None),
                                    ensure_ascii=False) + "\n")
        os.replace(tmp, self.path)

    def export_json(self, dest: Path | str, include_trajectory: bool = False) -> int:
        records = self.all_records(include_trajectory=include_trajectory)
        out = [r.to_dict(include_trajectory=include_trajectory) for r in records]
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open("w", encoding="utf-8") as fh:
            json.dump(out, fh, ensure_ascii=False, indent=2)
        return len(out)

    def close(self) -> int:
        if self.config.auto_compact:
            return self.compact()
        return 0
