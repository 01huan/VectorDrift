"""Static plot layers: space background, Desmos-style grid, force-field arrows, legend.

Everything with curved or diagonal edges is drawn at a higher resolution and
smoothscaled down, so edges stay soft instead of pixelated.
"""

import math
import random

import numpy as np
import pygame

from . import config
from .config import px
from .ui import get_font

# Arrow layer is drawn at this multiple and smoothscaled down for anti-aliasing;
# on high-DPI screens the real resolution is already high, so less is needed.
SUPERSAMPLE = 2 if config.UI_SCALE < 1.5 else 1.5
ARROW_SPACING_M = 1.0


def _lerp(c0, c1, t):
    return tuple(round(a + (b - a) * t) for a, b in zip(c0, c1))


# --- arrow geometry -----------------------------------------------------------
def arrow_polygon(start, end, width, head, head_width=None):
    """One polygon (shaft + head) for an arrow from start to end."""
    x0, y0 = start
    x1, y1 = end
    dx, dy = x1 - x0, y1 - y0
    length = math.hypot(dx, dy)
    if length < 1e-6:
        return None
    ux, uy = dx / length, dy / length
    nx, ny = -uy, ux
    head = min(head, length * 0.7)
    bx, by = x1 - ux * head, y1 - uy * head
    hw = width / 2
    hh = head_width / 2 if head_width else max(width * 1.2, head * 0.6)
    return [
        (x0 + nx * hw, y0 + ny * hw), (bx + nx * hw, by + ny * hw), (bx + nx * hh, by + ny * hh),
        (x1, y1),
        (bx - nx * hh, by - ny * hh), (bx - nx * hw, by - ny * hw), (x0 - nx * hw, y0 - ny * hw),
    ]


def draw_arrow(surface, start, end, color, width=2, head=7, head_width=None):
    pts = arrow_polygon(start, end, width, head, head_width)
    if pts:
        pygame.draw.polygon(surface, color, pts)


def draw_smooth_arrow(surface, start, end, color, width=3, head=10, outline=None, k=3):
    """Anti-aliased arrow drawn through a small supersampled surface."""
    pad = head + width + 4
    left = math.floor(min(start[0], end[0]) - pad)
    top = math.floor(min(start[1], end[1]) - pad)
    w = math.ceil(abs(end[0] - start[0]) + 2 * pad) + 1
    h = math.ceil(abs(end[1] - start[1]) + 2 * pad) + 1
    big = pygame.Surface((w * k, h * k), pygame.SRCALPHA)
    s0 = ((start[0] - left) * k, (start[1] - top) * k)
    s1 = ((end[0] - left) * k, (end[1] - top) * k)
    if outline:
        pts = arrow_polygon(s0, s1, (width + 3) * k, (head + 3) * k)
        if pts:
            pygame.draw.polygon(big, outline, pts)
            pygame.draw.circle(big, outline, s0, (width + 3) * k / 2)
    draw_arrow(big, s0, s1, color, width * k, head * k)
    surface.blit(pygame.transform.smoothscale(big, (w, h)), (left, top))


# --- space background -----------------------------------------------------------
_star_sprites = {}


def _star_sprite(radius, sparkle=False):
    key = (radius, sparkle)
    if key in _star_sprites:
        return _star_sprites[key]
    k = 4
    size = int(math.ceil(radius * 6)) + 2
    big = pygame.Surface((size * k, size * k), pygame.SRCALPHA)
    c = size * k / 2
    for i in range(10):
        f = i / 9
        r = radius * k * (2.6 - 1.6 * f)
        alpha = round(18 + 237 * f ** 2.2)
        pygame.draw.circle(big, (*config.STAR, alpha), (c, c), r)
    if sparkle:
        arm = radius * k * 3
        for dx, dy in ((1, 0), (0, 1)):
            pygame.draw.polygon(big, (*config.STAR, 200), [
                (c - dx * arm, c - dy * arm), (c + dy * k, c + dx * k),
                (c + dx * arm, c + dy * arm), (c - dy * k, c - dx * k)])
    sprite = pygame.transform.smoothscale(big, (size, size))
    _star_sprites[key] = sprite
    return sprite


def soft_glow(radius, color, max_alpha=255, extent=2.0, power=2.2):
    """Smooth radial glow (alpha falls off from the center) reaching radius*extent."""
    size = max(2, int(2 * radius * extent))
    c = (size - 1) / 2
    yy, xx = np.mgrid[0:size, 0:size]
    d = np.hypot(xx - c, yy - c) / (radius * extent)
    alpha = np.clip(1.0 - d, 0.0, 1.0) ** power * max_alpha
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    surf.fill((*color, 0))
    pygame.surfarray.pixels_alpha(surf)[:] = alpha.T.astype(np.uint8)
    return surf


