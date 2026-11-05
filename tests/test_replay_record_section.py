"""Replay records keep the level section of each launch (old saves read as section 0)."""

import pytest

from vector_drift.replay import ReplayRecord, normalize_records

FRAMES = [{"t": 0.0, "x": -7.0, "y": 0.0, "vx": 0.0, "vy": 0.0, "fx": 5.0, "fy": 0.0}]


def _record(**extra):
    rec = {"level_id": 9, "ship_id": "ship02", "fx_text": "5", "fy_text": "0",
           "outcome": "Outcome.REACHED", "frames": FRAMES, "created_at": 100.0, "seed": None,
           "consumed_pickups": [[1.0, 2.0]], "obstacle_centers": [[0.0, 3.0]]}
    rec.update(extra)
    return rec


def test_section_index_survives_normalize_records():
    (out,) = normalize_records([_record(section_index=1)])
    assert out["section_index"] == 1


def test_section_index_survives_a_round_trip():
    rec = ReplayRecord.from_dict(_record(section_index=2))
    assert rec.section_index == 2
    assert ReplayRecord.from_dict(rec.to_dict()).section_index == 2


def test_an_old_record_without_the_field_is_section_zero_and_otherwise_unchanged():
    old = _record()
    (out,) = normalize_records([old])
    assert out["section_index"] == 0
    for key, value in old.items():
        assert out[key] == value, key


@pytest.mark.parametrize("value", [None, "1", "abc", -1, -7, 1.5, True, [1]])
def test_a_bad_section_index_reads_as_zero(value):
    (out,) = normalize_records([_record(section_index=value)])
    assert out["section_index"] == 0
    assert out["level_id"] == 9 and out["frames"] == FRAMES       # the record is kept


def test_the_default_record_is_section_zero():
    assert ReplayRecord().section_index == 0
    assert ReplayRecord().to_dict()["section_index"] == 0
