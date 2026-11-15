"""Tests for the community browser rules (search, filters, sorting).

The rules live in ``vector_drift.community_browse``; they are pure Python,
so they are tested without pygame.
"""

import pytest

from vector_drift.community_browse import (
    DEFAULT_PICKUP_KIND,
    PICKUP_KINDS,
    SORT_CLEARERS,
    SORT_CLEARS,
    SORT_KEYS,
    SORT_NEWEST,
    SORT_OBSTACLES,
    SORT_OLDEST,
    SORT_PICKUP,
    SORT_PICKUPS,
    SORT_PLAYS,
    SORT_TIME,
    CommunityLevelInfo,
    FuzzyMatcher,
    filter_levels,
    fuzzy_score,
    level_info,
    normalize_text,
    sort_label,
)


def _row(row_id="r1", name="Meteor Maze", uploader="Alice", created="2024-05-01T10:00:00Z",
         time_limit=10.0, obstacles=0, pickups=(), plays=0, clears=0, clearers=0):
    return {
        "id": row_id,
        "user_id": "u1",
        "uploader_name": uploader,
        "level_name": name,
        "created_at": created,
        "level_data": {
            "id": 7001,
            "name": name,
            "start": [-7.0, 0.0],
            "target_center": [7.0, 0.0],
            "target_radius": 1.0,
            "time_limit": time_limit,
            "obstacles": [{"center": [0.0, 0.0], "radius": 0.5} for _ in range(obstacles)],
            "pickups": [{"center": [1.0, 0.0], "radius": 0.4, "kind": kind} for kind in pickups],
        },
        "play_count": plays,
        "clear_count": clears,
        "clear_players": [f"p{i}" for i in range(clearers)],
    }


# --- parsing ---------------------------------------------------------------

def test_level_info_reads_everything_the_browser_shows():
    info = level_info(_row(time_limit=12.5, obstacles=4, pickups=("money", "money", "life"),
                            plays=7, clears=3, clearers=2))
    assert info.name == "Meteor Maze"
    assert info.uploader == "Alice"
    assert info.time_limit == 12.5
    assert info.obstacle_count == 4
    assert info.pickup_count == 3
    assert info.count_of("money") == 2
    assert info.count_of("life") == 1
    assert info.count_of("shield") == 0
    assert info.play_count == 7
    assert info.clear_count == 3
    assert info.clear_player_count == 2
    assert info.created_at.startswith("2024-05-01")


def test_level_info_uses_the_name_inside_the_level_data():
    row = _row(name="")
    row["level_data"]["name"] = "Inner Name"
    assert level_info(row).name == "Inner Name"


def test_level_info_survives_broken_rows():
    for broken in (None, [], "nope", 42, {"level_data": "not a dict"},
                   {"level_data": {"obstacles": "nope", "pickups": 5}},
                   {"level_data": {"time_limit": "abc"}}, {"play_count": "many"}):
        info = level_info(broken)
        assert isinstance(info, CommunityLevelInfo)
        assert info.obstacle_count == 0
        assert info.pickup_count == 0
        assert info.play_count == 0


def test_level_info_counts_unknown_pickup_kinds_too():
    row = _row(pickups=("money", "totally_new_kind"))
    info = level_info(row)
    assert info.pickup_count == 2
    assert info.count_of("totally_new_kind") == 1


def test_level_info_accepts_a_clear_player_count_column():
    row = _row()
    row.pop("clear_players")
    row["clear_player_count"] = 5
    assert level_info(row).clear_player_count == 5


# --- fuzzy matching --------------------------------------------------------

def test_fuzzy_score_exact_match_is_the_best():
    assert fuzzy_score("meteor maze", "Meteor Maze") == pytest.approx(1.0)


def test_fuzzy_score_ignores_case_and_spaces():
    assert fuzzy_score("meteor  maze", "METEOR MAZE") == pytest.approx(1.0)