def make_space_background(size, seed=7, star_count=150):
    """Vertical gradient + soft gaussian nebula clouds + soft round stars."""
    w, h = size
    rng = random.Random(seed)

    # Gradient + nebula computed at quarter resolution, then smoothscaled up.
    sw, sh = max(1, w // 4), max(1, h // 4)
    yy, xx = np.mgrid[0:sh, 0:sw].astype(np.float32)
    top, bottom = np.array((16, 22, 50), np.float32), np.array((7, 10, 26), np.float32)
    img = top + (bottom - top) * (yy / max(1, sh - 1))[..., None]
    palette = [(110, 70, 190), (40, 130, 170), (170, 70, 150), (60, 90, 200)]
    for _ in range(7):
        color = np.array(rng.choice(palette), np.float32)
        cx, cy = rng.uniform(0, sw), rng.uniform(0, sh)
        sigma = rng.uniform(0.10, 0.22) * sh
        strength = rng.uniform(0.18, 0.32)
        blob = np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * sigma ** 2))
        img += (color - img) * (blob * strength)[..., None]
    small = pygame.surfarray.make_surface(np.clip(img, 0, 255).astype(np.uint8).transpose(1, 0, 2))
    surf = pygame.transform.smoothscale(small, size)

    for _ in range(star_count):
        x, y = rng.uniform(0, w), rng.uniform(0, h)
        roll = rng.random()
        if roll < 0.03:
            sprite = _star_sprite(1.6 * config.UI_SCALE, sparkle=True)
        elif roll < 0.18:
            sprite = _star_sprite(1.3 * config.UI_SCALE)
        else:
            sprite = _star_sprite(0.8 * config.UI_SCALE)
        sprite = sprite.copy()
        sprite.set_alpha(rng.randint(110, 255))
        surf.blit(sprite, sprite.get_rect(center=(x, y)))
    return surf


# --- grid ---------------------------------------------------------------------
def make_plot_background(viewport):
    """Space background + translucent minor/major grid + axes, sized to the plot."""
    w, h = viewport.width, viewport.height
    surf = make_space_background((w, h), seed=11, star_count=170)
    grid = pygame.Surface((w, h), pygame.SRCALPHA)
    ox, oy = viewport.left, viewport.top
    s = viewport.scale

    def sx(x):
        return round(viewport.cx - ox + x * s)

    def sy(y):
        return round(viewport.cy - oy - y * s)

    max_x = int(viewport.half_w) + 1
    max_y = int(viewport.half_h) + 1
    minor, major, axis = (130, 160, 230, 22), (130, 160, 230, 52), (180, 200, 245, 170)

    for i in range(-max_x * 5, max_x * 5 + 1):
        if i % 5:
            pygame.draw.line(grid, minor, (sx(i / 5), 0), (sx(i / 5), h))
    for j in range(-max_y * 5, max_y * 5 + 1):
        if j % 5:
            pygame.draw.line(grid, minor, (0, sy(j / 5)), (w, sy(j / 5)))
    for i in range(-max_x, max_x + 1):
        pygame.draw.line(grid, major, (sx(i), 0), (sx(i), h))
    for j in range(-max_y, max_y + 1):
        pygame.draw.line(grid, major, (0, sy(j)), (w, sy(j)))
    axis_w = max(2, px(1.5))
    pygame.draw.line(grid, axis, (sx(0), 0), (sx(0), h), axis_w)
    pygame.draw.line(grid, axis, (0, sy(0)), (w, sy(0)), axis_w)
    surf.blit(grid, (0, 0))
    return surf


def make_plot_labels(viewport):
    """Tick labels on a transparent layer, drawn above the arrow field."""
    w, h = viewport.width, viewport.height
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    ox, oy = viewport.left, viewport.top
    s = viewport.scale

    def sx(x):
        return round(viewport.cx - ox + x * s)

    def sy(y):
        return round(viewport.cy - oy - y * s)

    def label(text, pos, anchor):
        img = get_font(13).render(text, True, config.TICK_TEXT)
        rect = img.get_rect(**{anchor: pos})
        pygame.draw.rect(surf, (*config.BG, 200), rect.inflate(px(6), 0), border_radius=px(4))
        surf.blit(img, rect)

    max_x = int(viewport.half_w) + 1
    max_y = int(viewport.half_h) + 1
    tick, tick_w = px(4), max(2, px(1.5))
    for i in range(-max_x, max_x + 1):
        if i and i % 2 == 0 and abs(i) < viewport.half_w:
            pygame.draw.line(surf, config.AXIS, (sx(i), sy(0) - tick), (sx(i), sy(0) + tick), tick_w)
            label(str(i), (sx(i), sy(0) + px(7)), "midtop")
    for j in range(-max_y, max_y + 1):
        if j and j % 2 == 0 and abs(j) < viewport.half_h:
            pygame.draw.line(surf, config.AXIS, (sx(0) - tick, sy(j)), (sx(0) + tick, sy(j)), tick_w)
            label(str(j), (sx(0) - px(8), sy(j)), "midright")
    label("0", (sx(0) - px(6), sy(0) + px(6)), "topright")
    label("x (m)", (w - px(8), sy(0) - px(6)), "bottomright")
    label("y (m)", (sx(0) + px(8), px(6)), "topleft")
    return surf


