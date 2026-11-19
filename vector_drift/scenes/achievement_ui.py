"""Achievement icons and the Steam-style popup in the bottom-right corner.

Icons are code-drawn per category until a picture exists: drop
assets/images/achievements/<achievement id>.png in and it is used instead.
A tiered achievement's icon gets a frame in its tier's metal (bronze,
silver, gold, platinum).

ToastStack is owned by the SceneManager, so a popup shows over any scene:
it slides up from the bottom edge, stays a few seconds and slides back
down; several unlocks at once stack upward.
"""

import math
from pathlib import Path

import pygame

from .. import config
from ..achievements import ACHIEVEMENTS, FAILURE, MECHANICS, PROGRESS, SKILL, display_name
from ..config import px
from ..image_assets import AssetSpec, load_image, register
from ..ui import draw_text, get_font

SS = 4                                  # icons are drawn this many times larger, then smoothed
CATEGORY_COLORS = {
    PROGRESS: (240, 196, 80),
    SKILL: (90, 220, 240),
    MECHANICS: (170, 130, 255),
    "creation": (120, 210, 130),
    FAILURE: (235, 95, 95),
}
LOCKED_COLOR = (78, 88, 116)
TIER_COLORS = ((205, 127, 70), (196, 206, 222), (246, 204, 70), (150, 236, 246))   # I-IV

for _a in ACHIEVEMENTS:
    register(AssetSpec(f"achievement.{_a.id}", Path(f"achievements/{_a.id}.png")))

_icon_cache = {}


# --- icons -------------------------------------------------------------------------
def _star(c, r):
    return [(c + r * (1 if i % 2 == 0 else 0.45) * math.sin(i * math.pi / 5),
             c - r * (1 if i % 2 == 0 else 0.45) * math.cos(i * math.pi / 5)) for i in range(10)]


def _glyph(surface, category, c, r, color):
    """The category's symbol, centered at (c, c), about ``r`` in radius."""
    if category == PROGRESS:                            # a star
        pygame.draw.polygon(surface, color, _star(c, r))
    elif category == SKILL:                             # a lightning bolt
        pts = [(0.15, -1.0), (-0.55, 0.1), (-0.05, 0.1), (-0.25, 1.0), (0.6, -0.2), (0.08, -0.2), (0.4, -1.0)]
        pygame.draw.polygon(surface, color, [(c + x * r, c + y * r) for x, y in pts])
    elif category == MECHANICS:                         # a ringed planet
        pygame.draw.circle(surface, color, (c, c), r * 0.55)
        ring = pygame.Rect(0, 0, r * 2.0, r * 0.7)
        ring.center = (c, c)
        pygame.draw.ellipse(surface, color, ring, max(2, round(r * 0.14)))
    elif category == FAILURE:                           # a warning sign
        pygame.draw.polygon(surface, color, [(c, c - r), (c + r * 0.95, c + r * 0.75), (c - r * 0.95, c + r * 0.75)])
        bar = pygame.Rect(0, 0, r * 0.2, r * 0.75)
        bar.midtop = (c, c - r * 0.45)
        pygame.draw.rect(surface, (20, 24, 40), bar, border_radius=round(r * 0.08))
        pygame.draw.circle(surface, (20, 24, 40), (c, c + r * 0.5), r * 0.12)
    else:                                               # creation: a flag
        pole = pygame.Rect(0, 0, r * 0.18, r * 1.9)
        pole.midtop = (c - r * 0.55, c - r * 0.95)
        pygame.draw.rect(surface, color, pole)
        pygame.draw.polygon(surface, color, [(c - r * 0.45, c - r * 0.95), (c + r * 0.9, c - r * 0.5),
                                             (c - r * 0.45, c - r * 0.05)])


