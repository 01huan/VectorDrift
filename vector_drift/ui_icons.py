"""Icons and icon buttons."""

import pygame

from . import config
from .config import px

# --- icons ----------------------------------------------------------------------------
_icon_cache = {}


def icon_surface(name, size, color):
    """Anti-aliased vector icon (play, stop, grid, chev_left, chev_right, lock)."""
    key = (name, size, color)
    if key in _icon_cache:
        return _icon_cache[key]
    k = 4
    S = size * k
    big = pygame.Surface((S, S), pygame.SRCALPHA)

    def P(x, y):
        return (x * S, y * S)

    def thick_polyline(pts, w):
        pts = [P(*q) for q in pts]
        pygame.draw.lines(big, color, False, pts, max(1, round(w * S)))
        for q in pts:
            pygame.draw.circle(big, color, q, w * S / 2)

    if name == "play":
        pygame.draw.polygon(big, color, [P(0.30, 0.18), P(0.30, 0.82), P(0.82, 0.50)])
    elif name == "stop":
        pygame.draw.rect(big, color, pygame.Rect(P(0.26, 0.26), P(0.48, 0.48)), border_radius=round(0.08 * S))
    elif name == "grid":
        for gx in (0.22, 0.54):
            for gy in (0.22, 0.54):
                pygame.draw.rect(big, color, pygame.Rect(P(gx, gy), P(0.24, 0.24)), border_radius=round(0.05 * S))
    elif name == "chev_left":
        thick_polyline([(0.62, 0.18), (0.34, 0.50), (0.62, 0.82)], 0.11)
    elif name == "chev_right":
        thick_polyline([(0.38, 0.18), (0.66, 0.50), (0.38, 0.82)], 0.11)
    elif name == "lock":
        pygame.draw.circle(big, color, P(0.5, 0.42), 0.20 * S, round(0.08 * S))
        pygame.draw.rect(big, color, pygame.Rect(P(0.24, 0.44), P(0.52, 0.42)), border_radius=round(0.07 * S))
    elif name == "check":
        thick_polyline([(0.22, 0.52), (0.42, 0.72), (0.80, 0.30)], 0.12)
    else:
        raise ValueError(name)
    icon = pygame.transform.smoothscale(big, (size, size))
    _icon_cache[key] = icon
    return icon


class IconButton:
    """Small icon button. style 'circle' = filled round button, 'ghost' = icon only."""

    def __init__(self, rect, icon, style="ghost", color=config.TEXT):
        self.rect = pygame.Rect(rect)
        self.icon = icon
        self.style = style
        self.color = color
        self.enabled = True
        self.hover = False

    def handle_event(self, event):
        """Return 'click', 'disabled' (clicked while disabled) or None."""
        if event.type == pygame.MOUSEMOTION:
            self.hover = self.rect.collidepoint(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                return "click" if self.enabled else "disabled"
        return None

    def draw(self, surface):
        size = min(self.rect.w, self.rect.h)
        if self.style == "circle":
            if self.enabled:
                bg = config.BUTTON_PRIMARY_HOVER if self.hover else config.BUTTON_PRIMARY
            else:
                bg = config.BUTTON_DISABLED
            _draw_disc(surface, self.rect.center, size / 2, bg)
            icon_color = (255, 255, 255) if self.enabled else config.TEXT_FAINT
            icon = icon_surface(self.icon, round(size * 0.62), icon_color)
        else:
            if self.enabled and self.hover:
                pygame.draw.rect(surface, config.EDITOR_LINE_HL, self.rect, border_radius=px(3))
            icon = icon_surface(self.icon, size, self.color if self.enabled else config.TEXT_FAINT)
        surface.blit(icon, icon.get_rect(center=self.rect.center))


_disc_cache = {}


def _draw_disc(surface, center, radius, color):
    """Anti-aliased filled circle."""
    key = (round(radius * 2), color)
    if key not in _disc_cache:
        d = key[0]
        big = pygame.Surface((d * 4, d * 4), pygame.SRCALPHA)
        pygame.draw.circle(big, color, (d * 2, d * 2), d * 2)
        _disc_cache[key] = pygame.transform.smoothscale(big, (d, d))
    disc = _disc_cache[key]
    surface.blit(disc, disc.get_rect(center=center))







__all__ = ['IconButton', '_disc_cache', '_draw_disc', '_icon_cache', 'config', 'icon_surface', 'px', 'pygame']