def test_fuzzy_score_ignores_accents():
    assert fuzzy_score("ubound", "Ünbound") > 0.8


def test_fuzzy_score_finds_a_name_inside_a_longer_one():
    score = fuzzy_score("meteor", "Meteor Maze")
    assert 0.8 < score <= 1.0


def test_fuzzy_score_survives_a_typo():
    assert fuzzy_score("metor", "Meteor") > 0.6


def test_fuzzy_score_rejects_an_unrelated_text():
    assert fuzzy_score("meteor maze", "Orbit Run") == 0.0
    assert fuzzy_score("xyz", "Meteor Maze") == 0.0


def test_fuzzy_score_of_an_empty_query_is_zero():
    assert fuzzy_score("", "Meteor Maze") == 0.0
    assert fuzzy_score("meteor", "") == 0.0


def test_closer_names_score_higher():
    assert fuzzy_score("meteor", "Meteor") > fuzzy_score("meteor", "Meteor Maze")


def test_normalize_text_collapses_spaces():
    assert normalize_text("  Meteor   Maze \n") == "meteor maze"


def test_matcher_without_a_query_is_inactive():
    matcher = FuzzyMatcher("")
    assert not matcher.active
    assert matcher.score("anything") == 0.0


def test_matcher_caches_the_score_of_a_text():
    matcher = FuzzyMatcher("meteor")
    first = matcher.score("Meteor Maze")
    assert matcher.score("Meteor Maze") == first


def test_matcher_best_uses_the_closest_of_several_names():
    matcher = FuzzyMatcher("maze")
    assert matcher.best(("Orbit Run", "Meteor Maze")) == fuzzy_score("maze", "Meteor Maze")


# --- filtering -------------------------------------------------------------

def _infos():
    return [
        level_info(_row("r1", "Meteor Maze", "Alice", "2024-05-01T10:00:00Z", 10.0, 5,
                        ("money", "money", "life"), plays=10, clears=3, clearers=2)),
        level_info(_row("r2", "Orbit Run", "Bob", "2024-06-01T10:00:00Z", 15.0, 0,
                        ("shield", "shield", "shield", "shield"), plays=2, clears=0, clearers=0)),
        level_info(_row("r3", "Meteor", "alicia", "2024-04-01T10:00:00Z", 8.0, 0,
                        (), plays=50, clears=20, clearers=3)),
    ]


def test_filter_levels_without_a_query_keeps_everything():
    assert len(filter_levels(_infos())) == 3


def test_filter_levels_searches_the_level_name():
    names = [info.name for info in filter_levels(_infos(), name_query="meteor")]
    assert set(names) == {"Meteor Maze", "Meteor"}


def test_filter_levels_searches_the_uploader_name():
    names = [info.name for info in filter_levels(_infos(), uploader_query="alic")]
    assert set(names) == {"Meteor Maze", "Meteor"}


def test_filter_levels_puts_the_closest_match_first():
    names = [info.name for info in filter_levels(_infos(), name_query="meteor")]
    assert names[0] == "Meteor"


def test_filter_levels_needs_both_queries_to_match():
    infos = _infos()
    assert filter_levels(infos, name_query="meteor", uploader_query="bob") == []
    assert len(filter_levels(infos, name_query="meteor", uploader_query="alic")) == 2


def test_filter_levels_drops_unrelated_levels():
    assert filter_levels(_infos(), name_query="nothing-like-this") == []


# --- the numeric filters ---------------------------------------------------

def test_filter_levels_min_plays():
    names = [info.name for info in filter_levels(_infos(), min_plays=10)]
    assert set(names) == {"Meteor Maze", "Meteor"}


def test_filter_levels_min_clears():
    names = [info.name for info in filter_levels(_infos(), min_clears=1)]
    assert set(names) == {"Meteor Maze", "Meteor"}


