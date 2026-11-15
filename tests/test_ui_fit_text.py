"""Tests for the text helpers used by the community browser cards."""

import pytest

from vector_drift.ui import fit_text, get_font

pytestmark = pytest.mark.usefixtures("pygame_display")


def test_a_short_text_is_kept():
    assert fit_text("Meteor", 200, 15) == "Meteor"


def test_a_long_text_gets_an_ellipsis():
    text = "A very long community level name that does not fit"
    fitted = fit_text(text, 80, 15)
    assert fitted.endswith("…")
    assert len(fitted) < len(text)
    assert get_font(15, "ui").size(fitted)[0] <= 80


def test_an_empty_width_gives_an_empty_text():
    assert fit_text("Meteor", 0, 15) == ""


def test_a_none_text_is_empty():
    assert fit_text(None, 100, 15) == ""


def test_a_width_that_is_too_small_gives_nothing():
    assert fit_text("Meteor", 2, 15) == ""


def test_the_text_still_starts_with_the_beginning():
    text = "Meteor Maze with a long tail"
    assert fit_text(text, 100, 15).startswith("Meteor")
