from vector_drift.data import LevelSpec, ObstacleSpec, PickupSpec


def test_level_spec_roundtrip():
    level = LevelSpec(
        id=7,
        name="/custom",
        start=(-1.5, 2.0),
        target_center=(3, -4),
        target_radius=1.25,
        ship_id="ship03",
        time_limit=8.5,
        lives=3,
        obstacles=(ObstacleSpec(center=(0.5, 0.25), radius=0.7, restitution=0.9, kind="bumper"),),
        pickups=(PickupSpec(center=(1.0, -1.0), radius=0.4, kind="money"),),
    )
    row = level.to_row()
    restored = LevelSpec.from_row(row)
    assert restored == level
    assert isinstance(row["start"], list)
    assert isinstance(row["obstacles"][0]["center"], list)


def test_level_spec_from_row_defaults():
    row = {
        "id": 1,
        "name": "minimal",
        "start": [0, 0],
        "target_center": [5, 0],
        "target_radius": 1,
    }
    restored = LevelSpec.from_row(row)
    assert restored is not None
    assert restored.ship_id == "ship01"
    assert restored.time_limit == 10.0
    assert restored.lives == 5
    assert restored.obstacles == ()
    assert restored.pickups == ()


def test_level_spec_from_row_malformed():
    assert LevelSpec.from_row(None) is None
    assert LevelSpec.from_row({}) is None
    bad_obstacle = {
        "id": 1,
        "name": "bad",
        "start": [0, 0],
        "target_center": [5, 0],
        "target_radius": 1,
        "obstacles": [{"radius": 2}],
    }
    assert LevelSpec.from_row(bad_obstacle) is None
    bad_pickup = dict(bad_obstacle, obstacles=[])
    bad_pickup["pickups"] = [{"kind": "money"}]
    assert LevelSpec.from_row(bad_pickup) is None