def test_filter_levels_min_clearers():
    names = [info.name for info in filter_levels(_infos(), min_clearers=3)]
    assert names == ["Meteor"]


def test_filter_levels_ignores_broken_minimums():
    assert len(filter_levels(_infos(), min_plays=-5)) == 3
    assert len(filter_levels(_infos(), min_clears="x")) == 3


# --- the sort orders -------------------------------------------------------

def test_filter_levels_sorts_newest_first_by_default():
    names = [info.name for info in filter_levels(_infos())]
    assert names == ["Orbit Run", "Meteor Maze", "Meteor"]


def test_filter_levels_sorts_oldest_first():
    names = [info.name for info in filter_levels(_infos(), sort_key=SORT_OLDEST)]
    assert names == ["Meteor", "Meteor Maze", "Orbit Run"]


def test_filter_levels_sorts_by_time_limit():
    infos = _infos()
    ascending = [info.name for info in filter_levels(infos, sort_key=SORT_TIME, descending=False)]
    assert ascending == ["Meteor", "Meteor Maze", "Orbit Run"]
    descending = [info.name for info in filter_levels(infos, sort_key=SORT_TIME, descending=True)]
    assert descending == ["Orbit Run", "Meteor Maze", "Meteor"]


def test_filter_levels_sorts_by_obstacle_count():
    infos = _infos()
    names = [info.name for info in filter_levels(infos, sort_key=SORT_OBSTACLES, descending=True)]
    assert names[0] == "Meteor Maze"


def test_filter_levels_sorts_by_total_pickup_count():
    infos = _infos()
    names = [info.name for info in filter_levels(infos, sort_key=SORT_PICKUPS, descending=True)]
    assert names[0] == "Orbit Run"


def test_filter_levels_sorts_by_one_pickup_kind():
    infos = _infos()
    names = [info.name for info in filter_levels(infos, sort_key=SORT_PICKUP,
                                                 pickup_kind="money", descending=True)]
    assert names[0] == "Meteor Maze"
    names = [info.name for info in filter_levels(infos, sort_key=SORT_PICKUP,
                                                 pickup_kind="shield", descending=True)]
    assert names[0] == "Orbit Run"


def test_filter_levels_sorts_by_plays_clears_and_clearers():
    infos = _infos()
    assert [i.name for i in filter_levels(infos, sort_key=SORT_PLAYS, descending=True)][0] == "Meteor"
    assert [i.name for i in filter_levels(infos, sort_key=SORT_CLEARS, descending=True)][0] == "Meteor"
    assert [i.name for i in filter_levels(infos, sort_key=SORT_CLEARERS, descending=True)][0] == "Meteor"


def test_filter_levels_falls_back_to_newest_for_an_unknown_sort_key():
    infos = _infos()
    names = [info.name for info in filter_levels(infos, sort_key="nonsense")]
    assert names == ["Orbit Run", "Meteor Maze", "Meteor"]


def test_filter_levels_survives_an_empty_level_list():
    assert filter_levels([]) == []
    assert filter_levels(None) == []


def test_sort_label_shows_the_direction():
    assert sort_label(SORT_NEWEST, True).endswith("↓")
    assert sort_label(SORT_TIME, False).endswith("↑")
    assert "Time limit" in sort_label(SORT_TIME, False)


def test_the_sort_options_cover_every_requested_order():
    for key in (SORT_NEWEST, SORT_OLDEST, SORT_TIME, SORT_OBSTACLES, SORT_PICKUPS,
                SORT_PICKUP, SORT_PLAYS, SORT_CLEARS, SORT_CLEARERS):
        assert key in SORT_KEYS


def test_the_pickup_kinds_are_the_ones_the_game_knows():
    from vector_drift.sprites import PICKUP_RENDERERS

    assert set(PICKUP_KINDS) == set(PICKUP_RENDERERS)
    assert DEFAULT_PICKUP_KIND in PICKUP_KINDS
