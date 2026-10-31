import tomllib

import pytest

from vector_drift.hints import HintFormatError, parse_hints, load_hints
from pathlib import Path
import tempfile, os


def test_parse_hints_top_level_unknown():
    with pytest.raises(HintFormatError):
        parse_hints({"foo": 1})


def test_parse_hints_level_not_table():
    with pytest.raises(HintFormatError):
        parse_hints({"level": "x"})


def test_parse_level_key_not_int():
    with pytest.raises(HintFormatError):
        parse_hints({"level": {"abc": {}}})


def test_parse_level_out_of_range():
    with pytest.raises(HintFormatError):
        parse_hints({"level": {"99": {"steps": ["s"], "answer_note": "n", "answers": [{"fx": "1", "fy": "2"}]}}})


def test_parse_level_entry_not_table():
    with pytest.raises(HintFormatError):
        parse_hints({"level": {"1": "x"}})


def test_parse_level_steps_invalid():
    for steps in (None, [], ["", "  "], "x", [1]):
        with pytest.raises(HintFormatError):
            parse_hints({"level": {"1": {"steps": steps, "answer_note": "n", "answers": [{"fx": "1", "fy": "2"}]}}})


def test_parse_level_answer_note_invalid():
    with pytest.raises(HintFormatError):
        parse_hints({"level": {"1": {"steps": ["s"], "answer_note": "", "answers": [{"fx": "1", "fy": "2"}]}}})


def test_parse_level_answers_invalid():
    for answers in (None, [], "x"):
        with pytest.raises(HintFormatError):
            parse_hints({"level": {"1": {"steps": ["s"], "answer_note": "n", "answers": answers}}})


def test_parse_level_unknown_keys():
    with pytest.raises(HintFormatError):
        parse_hints({"level": {"1": {"steps": ["s"], "answer_note": "n", "answers": [{"fx": "1", "fy": "2"}], "foo": 1}}})


def test_parse_answer_not_table():
    with pytest.raises(HintFormatError):
        parse_hints({"level": {"1": {"steps": ["s"], "answer_note": "n", "answers": ["x"]}}})


def test_parse_answer_missing_keys():
    for key in ("fx", "fy"):
        entry = {"fx": "1", "fy": "2"}
        del entry[key]
        with pytest.raises(HintFormatError):
            parse_hints({"level": {"1": {"steps": ["s"], "answer_note": "n", "answers": [entry]}}})


def test_parse_answer_empty_text():
    for key in ("fx", "fy"):
        entry = {"fx": "1", "fy": "2"}
        entry[key] = ""
        with pytest.raises(HintFormatError):
            parse_hints({"level": {"1": {"steps": ["s"], "answer_note": "n", "answers": [entry]}}})


def test_parse_answer_label_invalid():
    with pytest.raises(HintFormatError):
        parse_hints({"level": {"1": {"steps": ["s"], "answer_note": "n", "answers": [{"fx": "1", "fy": "2", "label": ""}]}}})


def test_parse_answer_unknown_keys():
    with pytest.raises(HintFormatError):
        parse_hints({"level": {"1": {"steps": ["s"], "answer_note": "n", "answers": [{"fx": "1", "fy": "2", "z": 1}]}}})


def test_load_hints_bad_toml(tmp_path):
    p = tmp_path / "bad.toml"
    p.write_text("this is not = toml [[[", encoding="utf-8")
    with pytest.raises(HintFormatError):
        load_hints(p)
