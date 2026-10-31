import math

from vector_drift.pickups import (
    discs_overlap,
    PickupState,
    check_pickups_segment,
    extratime_bonus_steps,
    SHOCKWAVE_BLAST_RADIUS,
)
from vector_drift.data import PickupSpec


def test_discs_overlap_exception():
    assert discs_overlap("bad", 1, (0, 0), 1) is True


def test_pickup_state_repr():
    p = PickupState((1.0, 2.0), 0.5, "money")
    r = repr(p)
    assert "PickupState" in r
    assert p.center == (1.0, 2.0)


def test_pickup_state_from_spec():
    spec = PickupSpec(center=(1.0, 2.0), radius=0.5, kind="life")
    p = PickupState.from_spec(spec)
    assert p.kind == "life"


def test_check_pickups_segment_unknown_kind_and_exception():
    class BadPickup:
        consumed = False
        center = (0.0, 0.0)
        radius = 0.5
        kind = "unknown_kind_xyz"

    p = BadPickup()
    events = check_pickups_segment([p], (-1.0, 0.0), (1.0, 0.0), 0.0)
    assert p.consumed is True
    assert events and events[0]["kind"] == "unknown_kind_xyz"

    # effect raises
    from vector_drift.pickups import register_effect

    @register_effect("raising_kind")
    def raising_effect(pickup, ctx):
        raise RuntimeError("boom")

    class RaisingPickup:
        consumed = False
        center = (0.0, 0.0)
        radius = 0.5
        kind = "raising_kind"

    p2 = RaisingPickup()
    events2 = check_pickups_segment([p2], (-1.0, 0.0), (1.0, 0.0), 0.0)
    assert p2.consumed is True
    assert events2 and events2[0]["kind"] == "raising_kind"

    # effect returns None -> default event
    @register_effect("none_kind")
    def none_effect(pickup, ctx):
        return None

    class NonePickup:
        consumed = False
        center = (0.0, 0.0)
        radius = 0.5
        kind = "none_kind"

    p3 = NonePickup()
    events3 = check_pickups_segment([p3], (-1.0, 0.0), (1.0, 0.0), 0.0)
    assert events3 and events3[0]["kind"] == "none_kind"

    # consumed skip
    p4 = PickupState((0.0, 0.0), 0.5, "shockwave")
    p4.consumed = True
    assert check_pickups_segment([p4], (-1.0, 0.0), (1.0, 0.0), 0.0) == []

    # segment_hits_circle exception (bad center)
    class BadCenter:
        consumed = False
        center = "bad"
        radius = 0.5
        kind = "shockwave"

    p5 = BadCenter()
    assert check_pickups_segment([p5], (-1.0, 0.0), (1.0, 0.0), 0.0) == []
    assert p5.consumed is False


def test_extratime_bonus_steps():
    assert extratime_bonus_steps(0.1) > 0
