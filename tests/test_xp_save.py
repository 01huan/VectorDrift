"""XP progress on the Session and in the saved profile."""

from vector_drift.scenes.base import Session


def test_a_new_session_starts_without_xp():
    session = Session()
    assert session.xp_total == 0
    assert session.fixed_clear_counts == {}
    assert session.xp_achievements == set()
    assert session.xp_rewarded_level == 1


def test_sessions_do_not_share_xp_containers():
    a, b = Session(), Session()
    a.fixed_clear_counts[1] = 2
    a.xp_achievements.add("kaboom")
    assert b.fixed_clear_counts == {}
    assert b.xp_achievements == set()
