"""Hints for the fixed levels: every fixed level has one and every answer flies.

The checks run over every fixed level in data.LEVELS (and every section of a
multi-section level), so a new fixed level fails here until
vector_drift/hints.toml gives it a hint whose answers reach.
"""

import pytest

from vector_drift.data import (LEVELS, SHIPS, default_ship_id, get_level, section_count,
                               section_level)
from vector_drift.expr_parser import parse_expression
from vector_drift.hints import (HintFormatError, SectionedHint, get_hint, hint_sections,
                                load_hints, parse_hints)
from vector_drift.level_presets import is_dynamic_level
from vector_drift.physics import Flight, ForceField, Outcome

FIXED_IDS = [lv.id for lv in LEVELS if not is_dynamic_level(lv.id)]
# Fixed levels whose hint is still to be written. Strict: the check fails
# again as soon as the hint exists, so remember to drop it here.
HINTS_PENDING = set()


def _hint_case(level_id):
    if level_id in HINTS_PENDING:
        return pytest.param(level_id, id=str(level_id), marks=pytest.mark.xfail(
            reason=f"level {level_id} hint pending (written after play-testing)", strict=True))
    return pytest.param(level_id, id=str(level_id))
# (level id, section index (0-based), answer index, answer); one-screen levels are section 0.
ANSWERS = [(level_id, k, i, answer)
           for level_id, hint in sorted(load_hints().items())
           for k, section_hint in enumerate(hint_sections(hint))
           for i, answer in enumerate(section_hint.answers)]


def _answer_id(case):
    level_id, k, i, _ = case
    section = f"-section{k + 1}" if get_level(level_id).sections else ""
    return f"level{level_id}{section}-answer{i + 1}"


@pytest.mark.parametrize("level_id", [_hint_case(i) for i in FIXED_IDS])
def test_every_fixed_level_has_a_hint(level_id):
    level = get_level(level_id)
    for k in range(section_count(level)):
        where = f"[level.{level_id}.section.{k + 1}]" if level.sections else f"[level.{level_id}]"
        assert get_hint(level_id, k) is not None, (
            f"fixed level {level_id} has no hint: add {where} to vector_drift/hints.toml")


def test_hints_only_cover_existing_fixed_levels():
    for level_id in load_hints():
        assert level_id in FIXED_IDS, f"hints.toml has level {level_id}, which is not a fixed level"


def test_levels_without_a_hint_return_none():
    assert get_hint(7) is None
    assert get_hint(99) is None
    assert get_hint(1, 1) is None                # a one-screen level has only section 0


@pytest.mark.parametrize("case", ANSWERS, ids=_answer_id)
def test_every_answer_parses(case):
    level_id, _, _, answer = case
    parse_expression(answer.fx)
    parse_expression(answer.fy)


@pytest.mark.parametrize("case", ANSWERS, ids=_answer_id)
def test_every_answer_reaches_the_target(case):
    """Each answer flies from its own section's start to that section's target."""
    level_id, k, _, answer = case
    level = section_level(get_level(level_id), k)
    field = ForceField.from_exprs(parse_expression(answer.fx), parse_expression(answer.fy))
    flight = Flight(field, SHIPS[default_ship_id(level_id)], level)
    while flight.running:
        flight.step()

    assert flight.outcome is Outcome.REACHED, (
        f"level {level_id} section {k + 1}: Fx = {answer.fx}, Fy = {answer.fy} "
        f"ends {flight.outcome.name}")


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


# --- multi-section levels: [level.N.section.K] ----------------------------------------
MULTI_ID = next(lv.id for lv in LEVELS if lv.sections)      # level 9, two sections


def _sections(*numbers, **fields):
    return {"section": {str(n): _level(**fields) for n in numbers}}


def test_section_hints_are_read_one_per_section():
    hints = parse_hints({"level": {str(MULTI_ID): {"section": {
        "1": _level(steps=["First screen."]),
        "2": _level(steps=["Second screen."], answers=[{"fx": "4", "fy": "0"}]),
    }}}})

    hint = hints[MULTI_ID]
    assert isinstance(hint, SectionedHint)
    first, second = hint_sections(hint)
    assert (first.section, first.steps) == (1, ("First screen.",))
    assert (second.section, second.steps) == (2, ("Second screen.",))
    assert second.answers[0].fx == "4"


def test_a_one_screen_hint_is_its_own_only_section():
    hint = parse_hints({"level": {"1": _level()}})[1]
    assert hint_sections(hint) == (hint,) and hint.section is None


@pytest.mark.parametrize("data, message", [
    # Wrong number of sections.
    (_sections(1), rf"level {MULTI_ID} section 2: missing"),
    (_sections(1, 2, 3), rf"level {MULTI_ID} section 3: the level has only 2 sections"),
    # Numbers not 1, 2, ... in a row.
    (_sections(1, 3), rf"level {MULTI_ID} section 3: .*section 2 is missing"),
    (_sections(2, 3), rf"level {MULTI_ID} section 2: .*section 1 is missing"),
    ({"section": {"one": _level(), "2": _level()}}, rf"level {MULTI_ID} section 'one'"),
    # Plain keys and sections together, or plain keys alone.
    ({**_level(), **_sections(1, 2)}, rf"level {MULTI_ID}: give either 'section'"),
    (_level(), rf"level {MULTI_ID}: has 2 sections"),
    # A bad field inside a section names that section.
    ({"section": {"1": _level(), "2": _level(steps=[])}}, rf"level {MULTI_ID} section 2: 'steps'"),
    ({"section": {"1": _level(answers=[{"fy": "0"}]), "2": _level()}},
     rf"level {MULTI_ID} section 1: answer 1 is missing 'fx'"),
    ({"section": {"1": _level(), "2": _level(extra="x")}}, rf"level {MULTI_ID} section 2: unknown keys"),
])
def test_bad_section_hints_name_the_level_and_section(data, message):
    with pytest.raises(HintFormatError, match=message):
        parse_hints({"level": {str(MULTI_ID): data}})


def test_a_one_screen_level_cannot_use_sections():
    with pytest.raises(HintFormatError, match="level 1: is a one-screen level"):
        parse_hints({"level": {"1": _sections(1)}})


def test_a_section_hint_file_is_read(tmp_path):
    path = tmp_path / "hints.toml"
    body = 'steps = ["s"]\nanswer_note = "n"\nanswers = [ { fx = "5", fy = "0" } ]\n'
    path.write_text(f"[level.{MULTI_ID}.section.1]\n{body}\n[level.{MULTI_ID}.section.2]\n{body}",
                    encoding="utf-8")
    assert len(hint_sections(load_hints(path)[MULTI_ID])) == 2