def _render_icon(achievement, size, locked, hidden, tier=0):
    big = size * SS
    surf = pygame.Surface((big, big), pygame.SRCALPHA)
    color = LOCKED_COLOR if locked else CATEGORY_COLORS.get(achievement.category, config.ACCENT)
    frame = TIER_COLORS[tier - 1] if tier and not locked else color
    bg = tuple(round(v * 0.22) for v in color)
    pygame.draw.rect(surf, (*bg, 255), (0, 0, big, big), border_radius=big // 6)
    width = max(2, big // (12 if tier and not locked else 24))
    pygame.draw.rect(surf, frame, (0, 0, big, big), width=width, border_radius=big // 6)
    c, r = big / 2, big * 0.3
    if hidden:
        font = pygame.font.SysFont("segoeuisemibold,arial", round(big * 0.6), bold=True)
        mark = font.render("?", True, color)
        surf.blit(mark, mark.get_rect(center=(c, c)))
    else:
        _glyph(surf, achievement.category, c, r, color)
    return pygame.transform.smoothscale(surf, (size, size))


def draw_icon(surface, rect, achievement, locked=False, hidden=False, tier=0):
    """The achievement's picture if one exists, else its category icon.

    ``tier`` (1-4) frames a tiered achievement's icon in that tier's metal.
    """
    rect = pygame.Rect(rect)
    img = None if (locked and hidden) else load_image(f"achievement.{achievement.id}", size_px=rect.size)
    if img is not None:
        if locked:
            img = img.copy()
            img.fill((90, 90, 90, 255), special_flags=pygame.BLEND_RGBA_MULT)
        surface.blit(img, img.get_rect(center=rect.center))
        if tier and not locked:
            pygame.draw.rect(surface, TIER_COLORS[tier - 1], rect, width=max(2, rect.w // 12),
                             border_radius=rect.w // 6)
        return
    key = (achievement.id, rect.w, locked, hidden, tier)
    if key not in _icon_cache:
        _icon_cache[key] = _render_icon(achievement, rect.w, locked, hidden, tier)
    surface.blit(_icon_cache[key], rect)


# --- popup -------------------------------------------------------------------------
TOAST_W, TOAST_H, TOAST_GAP, TOAST_MARGIN = 340, 76, 8, 16
NAME_SIZES = (17, 15, 13)               # a long name steps down until it fits
SLIDE_S, HOLD_S = 0.3, 4.0
MAX_SHOWN = 4                           # more unlocks wait their turn
TOAST_BG = (20, 26, 44, 240)


def _ease(x):
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


class ToastStack:
    def __init__(self):
        self.shown = []                 # [[achievement, tier, seconds shown]]
        self.waiting = []               # [(achievement, tier)]

    def push(self, achievement, tier=0):
        self.waiting.append((achievement, tier))
        self._fill()

    def _fill(self):
        while self.waiting and len(self.shown) < MAX_SHOWN:
            self.shown.append([*self.waiting.pop(0), 0.0])

    def update(self, dt):
        for toast in self.shown:
            toast[2] += dt
        self.shown = [t for t in self.shown if t[2] < 2 * SLIDE_S + HOLD_S]
        self._fill()

    def draw(self, surface):
        w, h = px(TOAST_W), px(TOAST_H)
        x = config.WINDOW_W - px(TOAST_MARGIN) - w
        for i, (achievement, tier, t) in enumerate(self.shown):
            rest_y = config.WINDOW_H - px(TOAST_MARGIN) - h - i * (h + px(TOAST_GAP))
            if t < SLIDE_S:
                shown = _ease(t / SLIDE_S)
            elif t > SLIDE_S + HOLD_S:
                shown = 1 - _ease((t - SLIDE_S - HOLD_S) / SLIDE_S)
            else:
                shown = 1.0
            y = round(rest_y + (config.WINDOW_H - rest_y) * (1 - shown))
            card = pygame.Rect(x, y, w, h)
            panel = pygame.Surface(card.size, pygame.SRCALPHA)
            pygame.draw.rect(panel, TOAST_BG, panel.get_rect(), border_radius=px(4))
            surface.blit(panel, card)
            pygame.draw.rect(surface, config.PANEL_EDGE, card, width=max(1, px(1)), border_radius=px(4))
            icon = pygame.Rect(card.x + px(12), card.y + px(12), h - px(24), h - px(24))
            draw_icon(surface, icon, achievement, tier=tier)
            tx = icon.right + px(12)
            draw_text(surface, "ACHIEVEMENT UNLOCKED", (tx, card.y + px(16)), 11, config.TEXT_DIM, kind="bold")
            name = display_name(achievement, tier)
            room = card.right - px(12) - tx
            size = next((s for s in NAME_SIZES if get_font(s, "bold").size(name)[0] <= room), NAME_SIZES[-1])
            draw_text(surface, name, (tx, card.y + px(34)), size, config.TEXT, kind="bold")
