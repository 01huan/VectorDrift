import pygame
import pytest

from vector_drift import config, ui

pytestmark = pytest.mark.usefixtures("pygame_display")


def test_ui_basic_functions():
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    font = ui.get_font(16, "ui")
    assert font is not None
    ui.draw_text(surface, "hello", (10, 10), 16, config.TEXT)
    lines = ui.wrap_text("hello world " * 5, 16, 100)
    assert isinstance(lines, list)
    ui.draw_panel_box(surface, pygame.Rect(0, 0, 50, 50))
    ui.draw_squiggle(surface, 0, 50, 20)
    span = ui.error_span("abc def", 4)
    assert isinstance(span, tuple)
    # clipboard roundtrip (may be unavailable)
    try:
        ui.clipboard_put("x")
        assert ui.clipboard_get() in ("x", "")
    except Exception:
        pass
    # highlight
    assert ui.highlight("Fx = 2x + y") is not None
    # icon surfaces
    for name in ("play", "stop", "grid", "chev_left", "chev_right", "lock", "check"):
        img = ui.icon_surface(name, 16, config.TEXT)
        assert img is not None
    # button
    btn = ui.Button((0, 0, 60, 30), "Click", style="primary")
    assert btn.handle_event(pygame.event.Event(pygame.MOUSEMOTION, pos=(5, 5))) is None
    assert btn.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(5, 5))) == "click"
    btn.draw(surface)
    btn.enabled = False
    btn.draw(surface)
    # icon button
    ib = ui.IconButton((0, 0, 30, 30), "play", style="circle")
    ib.handle_event(pygame.event.Event(pygame.MOUSEMOTION, pos=(5, 5)))
    assert ib.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(5, 5))) == "click"
    ib.draw(surface)
    ib.enabled = False
    ib.draw(surface)
    # _dim
    assert ui._dim(config.TEXT) is not None
