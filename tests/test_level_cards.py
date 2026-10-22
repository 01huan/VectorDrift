"""Level-select cards: long dynamic-level blurbs wrap inside the card."""
from types import SimpleNamespace

import pygame
import pytest

from vector_drift.config import px
from vector_drift.level_presets import PRESETS
from vector_drift.scenes.levels import CARD_W
from vector_drift.ui import get_font, wrap_text

pytestmark = pytest.mark.usefixtures("pygame_display")

CARD_TEXT_W = px(CARD_W - 36)


def test_wrap_text_keeps_lines_within_width():
    text = "Denser maze, smaller target, more bombs"
    lines = wrap_text(text, 13, CARD_TEXT_W)
    assert len(lines) == 2
    assert " ".join(lines) == text
    assert all(get_font(13).size(line)[0] <= CARD_TEXT_W for line in lines)


def test_wrap_text_edge_cases():
    assert wrap_text("", 13, 100) == []
    assert wrap_text("short", 13, 1000) == ["short"]
    assert wrap_text("unbreakablewordthatistoolong ok", 13, 10) == ["unbreakablewordthatistoolong", "ok"]


@pytest.mark.parametrize("level_id", sorted(PRESETS))
def test_every_preset_blurb_fits_two_lines(level_id):
    blurb = PRESETS[level_id].card_blurb
    assert len(wrap_text(blurb, 10, CARD_TEXT_W)) <= 2


def test_level_select_draws():
    from vector_drift.scenes.base import SceneManager
    from vector_drift.scenes.levels import LevelSelectScene
    audio = SimpleNamespace(play=lambda *a: None)
    scene = LevelSelectScene(SceneManager(audio))
    scene.draw(pygame.Surface((px(1280), px(720))))
