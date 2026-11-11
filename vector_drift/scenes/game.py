"""Game screen: set up the force field, launch, watch the flight."""

import logging
import math
from dataclasses import replace

import pygame

from .. import config, render, sprites
from ..config import px
from ..desktop import set_cursor
from ..background import BackgroundBuilder
from ..coords import Viewport, fit_zoom
from ..data import (SHIPS, custom_level_to_snapshot, default_ship_id, get_level,
                    is_custom_level, level_holes, section_count, section_level, section_shift,
                    ship_unlocked)
from ..expr_parser import diagnose_expression
from ..hints import get_hint
from ..level_presets import is_dynamic_level
from ..physics import Flight, ForceField, Outcome
from ..pickups import EXTRATIME_DURATION, extratime_bonus_steps
from ..image_assets import COIN_BALANCE
from ..ui import (Button, CodeEditor, IconButton, coin_price_parts, draw_coins, draw_icon_row,
                  draw_panel_box, draw_text, icon_surface)
from ..solver import PSOSolver, PSOConfig, Solver, run_solver_async
from ..solver.interface import SolveResult
from .base import Scene, InventoryMixin
from .hint_popup import HintPopup, confirm_text
from .pause_menu import PauseMenu
from . import pickup_effects as pfx
from .game_section_pan import SectionPan
log = logging.getLogger(__name__)

_PHYSICS_ERRORS = (
    ArithmeticError, ValueError, TypeError, OverflowError,
    RecursionError, MemoryError,
)
_RENDER_ERRORS = (
    pygame.error, ValueError, TypeError, OverflowError, MemoryError,
)

# Re-exported for callers/tests that historically imported these names from
# this module. The scene implementation imports them from game_layout.
from .game_layout import (
    ARRIVED, CAMERA_EASE_S, CAMERA_MARGIN_M, CHECKPOINT_LIFE_POP_S,
    CONTENT_W, CX, EDITOR_Y, FLIGHT, HISTORY_ALPHA, LEGEND_LABEL_Y,
    LEGEND_Y, LEVEL_ROW_Y, LOGO_W, LOGO_Y, OUTCOME_TEXT, PAD, PANNING,
    RESPAWN_EVERY_LIFE, RESUME_OUTCOMES, R, RUN_GREEN, SETUP, SHIP_BOX,
    SHIP_LABEL_Y, SHIP_MASS_Y, SHIP_MIN_SCALE, SHIP_NAME_Y,
    START_MARKER_RADIUS_M, STATUS_Y, TELEMETRY_ROW_H, UNBOUND_EDGE,
    ZOOM_LEVELS_AT_LAUNCH, ZOOM_LEVELS_KEPT, ZOOM_LEVELS_PER_HALVING,
    ease_in_out, fmt_clock, fmt_pair, level_zoom, pan_offsets, zoom_level,
)
from .game_core import GameCoreMixin
from .game_flight import GameFlightMixin
from .game_pickups import GamePickupMixin
from .game_update import GameUpdateMixin
from .game_ui import GameUIMixin
from .game_render import GameRenderMixin


class GameScene(InventoryMixin, GameCoreMixin, GameFlightMixin, GamePickupMixin,
               GameUpdateMixin, GameUIMixin, GameRenderMixin, Scene):
    music = "level"
