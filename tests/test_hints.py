"""Hints for the fixed levels: every fixed level has one and every answer flies.

The checks run over every fixed level in data.LEVELS, so a new fixed level
fails here until vector_drift/hints.toml gives it a hint whose answers reach.
"""

import pytest

from vector_drift.data import LEVELS, SHIPS, default_ship_id, get_level
from vector_drift.expr_parser import parse_expression
from vector_drift.hints import HintFormatError, get_hint, load_hints, parse_hints
from vector_drift.level_presets import is_dynamic_level
from vector_drift.physics import Flight, ForceField, Outcome

FIXED_IDS = [lv.id for lv in LEVELS if not is_dynamic_level(lv.id)]
ANSWERS = [(level_id, i, answer)
           for level_id, hint in sorted(load_hints().items())
           for i, answer in enumerate(hint.answers)]


def _answer_id(case):
    level_id, i, _ = case
    return f"level{level_id}-answer{i + 1}"


@pytest.mark.parametrize("level_id", FIXED_IDS)
def test_every_fixed_level_has_a_hint(level_id):
    assert get_hint(level_id) is not None, (
        f"fixed level {level_id} has no hint: add [level.{level_id}] to vector_drift/hints.toml")


def test_hints_only_cover_existing_fixed_levels():
    for level_id in load_hints():
        assert level_id in FIXED_IDS, f"hints.toml has level {level_id}, which is not a fixed level"


def test_levels_without_a_hint_return_none():
    assert get_hint(7) is None
    assert get_hint(99) is None


@pytest.mark.parametrize("case", ANSWERS, ids=_answer_id)
def test_every_answer_parses(case):
    level_id, _, answer = case
    parse_expression(answer.fx)
    parse_expression(answer.fy)


@pytest.mark.parametrize("case", ANSWERS, ids=_answer_id)
def test_every_answer_reaches_the_target(case):
    level_id, _, answer = case
    level = get_level(level_id)
    field = ForceField.from_exprs(parse_expression(answer.fx), parse_expression(answer.fy))
    flight = Flight(field, SHIPS[default_ship_id(level_id)], level)
    while flight.running:
        flight.step()

    assert flight.outcome is Outcome.REACHED, (
        f"level {level_id}: Fx = {answer.fx}, Fy = {answer.fy} ends {flight.outcome.name}")


def _level(**fields):
    entry = {"steps": ["Look right."], "answer_note": "Push right.",
             "answers": [{"fx": "5", "fy": "0"}]}
    entry.update(fields)
    return entry


@pytest.mark.parametrize("data, message", [
    ({"level": {"2": _level(steps=[])}}, "level 2: 'steps'"),
    ({"level": {"2": _level(answers=[])}}, "level 2: 'answers'"),
    ({"level": {"2": _level(answers=[{"fy": "0"}])}}, "level 2: answer 1 is missing 'fx'"),
    ({"level": {"2": _level(answers=[{"fx": "5", "fy": "0"}, {"fx": "5"}])}},
     "level 2: answer 2 is missing 'fy'"),
    ({"level": {"2": _level(steps=["ok", ""])}}, "level 2: 'steps'"),
    ({"level": {"2": {"steps": ["Look right."], "answers": [{"fx": "5", "fy": "0"}]}}},
     "level 2: 'answer_note'"),
    ({"level": {"7": _level()}}, "level 7"),
    ({"level": {"0": _level()}}, "level 0"),
    ({"level": {"one": _level()}}, "'one'"),
])
def test_bad_hint_data_is_rejected_with_the_level_and_field(data, message):
    with pytest.raises(HintFormatError, match=message):
        parse_hints(data)


def test_a_bad_hint_file_is_rejected(tmp_path):
    path = tmp_path / "hints.toml"
    path.write_text('[level.1]\nsteps = []\nanswer_note = "x"\n'
                    'answers = [ { fx = "5", fy = "0" } ]\n', encoding="utf-8")

    with pytest.raises(HintFormatError, match="level 1: 'steps'"):
        load_hints(path)


def test_answer_label_is_optional():
    hints = parse_hints({"level": {"3": _level(answers=[
        {"fx": "3", "fy": "-x - 2y", "label": "Top Shockwave"},
        {"fx": "3", "fy": "x - 2y"},
    ])}})

    assert [a.label for a in hints[3].answers] == ["Top Shockwave", None]
