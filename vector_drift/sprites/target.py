"""Target planet sprites."""

import math

import pygame

from .common import SS, OUTLINE, _cached, _shade
from .common import load_image
from ..render import soft_glow


def _render_planet(radius):
    d = 2 * radius + 6
    D = d * SS
    c, r = D / 2, radius * SS
    base, light, dark = (82, 142, 240), (130, 190, 255), (56, 102, 208)

    body = pygame.Surface((D, D), pygame.SRCALPHA)
    body.fill((*base, 255))
    bands = ((-0.55, 0.16, light, 0.0), (-0.12, 0.10, dark, 1.3), (0.30, 0.20, light, 2.1), (0.68, 0.10, dark, 0.6))
    for yf, thick, color, phase in bands:
        top, bottom = [], []
        for i in range(41):
            x = c - r + 2 * r * i / 40
            wave = 0.05 * r * math.sin(i / 40 * 2 * math.pi * 1.5 + phase)
            top.append((x, c + yf * r + wave - thick * r / 2))
            bottom.append((x, c + yf * r + wave + thick * r / 2))
        pygame.draw.polygon(body, color, top + bottom[::-1])
    for fx, fy, fr in ((-0.35, -0.15, 0.13), (0.30, 0.48, 0.09), (0.45, -0.38, 0.07)):
        crater = pygame.Rect(0, 0, 2 * fr * r, 1.6 * fr * r)
        crater.center = (c + fx * r, c + fy * r)
        pygame.draw.ellipse(body, dark, crater)
        pygame.draw.ellipse(body, _shade(dark, 0.8), crater.inflate(-crater.w * 0.35, -crater.h * 0.35))
    shadow = pygame.Surface((D, D), pygame.SRCALPHA)
    pygame.draw.circle(shadow, (8, 16, 60, 120), (c, c), r)
    pygame.draw.circle(shadow, (0, 0, 0, 0), (c - 0.28 * r, c - 0.28 * r), r * 1.12)
    body.blit(shadow, (0, 0))
    shine = pygame.Surface((D, D), pygame.SRCALPHA)
    hl = pygame.Rect(0, 0, 0.62 * r, 0.36 * r)
    hl.center = (c - 0.42 * r, c - 0.52 * r)
    pygame.draw.ellipse(shine, (255, 255, 255, 80), hl)
    pygame.draw.circle(shine, (255, 255, 255, 170), (c - 0.52 * r, c - 0.40 * r), 0.07 * r)
    body.blit(shine, (0, 0))
    mask = pygame.Surface((D, D), pygame.SRCALPHA)
    pygame.draw.circle(mask, (255, 255, 255, 255), (c, c), r)
    body.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    pygame.draw.circle(body, OUTLINE, (c, c), r, max(2, round(0.06 * r)))
    return pygame.transform.smoothscale(body, (d, d))


def _render_glow(radius):
    return soft_glow(radius, (110, 180, 255), max_alpha=210, extent=2.0, power=2.0)


def draw_target(surface, center, radius, t, flash=0.0):
    radius = round(radius)

    img = load_image("target.planet", size_px=(radius * 2, radius * 2))
    if img is not None:
        try:
            surface.blit(img, img.get_rect(center=center))
        except (pygame.error, TypeError, ValueError, OverflowError, MemoryError):
            pass
    else:
        art = _cached(("planet", radius), lambda: _render_planet(radius))
        try:
            surface.blit(art, art.get_rect(center=center))
        except (pygame.error, TypeError, ValueError, OverflowError, MemoryError):
            pass

    glow = _cached(("glow", radius), lambda: _render_glow(radius))
    pulse = 0.5 + 0.5 * math.sin(t * 2.2)
    glow.set_alpha(round(140 + 115 * pulse))
    try:
        surface.blit(glow, glow.get_rect(center=center))
    except (pygame.error, TypeError, ValueError, OverflowError, MemoryError):
        return
    if flash > 0:
        ring = pygame.Surface((radius * 6, radius * 6), pygame.SRCALPHA)
        rc = radius * 3
        pygame.draw.circle(ring, (255, 255, 255, round(150 * flash)), (rc, rc),
                           radius * (1 + 1.5 * (1 - flash)), max(2, radius // 6))
        try:
            surface.blit(ring, ring.get_rect(center=center))
        except (pygame.error, TypeError, ValueError, OverflowError, MemoryError):
            return
