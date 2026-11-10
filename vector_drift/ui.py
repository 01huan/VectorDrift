"""Fonts, widgets and code editor (re-exported from submodules).

Kept as the single historical import path for UI helpers. New code may import
from ``ui_fonts`` / ``ui_editor`` / ``ui_icons`` directly.
"""

import re

import pygame

from . import config
from .config import px
from .ui_editor import (
    HISTORY_LIMIT,
    STEP_BREAKERS,
    CodeEditor,
    LineHistory,
    _Step,
    _TOKEN_RE,
    _dim,
    clipboard_get,
    clipboard_put,
    draw_squiggle,
    error_span,
    highlight,
)
from .ui_fonts import (
    COIN_GOLD,
    Button,
    _FONT_CHOICES,
    _font_cache,
    _icon,
    coin_price_parts,
    draw_coins,
    draw_icon_row,
    draw_panel_box,
    draw_text,
    get_font,
    wrap_text,
)
from .ui_icons import (
    IconButton,
    _disc_cache,
    _draw_disc,
    _icon_cache,
    icon_surface,
)


__all__ = [
    "Button", "COIN_GOLD", "coin_price_parts", "draw_coins", "draw_icon_row",
    "draw_panel_box", "draw_text", "get_font", "wrap_text",
    "CodeEditor", "HISTORY_LIMIT", "LineHistory", "STEP_BREAKERS",
    "clipboard_get", "clipboard_put", "draw_squiggle", "error_span",
    "highlight",
    "IconButton", "icon_surface",
    "config", "px", "pygame", "re",
]
