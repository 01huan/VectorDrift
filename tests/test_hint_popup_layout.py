"""The hint window fits every fixed level's hint: no text is cut or covered.

Runs over every section of every fixed level in hints.toml, so a new level's
hint is checked as soon as it is added. What is checked is what the popup
actually draws (the rects draw_text returns), not how it lays the page out.
"""

import pygame
import pytest

from vector_drift import config
from vector_drift.config import px
from vector_drift.hints import HintAnswer, LevelHint, hint_sections, load_hints
from vector_drift.scenes import hint_popup as hint_popup_module
from vector_drift.scenes.hint_popup import HintPopup

pytestmark = pytest.mark.usefixtures("pygame_display")

SECTIONS = [pytest.param(section_hint, id=f"level{level_id}-section{k + 1}")
            for level_id, hint in sorted(load_hints().items())
            for k, section_hint in enumerate(hint_sections(hint))]


def _drawn_texts(monkeypatch, popup):
    """[(text, rect)] of every text the popup draws on its current page."""
    drawn = []
    real = hint_popup_module.draw_text

    def spy(surface, text, *args, **kwargs):
        rect = real(surface, text, *args, **kwargs)
        drawn.append((text, rect))
        return rect

    monkeypatch.setattr(hint_popup_module, "draw_text", spy)
    popup.draw(pygame.Surface((config.WINDOW_W, config.WINDOW_H)))
    monkeypatch.setattr(hint_popup_module, "draw_text", real)
    return drawn


def _formula_rects(monkeypatch, popup):
    """[(text, rect)] of the Fx / Fy text on the answer page."""
    popup.page = popup.answer_page
    return [(text, rect) for text, rect in _drawn_texts(monkeypatch, popup)
            if text.startswith(("Fx =", "Fy ="))]


@pytest.mark.parametrize("hint", SECTIONS)
def test_every_step_fits_above_the_buttons(monkeypatch, hint):
    popup = HintPopup(hint)
    # Leave a line for the "Need N coins" note drawn above the buttons on the last step.
    bottom = popup.next_button.rect.y - px(12) - px(hint_popup_module.LINE_H)
    for page, step in enumerate(hint.steps):
        popup.page = page
        lines = [(t, r) for t, r in _drawn_texts(monkeypatch, popup)
                 if r.y >= popup.card.y + px(78)]
        assert " ".join(t for t, _ in lines) == " ".join(step.split())     # nothing dropped
        for text, rect in lines:
            assert popup.card.x < rect.x and rect.right < popup.card.right, text
            assert rect.bottom <= bottom, text


@pytest.mark.parametrize("hint", SECTIONS)
def test_no_answer_text_runs_under_the_apply_button(monkeypatch, hint):
    popup = HintPopup(hint)
    formulas = _formula_rects(monkeypatch, popup)
    shown = " ".join(text for text, _ in formulas)
    for answer in hint.answers:                                 # every formula is drawn whole
        assert f"Fx = {answer.fx}" in shown and f"Fy = {answer.fy}" in shown
    apply_left = min(button.rect.x for button in popup.apply_buttons)
    for text, rect in formulas:
        assert rect.right < apply_left, text


@pytest.mark.parametrize("hint", SECTIONS)
def test_every_answer_row_sits_inside_the_card(monkeypatch, hint):
    popup = HintPopup(hint)
    for text, rect in _formula_rects(monkeypatch, popup):
        assert popup.card.contains(rect), text
    for (_, row), button in zip(popup._answer_rows, popup.apply_buttons):
        assert popup.card.contains(row)
        assert row.bottom <= popup.prev_button.rect.y              # above Back / Close
        assert row.contains(button.rect)


# --- the layout rule itself, on made-up answers ------------------------------------------
SHORT = HintAnswer(fx="-y", fy="x + 6")
LONG = HintAnswer(fx="-(x - 3) + abs(x - 3)", fy="-10((x - 3) + abs(x - 3))")


def _hint(*answers):
    return LevelHint(level_id=99, steps=("A step.",), answer_note="Note:", answers=answers)


def test_a_short_answer_keeps_one_line(monkeypatch):
    popup = HintPopup(_hint(SHORT))
    (text, rect), = _formula_rects(monkeypatch, popup)
    assert text == "Fx = -y    Fy = x + 6"
    (_, row), = popup._answer_rows
    assert row.height == px(40) and rect.centery == row.centery


def test_a_long_answer_goes_onto_two_lines_with_apply_centred(monkeypatch):
    popup = HintPopup(_hint(LONG))
    (fx_text, fx_rect), (fy_text, fy_rect) = _formula_rects(monkeypatch, popup)
    assert (fx_text, fy_text) == (f"Fx = {LONG.fx}", f"Fy = {LONG.fy}")
    assert fx_rect.x == fy_rect.x and fx_rect.bottom <= fy_rect.top
    (_, row), = popup._answer_rows
    assert row.top < fx_rect.top and fy_rect.bottom < row.bottom
    assert popup.apply_buttons[0].rect.centery == row.centery


def test_a_two_line_answer_pushes_the_next_one_down(monkeypatch):
    one_line = HintPopup(_hint(SHORT, SHORT))._answer_rows
    two_lines = HintPopup(_hint(LONG, SHORT))._answer_rows
    assert two_lines[0][1].height > one_line[0][1].height
    grow = two_lines[0][1].height - one_line[0][1].height
    assert two_lines[1][1].y == one_line[1][1].y + grow
