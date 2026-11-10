"""Pickup prop sprites."""

import math

import pygame

from .common import SS, OUTLINE, _cached, _paint_cached_prop
from .common import load_image


def _render_shockwave(radius):
    d = 2 * radius + 10
    D = d * SS
    c, r = D / 2, radius * SS
    surf = pygame.Surface((D, D), pygame.SRCALPHA)
    pygame.draw.circle(surf, (38, 42, 58), (c, c), r)
    cap = pygame.Surface((D, D), pygame.SRCALPHA)
    pygame.draw.circle(cap, (92, 100, 130), (c, c), r)
    pygame.draw.circle(cap, (0, 0, 0, 0), (c + 0.22 * r, c + 0.30 * r), r * 1.02)
    surf.blit(cap, (0, 0))
    shine = pygame.Rect(0, 0, 0.36 * r, 0.22 * r)
    shine.center = (c - 0.30 * r, c - 0.38 * r)
    pygame.draw.ellipse(surf, (210, 220, 240), shine)
    cap_w, cap_h = 0.34 * r, 0.20 * r
    cap_rect = pygame.Rect(0, 0, cap_w, cap_h)
    cap_rect.center = (c + 0.10 * r, c - 0.98 * r)
    pygame.draw.rect(surf, (120, 128, 150), cap_rect, border_radius=round(0.06 * r))
    fuse_end = (c + 0.34 * r, c - 1.30 * r)
    pygame.draw.line(surf, (150, 120, 80), cap_rect.midtop, fuse_end, max(2, round(0.07 * r)))
    pygame.draw.circle(surf, (255, 190, 90), fuse_end, 0.16 * r)
    pygame.draw.circle(surf, (255, 240, 200), fuse_end, 0.08 * r)
    pygame.draw.circle(surf, OUTLINE, (c, c), r, max(2, round(0.06 * r)))
    return pygame.transform.smoothscale(surf, (d, d))


def _paint_shockwave(surface, center, radius, t):
    _paint_cached_prop(surface, center, radius, t, "shockwave", _render_shockwave)


