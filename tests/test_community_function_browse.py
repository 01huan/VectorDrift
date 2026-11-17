"""Tests for the community Function browser rules.

The rules live in ``vector_drift.community_function_browse``; they are pure
Python, so they are tested without pygame.
"""

from vector_drift.community_function_browse import (
    MAX_TAGS,
    SORT_FAVORITES,
    SORT_NEWEST,
    SORT_OLDEST,
    SORT_RATING,
    SORT_SUCCESS,
    SORT_USES,
    average_rating,
    filter_functions,
    function_info,
    normalize_tags,
    parse_tags,
    tag_matches,
    tags_to_text,
)


def _row(row_id="r1", name="Vortex", uploader="Alice", created="2026-10-01T10:00:00Z",
         updated="2026-10-02T10:00:00Z", description="spiral field",
         tags=("vortex",), fx="-y", fy="x",
         uses=0, successful=0, unique_users=0, favorites=0,
         rating_count=0, rating_total=0):
    return {
        "id": row_id,
        "user_id": "u1",
        "uploader_name": uploader,
        "function_name": name,
        "fx": fx,
        "fy": fy,
        "description": description,
        "tags": list(tags),
        "created_at": created,
        "updated_at": updated,
        "usage_count": uses,
        "successful_usage_count": successful,
        "unique_user_count": unique_users,
        "favorite_count": favorites,
        "rating_count": rating_count,
        "rating_total": rating_total,
    }


# --- parsing ---------------------------------------------------------------

def test_function_info_reads_everything_the_card_shows():
    info = function_info(_row(uses=12, successful=9, unique_users=5, favorites=7,
                              rating_count=4, rating_total=18))
    assert info.name == "Vortex"
    assert info.uploader == "Alice"
    assert info.fx == "-y" and info.fy == "x"
    assert info.description == "spiral field"
    assert info.tags == ("vortex",)
    assert info.usage_count == 12
    assert info.successful_usage_count == 9
    assert info.unique_user_count == 5
    assert info.favorite_count == 7
    assert info.rating_count == 4
    assert info.rating_total == 18
    assert info.average_rating == 4.5
    assert info.success_rate == 0.75
    assert info.detail_date() == "2026-10-02"


def test_function_info_tolerates_missing_statistics():
    info = function_info({"id": "x", "function_name": "Loose"})
    assert info.usage_count == 0
    assert info.average_rating == 0.0
    assert info.success_rate == 0.0
    assert info.tags == ()


def test_function_info_tolerates_a_broken_row():
    assert function_info(None).name == "Untitled"
    assert function_info("junk").name == "Untitled"


def test_average_rating_never_divides_by_zero():
    assert average_rating(0, 0) == 0.0
    assert average_rating(14, 4) == 3.5
    assert average_rating(999, 1) == 5.0    # clamped to the 1..5 scale


# --- tags --------------------------------------------------------------------

def test_normalize_tags_trims_deduplicates_and_caps():
    assert normalize_tags(["  Vortex ", "vortex", "calm", ""]) == ("Vortex", "calm")
    assert normalize_tags("a, b, c") == ("a", "b", "c")
    too_many = [f"tag{i}" for i in range(30)]
    assert len(normalize_tags(too_many)) == MAX_TAGS


def test_parse_tags_and_tags_to_text_round_trip():
    assert parse_tags("grav, spiral") == ("grav", "spiral")
    assert tags_to_text(("grav", "spiral")) == "grav, spiral"


def test_tag_matches_is_case_insensitive_partial():
    tags = ("Vortex", "spiral")
    assert tag_matches("vort", tags)
    assert tag_matches("SPIR", tags)
    assert not tag_matches("gravity", tags)
    assert tag_matches("", tags)


# --- sorting and filtering ----------------------------------------------------

def test_filter_functions_sorts_by_uses():
    infos = [function_info(_row(row_id=f"r{i}", uses=i * 10)) for i in range(1, 5)]
    ordered = filter_functions(infos, sort_key=SORT_USES)
    assert [i.usage_count for i in ordered] == [40, 30, 20, 10]


def test_filter_functions_sorts_by_successful_uses():
    infos = [function_info(_row(row_id=f"r{i}", successful=i)) for i in range(1, 5)]
    ordered = filter_functions(infos, sort_key=SORT_SUCCESS)
    assert [i.successful_usage_count for i in ordered] == [4, 3, 2, 1]


def test_filter_functions_sorts_by_favorites_and_rating():
    infos = [function_info(_row(row_id="low", favorites=1, rating_count=1, rating_total=2)),
             function_info(_row(row_id="high", favorites=3, rating_count=1, rating_total=5)),
             function_info(_row(row_id="mid", favorites=2, rating_count=1, rating_total=4))]
    ordered = filter_functions(infos, sort_key=SORT_FAVORITES)
    assert [i.row_id for i in ordered] == ["high", "mid", "low"]
    by_rating = filter_functions(infos, sort_key=SORT_RATING, descending=True)
    assert [i.row_id for i in by_rating] == ["high", "mid", "low"]


def test_filter_functions_sorts_oldest_and_newest():
    infos = [function_info(_row(row_id="a", created="2026-01-01T00:00:00Z")),
             function_info(_row(row_id="b", created="2026-06-01T00:00:00Z"))]
    assert [i.row_id for i in filter_functions(infos, sort_key=SORT_NEWEST)] == ["b", "a"]
    assert [i.row_id for i in filter_functions(infos, sort_key=SORT_OLDEST)] == ["a", "b"]


def test_filter_functions_honors_the_tag_filter():
    infos = [function_info(_row(row_id="a", tags=("vortex",))),
             function_info(_row(row_id="b", tags=("gravity",)))]
    assert [i.row_id for i in filter_functions(infos, tag_query="vort")] == ["a"]
    assert filter_functions(infos, tag_query="absent") == []


def test_filter_functions_combines_the_two_text_queries():
    infos = [
        function_info(_row(row_id="a", name="Vortex Rush", uploader="Alice")),
        function_info(_row(row_id="b", name="Vortex Calm", uploader="Bob")),
        function_info(_row(row_id="c", name="Calm Drift", uploader="Alice")),
    ]
    assert [i.row_id for i in filter_functions(infos, name_query="vortex")] == ["a", "b"]
    assert [i.row_id for i in filter_functions(infos, uploader_query="alice")] == ["a", "c"]
    assert [i.row_id for i in filter_functions(infos, name_query="vortex",
                                                uploader_query="alice")] == ["a"]


def test_filter_functions_min_uses():
    infos = [function_info(_row(row_id=f"r{i}", uses=i * 10)) for i in range(1, 5)]
    assert [i.usage_count for i in filter_functions(infos, min_uses=25,
                                                    sort_key=SORT_USES)] == [40, 30]


def test_filter_functions_closest_match_first():
    infos = [function_info(_row(row_id="far", name="XxY vortex zz")),
             function_info(_row(row_id="near", name="vortex"))]
    assert filter_functions(infos, name_query="vortex")[0].row_id == "near"