# --- arrows -------------------------------------------------------------------
def field_samples(viewport, field):
    """Sample points (cell centers, 1 m apart) with the force at each."""
    nx = int(viewport.half_w / ARROW_SPACING_M + 1e-6)
    ny = int(viewport.half_h / ARROW_SPACING_M + 1e-6)
    samples = []
    for i in range(-nx, nx):
        x = (i + 0.5) * ARROW_SPACING_M
        for j in range(-ny, ny):
            y = (j + 0.5) * ARROW_SPACING_M
            samples.append((x, y, *field.at(x, y)))
    return samples


def field_arrow_shape(length_px):
    """(shaft width, head length, head width) in px for a thin, formal field arrow."""
    u = config.UI_SCALE
    head = max(2.5 * u, min(6.5 * u, 0.32 * length_px))
    return 1.3 * u, head, head * 0.85


def make_field_layer(viewport, field):
    """Arrow field as a transparent plot-sized surface, plus the largest |F| shown.

    All arrows share one color. Length is linear in |F|, scaled so the largest
    force on screen gets the longest arrow (like a quiver plot).
    """
    k = SUPERSAMPLE
    w, h = viewport.width, viewport.height
    big = pygame.Surface((round(w * k), round(h * k)), pygame.SRCALPHA)
    s = viewport.scale
    cx, cy = w * k / 2, h * k / 2
    color = (*config.ARROW, 235)
    dot = 1.3 * config.UI_SCALE * k

    samples = field_samples(viewport, field)
    mags = [math.hypot(fx, fy) for _, _, fx, fy in samples]
    finite = [m for m in mags if math.isfinite(m)]
    max_mag = max(finite) if finite else 0.0
    max_len_px = config.ARROW_MAX_M * s

    for (x, y, fx, fy), mag in zip(samples, mags):
        qx, qy = cx + x * s * k, cy - y * s * k
        if max_mag <= 1e-12 or not math.isfinite(mag):
            pygame.draw.circle(big, color, (qx, qy), dot)
            continue
        length = max_len_px * mag / max_mag
        if length < 2.5 * config.UI_SCALE:
            pygame.draw.circle(big, color, (qx, qy), dot * 0.85)
            continue
        width, head, head_w = field_arrow_shape(length)
        ux, uy = fx / mag, -fy / mag
        half = length * k / 2
        draw_arrow(big, (qx - ux * half, qy - uy * half), (qx + ux * half, qy + uy * half),
                   color, width * k, head * k, head_w * k)
    return pygame.transform.smoothscale(big, (w, h)), max_mag


def format_force(value):
    if value >= 1000:
        return f"{value:,.0f} N"
    if value >= 10:
        return f"{value:.1f} N"
    return f"{value:.3g} N"


def draw_legend(surface, center, max_mag):
    """A full-length sample arrow followed by '= <largest |F| on screen>', centered on `center`."""
    length = config.ARROW_MAX_M * config.PIXELS_PER_METER
    width, head, head_w = field_arrow_shape(length)
    k = 3
    pad, img_h = px(4), px(16)
    big = pygame.Surface(((round(length) + 2 * pad) * k, img_h * k), pygame.SRCALPHA)
    draw_arrow(big, (pad * k, img_h * k / 2), ((pad + length) * k, img_h * k / 2), (*config.ARROW, 235),
               width * k, head * k, head_w * k)
    arrow = pygame.transform.smoothscale(big, (round(length) + 2 * pad, img_h))
    value = format_force(max_mag) if max_mag > 0 else "0 N"
    text = get_font(14, "mono").render(f"= {value}", True, config.TEXT)
    gap = px(6)
    left = center[0] - (arrow.get_width() + gap + text.get_width()) // 2
    surface.blit(arrow, arrow.get_rect(midleft=(left, center[1])))
    surface.blit(text, text.get_rect(midleft=(left + arrow.get_width() + gap, center[1])))
