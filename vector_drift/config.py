"""Global constants: window layout, colors, physics parameters."""

import os
import sys
from pathlib import Path

# --- Paths ---------------------------------------------------------------
ROOT_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = ROOT_DIR / "assets"

# --- Display scale ---------------------------------------------------------
# Layout is designed for 1280x720 "logical" pixels. We tell Windows we handle
# DPI ourselves and draw everything UI_SCALE times larger, so it stays sharp
# instead of being stretched (blurry/pixelated) by the OS.
#
# By default the game runs fullscreen: UI_SCALE is chosen so the 16:9 layout
# fills the screen, and any leftover strip (e.g. on a 16:10 screen) is drawn in
# the background color. Set VECTOR_DRIFT_WINDOWED=1 to run in a window instead.
BASE_W, BASE_H = 1280, 720
HEADLESS = os.environ.get("SDL_VIDEODRIVER") == "dummy"
FULLSCREEN = not HEADLESS and not os.environ.get("VECTOR_DRIFT_WINDOWED")


def _screen_info():
    """(dpi_scale, screen_w, screen_h) in real pixels; makes the process DPI-aware."""
    if sys.platform != "win32" or HEADLESS:
        return 1.0, None, None
    try:
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)     # per-monitor aware
        except (AttributeError, OSError):
            ctypes.windll.user32.SetProcessDPIAware()
        user32 = ctypes.windll.user32
        return user32.GetDpiForSystem() / 96, user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
    except (AttributeError, OSError):
        return 1.0, None, None


def _detect_ui_scale(dpi_scale, screen_w, screen_h):
    override = os.environ.get("VECTOR_DRIFT_SCALE")
    if override:
        return max(0.5, float(override))
    if not screen_w:
        return 1.0
    if FULLSCREEN:
        return min(screen_w / BASE_W, screen_h / BASE_H)
    # Windowed: leave room for the title bar and taskbar.
    fit = min(screen_w * 0.95 / BASE_W, screen_h * 0.88 / BASE_H)
    return max(1.0, min(dpi_scale, fit))


UI_SCALE = _detect_ui_scale(*_screen_info())


def px(value):
    """Logical pixels -> real pixels."""
    return int(round(value * UI_SCALE))


# --- Window & layout -----------------------------------------------------
WINDOW_W, WINDOW_H = px(BASE_W), px(BASE_H)
FPS = 60
TITLE = "Vector Drift"

PANEL_W = px(320)                   # left control panel width
PLOT_RECT = (PANEL_W, 0, WINDOW_W - PANEL_W, WINDOW_H)   # x, y, w, h
PIXELS_PER_METER = 48 * UI_SCALE    # 960 logical px / 20 m

# Visible world range
WORLD_HALF_W = 10.0
WORLD_HALF_H = 7.5

# --- Physics -------------------------------------------------------------
DT = 1.0 / 120.0                    # fixed simulation step (s)
MAX_FRAME_DT = 0.25                 # clamp for long frames (s)

# --- Safety limits (layered defense, see docs) --------------------------------
# Parser(1e12) -> Physics(1e6) -> Render(10000px / 4000px) -> Scene(swallow).
# UI caps typed input at MAX_EXPR_LEN, but pasted text / restored sessions /
# direct API calls can bypass it, so the parser enforces its own backstops.
MAX_EXPR_TEXT_LEN = 5000   # reject any expression text longer than this
MAX_NUMBER_DIGITS = 1000    # max significant digits per numeric literal
MAX_EXPR_RESULT = 1e12    # finite results larger than this are treated as diverged
MAX_FORCE = 1e6           # |F| above this is treated as diverged (physics)
MAX_STEP_M = 50.0         # single-step displacement above this is diverged
MAX_PX_CULL = 10000       # screen-space cull margin for huge-finite coords
MAX_ARROW_PX = 4000       # refuse to allocate arrow temp surfaces larger than this

# --- Costs ---------------------------------------------------------------
AI_SOLVER_COST = 10
HINT_COST = 10
AI_COST = AI_SOLVER_COST
HINT_MONEY_COST = HINT_COST
SOLVER_COST = AI_SOLVER_COST
MONEY_COST_PER_USE = 10

# --- Gameplay ------------------------------------------------------------
MAX_EXPR_LEN = 1000
BANNER_DURATION = 1.8               # life-lost banner (s)
WIN_DELAY = 0.8                     # pause on target before Win screen (s)

# --- Level select ------------------------------------------------------------
# Level numbers shown even before they exist (as "Coming soon" cards).  The
# list always reaches the highest real level id, whichever is larger.
PLANNED_LEVELS = 24

# --- Random levels -----------------------------------------------------------
# All tunables live in level_presets.py (one RandomPreset per dynamic level).
# Tweak difficulty or add a new random level by editing PRESETS only.

# Field arrows: linear length, the largest |F| on screen gets ARROW_MAX_M
ARROW_MAX_M = 0.90                  # longest arrow (m); arrows are 1 m apart

# --- Colors --------------------------------------------------------------
BG = (11, 16, 32)
PANEL_BG = (16, 22, 42)
PANEL_EDGE = (40, 52, 86)
STAR = (200, 210, 235)

GRID_MINOR = (20, 28, 50)
GRID_MAJOR = (32, 44, 74)
AXIS = (92, 112, 160)
TICK_TEXT = (150, 168, 210)

ARROW = (160, 184, 206)             # force-field arrows (single color)
OUTLINE = (14, 18, 38)              # cartoon outline color

TEXT = (225, 232, 248)
TEXT_DIM = (130, 142, 175)
TEXT_FAINT = (80, 92, 125)
ACCENT = (90, 220, 240)
DANGER = (240, 90, 100)
SUCCESS = (110, 230, 150)
WARNING = (255, 190, 90)

FORCE_VEC = (255, 160, 70)
TRAIL = (255, 214, 120)
VELOCITY_VEC = (120, 240, 140)

BUTTON_PRIMARY = (14, 99, 156)
BUTTON_PRIMARY_HOVER = (20, 120, 186)
BUTTON_DANGER = (150, 38, 50)
BUTTON_DANGER_HOVER = (176, 48, 62)
BUTTON_PLAIN = (34, 42, 68)
BUTTON_PLAIN_HOVER = (46, 56, 88)
BUTTON_DISABLED = (26, 32, 50)

# Code editor (VS Code Dark+ inspired)
EDITOR_BG = (13, 17, 31)
EDITOR_TABBAR = (19, 25, 45)
EDITOR_LINE_HL = (25, 32, 58)
EDITOR_BORDER = (44, 56, 92)
EDITOR_GUTTER = (88, 98, 130)
EDITOR_GUTTER_ACTIVE = (200, 210, 235)
EDITOR_CURSOR = (230, 236, 248)
EDITOR_SELECTION = (38, 79, 120)
SYN_KEYWORD = (197, 134, 192)       # Fx / Fy
SYN_NUMBER = (226, 156, 110)
SYN_VARIABLE = (156, 220, 254)
SYN_OPERATOR = (160, 170, 192)
SYN_IDENT = (220, 220, 170)         # unknown names (sin, z, ...)
SYN_PLAIN = (212, 212, 212)
SQUIGGLE = (244, 71, 71)