def _render_extratime(radius):
    d = 2 * radius + 10
    D = d * SS
    c, r = D / 2, radius * SS
    surf = pygame.Surface((D, D), pygame.SRCALPHA)
    pygame.draw.circle(surf, (38, 58, 42), (c, c), r)
    cap = pygame.Surface((D, D), pygame.SRCALPHA)
    pygame.draw.circle(cap, (92, 130, 100), (c, c), r)
    pygame.draw.circle(cap, (0, 0, 0, 0), (c + 0.22 * r, c + 0.30 * r), r * 1.02)
    surf.blit(cap, (0, 0))
    shine = pygame.Rect(0, 0, 0.36 * r, 0.22 * r)
    shine.center = (c - 0.30 * r, c - 0.38 * r)
    pygame.draw.ellipse(surf, (210, 240, 220), shine)
    plus_size = round(0.5 * r)
    plus_thickness = max(2, round(0.1 * r))
    pygame.draw.line(surf, (255, 255, 255), (c - plus_size // 2, c), (c + plus_size // 2, c), plus_thickness)
    pygame.draw.line(surf, (255, 255, 255), (c, c - plus_size // 2), (c, c + plus_size // 2), plus_thickness)
    pygame.draw.circle(surf, OUTLINE, (c, c), r, max(2, round(0.06 * r)))
    return pygame.transform.smoothscale(surf, (d, d))


def _paint_extratime(surface, center, radius, t):
    _paint_cached_prop(surface, center, radius, t, "extratime", _render_extratime)


def _render_shield_pickup(radius):
    d = 2 * radius + 10
    D = d * SS
    c, r = D / 2, radius * SS
    surf = pygame.Surface((D, D), pygame.SRCALPHA)
    pygame.draw.circle(surf, (130, 90, 220), (c, c), r)
    cap = pygame.Surface((D, D), pygame.SRCALPHA)
    pygame.draw.circle(cap, (170, 130, 255), (c, c), r)
    pygame.draw.circle(cap, (0, 0, 0, 0), (c + 0.22 * r, c + 0.30 * r), r * 1.02)
    surf.blit(cap, (0, 0))
    shine = pygame.Rect(0, 0, 0.36 * r, 0.22 * r)
    shine.center = (c - 0.30 * r, c - 0.38 * r)
    pygame.draw.ellipse(surf, (235, 235, 255), shine)
    line_size = round(0.62 * r)
    line_thickness = max(3, round(0.14 * r))
    pygame.draw.line(surf, (255, 255, 255), (c - line_size // 2, c), (c + line_size // 2, c), line_thickness)
    cap_size = max(2, round(0.09 * r))
    pygame.draw.line(surf, (255, 255, 255), (c - line_size // 2, c - cap_size), (c - line_size // 2, c + cap_size), cap_size)
    pygame.draw.line(surf, (255, 255, 255), (c + line_size // 2, c - cap_size), (c + line_size // 2, c + cap_size), cap_size)
    pygame.draw.circle(surf, OUTLINE, (c, c), r, max(2, round(0.06 * r)))
    return pygame.transform.smoothscale(surf, (d, d))


def _paint_shield(surface, center, radius, t):
    _paint_cached_prop(surface, center, radius, t, "shield-pickup", _render_shield_pickup)


def _render_life(radius):
    d = 2 * radius + 10
    D = d * SS
    c, r = D / 2, radius * SS
    surf = pygame.Surface((D, D), pygame.SRCALPHA)
    pygame.draw.circle(surf, (230, 60, 90), (c, c), r)
    pygame.draw.circle(surf, (255, 180, 200), (c, c), r * 0.6)
    plus = round(0.4 * r)
    thick = max(2, round(0.12 * r))
    pygame.draw.line(surf, (255, 255, 255), (c - plus // 2, c), (c + plus // 2, c), thick)
    pygame.draw.line(surf, (255, 255, 255), (c, c - plus // 2), (c, c + plus // 2), thick)
    pygame.draw.circle(surf, OUTLINE, (c, c), r, max(2, round(0.06 * r)))
    return pygame.transform.smoothscale(surf, (d, d))


def _paint_life(surface, center, radius, t):
    _paint_cached_prop(surface, center, radius, t, "life", _render_life)


def _render_money(radius):
    d = 2 * radius + 10
    D = d * SS
    c, r = D / 2, radius * SS
    surf = pygame.Surface((D, D), pygame.SRCALPHA)
    pygame.draw.circle(surf, (180, 140, 40), (c, c), r)
    pygame.draw.circle(surf, (230, 190, 70), (c, c), r * 0.78)
    shine = pygame.Rect(0, 0, 0.36 * r, 0.22 * r)
    shine.center = (c - 0.30 * r, c - 0.38 * r)
    pygame.draw.ellipse(surf, (255, 230, 140), shine)
    thick = max(2, round(0.12 * r))
    pygame.draw.line(surf, (120, 80, 20), (c, c - 0.4 * r), (c, c + 0.4 * r), thick)
    pygame.draw.arc(surf, (120, 80, 20), (c - 0.25 * r, c - 0.35 * r, 0.5 * r, 0.35 * r), 0, 3.14, thick)
    pygame.draw.arc(surf, (120, 80, 20), (c - 0.25 * r, c, 0.5 * r, 0.35 * r), 3.14, 6.28, thick)
    pygame.draw.circle(surf, OUTLINE, (c, c), r, max(2, round(0.06 * r)))
    return pygame.transform.smoothscale(surf, (d, d))


def _paint_money(surface, center, radius, t):
    _paint_cached_prop(surface, center, radius, t, "money", _render_money)


def _render_unbound(radius):
    d = 2 * radius + 10
    D = d * SS
    c, r = D / 2, radius * SS
    surf = pygame.Surface((D, D), pygame.SRCALPHA)
    pygame.draw.circle(surf, (96, 34, 150), (c, c), r)
    cap = pygame.Surface((D, D), pygame.SRCALPHA)
    pygame.draw.circle(cap, (160, 92, 230), (c, c), r)
    pygame.draw.circle(cap, (0, 0, 0, 0), (c + 0.22 * r, c + 0.30 * r), r * 1.02)
    surf.blit(cap, (0, 0))
    shine = pygame.Rect(0, 0, 0.36 * r, 0.22 * r)
    shine.center = (c - 0.30 * r, c - 0.38 * r)
    pygame.draw.ellipse(surf, (240, 220, 255), shine)
    white = (255, 255, 255)
    thick = max(2, round(0.09 * r))
    half, gap = 0.34 * r, 0.14 * r
    for sx in (-1, 1):
        for sy in (-1, 1):
            corner = (c + sx * half, c + sy * half)
            pygame.draw.line(surf, white, corner, (c + sx * gap, c + sy * half), thick)
            pygame.draw.line(surf, white, corner, (c + sx * half, c + sy * gap), thick)
    head = 0.16 * r
    for ux, uy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        tip = (c + ux * 0.72 * r, c + uy * 0.72 * r)
        base = (c + ux * 0.18 * r, c + uy * 0.18 * r)
        pygame.draw.line(surf, white, base, tip, thick)
        nx, ny = -uy, ux
        pygame.draw.polygon(surf, white, [
            (tip[0] + ux * head * 0.4, tip[1] + uy * head * 0.4),
            (tip[0] - ux * head + nx * head, tip[1] - uy * head + ny * head),
            (tip[0] - ux * head - nx * head, tip[1] - uy * head - ny * head)])
    pygame.draw.circle(surf, OUTLINE, (c, c), r, max(2, round(0.06 * r)))
    return pygame.transform.smoothscale(surf, (d, d))


def _paint_unbound(surface, center, radius, t):
    _paint_cached_prop(surface, center, radius, t, "unbound", _render_unbound)


PICKUP_RENDERERS = {"shockwave": _paint_shockwave, "extratime": _paint_extratime, "shield": _paint_shield, "life": _paint_life, "money": _paint_money,
                    "unbound": _paint_unbound}


def draw_pickup(surface, center, radius, t, kind="shockwave"):
    img = load_image(f"pickup.{kind}", size_px=(radius * 2, radius * 2))
    if img is not None:
        try:
            surface.blit(img, img.get_rect(center=center))
        except (pygame.error, TypeError, ValueError, OverflowError, MemoryError):
            return
        return

    painter = PICKUP_RENDERERS.get(kind)
    if painter is None:
        import logging
        logging.getLogger(__name__).warning("no pickup renderer for kind %r; drawing nothing", kind)
        return
    try:
        painter(surface, center, radius, t)
    except (pygame.error, TypeError, ValueError, OverflowError, MemoryError):
        return


def draw_pickup_burst(surface, center, radius, t, kind, progress, grow=2.0):
    try:
        cx, cy = float(center[0]), float(center[1])
        radius, progress, grow = float(radius), max(0.0, float(progress)), float(grow)
    except (TypeError, ValueError, OverflowError):
        return
    if (progress >= 1.0 or radius <= 1
            or not (math.isfinite(cx) and math.isfinite(cy) and math.isfinite(radius)
                    and math.isfinite(grow))):
        return
    r = round(radius)
    half = r + max(6, r // 2)
    try:
        art = pygame.Surface((2 * half, 2 * half), pygame.SRCALPHA)
        draw_pickup(art, (half, half), r, t, kind=kind)
        img = pygame.transform.rotozoom(art, 0, 1.0 + (grow - 1.0) * progress)
        img.set_alpha(round(255 * (1.0 - progress)))
        surface.blit(img, img.get_rect(center=(cx, cy)))
    except (pygame.error, TypeError, ValueError, OverflowError, MemoryError):
        return
