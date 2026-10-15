"""Code-drawn cartoon art: ship, target planet, launch pad, trail, vectors.

Each piece is drawn once at SS x resolution with dark outlines, then
smoothscaled down and cached, so edges stay smooth. Swapping in image
sprites later only touches this file.
"""

import math

import pygame

from . import config
from .render import draw_smooth_arrow, soft_glow

SS = 4                      # supersampling factor for cached art
OUTLINE = config.OUTLINE
GLASS = (110, 210, 255)
NOZZLE = (88, 96, 124)

_cache = {}


def _cached(key, build):
    if key not in _cache:
        _cache[key] = build()
    return _cache[key]


def _poly(surface, pts, fill, outline_w):
    """Filled polygon with a rounded-corner outline."""
    pygame.draw.polygon(surface, fill, pts)
    if outline_w > 0:
        pygame.draw.polygon(surface, OUTLINE, pts, outline_w)
        for p in pts:
            pygame.draw.circle(surface, OUTLINE, p, outline_w / 2)


def _shade(color, f):
    return tuple(max(0, min(255, round(c * f))) for c in color)


# --- ship -----------------------------------------------------------------------
def _body_half_width(x):
    """Fuselage half-width at x (ship length = 1, nose at +0.5, tail at -0.42)."""
    if x >= 0.04:
        return 0.15 * math.sqrt(max(0.0, 1 - ((x - 0.04) / 0.46) ** 2))
    return 0.15 * (1 - 0.35 * ((0.04 - x) / 0.46) ** 2)


def _render_ship(length, hull, wing, trim):
    """Ship pointing +x; returns a surface centered on the ship's middle."""
    w, h = math.ceil(length * 1.15) + 4, math.ceil(length * 0.95) + 4
    big = pygame.Surface((w * SS, h * SS), pygame.SRCALPHA)
    S = length * SS
    cx, cy = w * SS / 2, h * SS / 2
    ow = max(2, round(0.035 * S))

    def P(x, y):
        return (cx + x * S, cy - y * S)

    # Wings (both sides) with colored tips
    for sgn in (1, -1):
        wing_pts = [P(0.10, 0.09 * sgn), P(-0.22, 0.40 * sgn), P(-0.36, 0.40 * sgn), P(-0.30, 0.09 * sgn)]
        _poly(big, wing_pts, wing, ow)
        tip = [P(-0.22, 0.40 * sgn), P(-0.36, 0.40 * sgn), P(-0.347, 0.33 * sgn), P(-0.148, 0.33 * sgn)]
        pygame.draw.polygon(big, trim, tip)
        pygame.draw.polygon(big, OUTLINE, wing_pts, ow)

    # Engine nozzle
    _poly(big, [P(-0.40, 0.075), P(-0.49, 0.085), P(-0.49, -0.085), P(-0.40, -0.075)], NOZZLE, ow)

    # Fuselage: light top half, shaded lower half, outline
    xs = [0.5 - i * 0.92 / 40 for i in range(41)]
    upper = [P(x, _body_half_width(x)) for x in xs]
    lower = [P(x, -_body_half_width(x)) for x in reversed(xs)]
    body = upper + lower
    pygame.draw.polygon(big, hull, body)
    shade = [P(x, -_body_half_width(x)) for x in xs] + [P(x, -0.25 * _body_half_width(x)) for x in reversed(xs)]
    pygame.draw.polygon(big, _shade(hull, 0.84), shade)
    shine = [P(x, 0.62 * _body_half_width(x)) for x in xs[8:30]] + \
            [P(x, 0.80 * _body_half_width(x)) for x in reversed(xs[8:30])]
    pygame.draw.polygon(big, (255, 255, 255), shine)
    pygame.draw.polygon(big, OUTLINE, body, ow)

    # Center stripe
    stripe = pygame.Rect(0, 0, 0.34 * S, 0.05 * S)
    stripe.midright = P(-0.04, 0)
    pygame.draw.rect(big, wing, stripe, border_radius=round(0.025 * S))

    # Cockpit bubble with highlight
    cockpit = pygame.Rect(0, 0, 0.26 * S, 0.15 * S)
    cockpit.center = P(0.20, 0)
    pygame.draw.ellipse(big, GLASS, cockpit)
    pygame.draw.ellipse(big, OUTLINE, cockpit, ow)
    glint = pygame.Rect(0, 0, 0.10 * S, 0.045 * S)
    glint.center = P(0.235, 0.03)
    pygame.draw.ellipse(big, (240, 252, 255), glint)

    return pygame.transform.smoothscale(big, (w, h))


def draw_ship(surface, center, heading, size, ship):
    """Draw the ship. `size` = ship length in px, `heading` in world radians."""
    size = max(6, round(size))
    deg = math.degrees(heading)
    img = _cached(("ship", ship.id, size),
                  lambda: _render_ship(size, ship.hull_color, ship.wing_color, ship.trim_color))
    rotated = pygame.transform.rotozoom(img, deg, 1.0)
    surface.blit(rotated, rotated.get_rect(center=center))


def draw_ship_icon(surface, center, size, ship, alive=True):
    """Small upright ship (for the lives counter); grey when the life is used up."""
    def build():
        if alive:
            img = _render_ship(size, ship.hull_color, ship.wing_color, ship.trim_color)
        else:
            img = _render_ship(size, (70, 80, 108), (54, 62, 88), (64, 72, 98))
        return pygame.transform.rotozoom(img, 90, 1.0)
    icon = _cached(("icon", ship.id, size, alive), build)
    surface.blit(icon, icon.get_rect(center=center))


# --- target planet ------------------------------------------------------------------
def _render_planet(radius):
    d = 2 * radius + 6
    D = d * SS
    c, r = D / 2, radius * SS
    base, light, dark = (82, 142, 240), (130, 190, 255), (56, 102, 208)

    body = pygame.Surface((D, D), pygame.SRCALPHA)
    body.fill((*base, 255))
    # Wavy cartoon bands
    bands = ((-0.55, 0.16, light, 0.0), (-0.12, 0.10, dark, 1.3), (0.30, 0.20, light, 2.1), (0.68, 0.10, dark, 0.6))
    for yf, thick, color, phase in bands:
        top, bottom = [], []
        for i in range(41):
            x = c - r + 2 * r * i / 40
            wave = 0.05 * r * math.sin(i / 40 * 2 * math.pi * 1.5 + phase)
            top.append((x, c + yf * r + wave - thick * r / 2))
            bottom.append((x, c + yf * r + wave + thick * r / 2))
        pygame.draw.polygon(body, color, top + bottom[::-1])
    # A couple of craters
    for fx, fy, fr in ((-0.35, -0.15, 0.13), (0.30, 0.48, 0.09), (0.45, -0.38, 0.07)):
        crater = pygame.Rect(0, 0, 2 * fr * r, 1.6 * fr * r)
        crater.center = (c + fx * r, c + fy * r)
        pygame.draw.ellipse(body, dark, crater)
        pygame.draw.ellipse(body, _shade(dark, 0.8), crater.inflate(-crater.w * 0.35, -crater.h * 0.35))
    # Night-side crescent (bottom-right)
    shadow = pygame.Surface((D, D), pygame.SRCALPHA)
    pygame.draw.circle(shadow, (8, 16, 60, 120), (c, c), r)
    pygame.draw.circle(shadow, (0, 0, 0, 0), (c - 0.28 * r, c - 0.28 * r), r * 1.12)
    body.blit(shadow, (0, 0))
    # Highlight
    shine = pygame.Surface((D, D), pygame.SRCALPHA)
    hl = pygame.Rect(0, 0, 0.62 * r, 0.36 * r)
    hl.center = (c - 0.42 * r, c - 0.52 * r)
    pygame.draw.ellipse(shine, (255, 255, 255, 80), hl)
    pygame.draw.circle(shine, (255, 255, 255, 170), (c - 0.52 * r, c - 0.40 * r), 0.07 * r)
    body.blit(shine, (0, 0))
    # Clip to the disc
    mask = pygame.Surface((D, D), pygame.SRCALPHA)
    pygame.draw.circle(mask, (255, 255, 255, 255), (c, c), r)
    body.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    pygame.draw.circle(body, OUTLINE, (c, c), r, max(2, round(0.06 * r)))
    return pygame.transform.smoothscale(body, (d, d))


def _render_glow(radius):
    return soft_glow(radius, (110, 180, 255), max_alpha=210, extent=2.0, power=2.0)


def draw_target(surface, center, radius, t, flash=0.0):
    radius = round(radius)
    planet = _cached(("planet", radius), lambda: _render_planet(radius))
    glow = _cached(("glow", radius), lambda: _render_glow(radius))
    pulse = 0.5 + 0.5 * math.sin(t * 2.2)
    glow.set_alpha(round(140 + 115 * pulse))
    surface.blit(glow, glow.get_rect(center=center))
    surface.blit(planet, planet.get_rect(center=center))
    if flash > 0:
        ring = pygame.Surface((radius * 6, radius * 6), pygame.SRCALPHA)
        rc = radius * 3
        pygame.draw.circle(ring, (255, 255, 255, round(150 * flash)), (rc, rc),
                           radius * (1 + 1.5 * (1 - flash)), max(2, radius // 6))
        surface.blit(ring, ring.get_rect(center=center))


# --- launch pad -----------------------------------------------------------------------
def _render_pad(radius):
    size = 2 * radius + round(8 * config.UI_SCALE)
    big = pygame.Surface((size * SS, size * SS), pygame.SRCALPHA)
    c, r = size * SS / 2, radius * SS
    thick = 1.4 * config.UI_SCALE * SS
    dashes = 12
    for i in range(dashes):
        a0 = i * 2 * math.pi / dashes
        for s in range(13):
            a = a0 + (math.pi / dashes) * s / 12
            pygame.draw.circle(big, (180, 196, 232, 220), (c + r * math.cos(a), c + r * math.sin(a)), thick)
    pygame.draw.circle(big, (180, 196, 232, 200), (c, c), 2.2 * config.UI_SCALE * SS)
    return pygame.transform.smoothscale(big, (size, size))


def draw_start_marker(surface, center, radius, t):
    """Dashed circle slowly rotating around the launch point."""
    pad = _cached(("pad", round(radius)), lambda: _render_pad(round(radius)))
    rotated = pygame.transform.rotozoom(pad, -math.degrees(t * 0.4), 1.0)
    surface.blit(rotated, rotated.get_rect(center=center))


# --- trail & vectors -----------------------------------------------------------------------
class TrailLayer:
    """Smooth, anti-aliased trail that grows incrementally.

    Segments are drawn on a k-times larger surface; only the region touched by
    new segments is downsampled into the visible layer, so it stays cheap.
    Points are in the layer's own pixel coordinates.
    """

    def __init__(self, size, color=config.TRAIL, width=2.4, k=None):
        # Supersampling: high-DPI screens already have plenty of pixels.
        k = k or (3 if config.UI_SCALE < 1.5 else 2)
        self.k = k
        self.color = color
        self.width = width * config.UI_SCALE
        self.big = pygame.Surface((size[0] * k, size[1] * k), pygame.SRCALPHA)
        self.layer = pygame.Surface(size, pygame.SRCALPHA)
        self.bounds = pygame.Rect(0, 0, 0, 0)   # area of `layer` that has content
        self.last = None

    def clear(self):
        if self.bounds.w and self.bounds.h:
            b, k = self.bounds, self.k
            self.big.fill((0, 0, 0, 0), (b.x * k, b.y * k, b.w * k, b.h * k))
            self.layer.fill((0, 0, 0, 0), b)
        self.bounds = pygame.Rect(0, 0, 0, 0)
        self.last = None

    def draw(self, surface, topleft, alpha=255):
        """Blit only the part of the layer that has content."""
        if self.bounds.w and self.bounds.h:
            self.layer.set_alpha(alpha)
            surface.blit(self.layer, (topleft[0] + self.bounds.x, topleft[1] + self.bounds.y), self.bounds)
            self.layer.set_alpha(255)

    def extend(self, points):
        if not points:
            return
        k = self.k
        pts = ([self.last] if self.last is not None else []) + list(points)
        line_w = max(1, round(self.width * k))
        radius = self.width * k / 2
        if self.last is None:
            pygame.draw.circle(self.big, self.color, (pts[0][0] * k, pts[0][1] * k), radius)
        for a, b in zip(pts, pts[1:]):
            pa, pb = (a[0] * k, a[1] * k), (b[0] * k, b[1] * k)
            pygame.draw.line(self.big, self.color, pa, pb, line_w)
            pygame.draw.circle(self.big, self.color, pb, radius)
        self.last = pts[-1]

        margin = self.width + 2
        x0 = math.floor(min(p[0] for p in pts) - margin)
        y0 = math.floor(min(p[1] for p in pts) - margin)
        x1 = math.ceil(max(p[0] for p in pts) + margin)
        y1 = math.ceil(max(p[1] for p in pts) + margin)
        dirty = pygame.Rect(x0, y0, x1 - x0, y1 - y0).clip(self.layer.get_rect())
        if dirty.w <= 0 or dirty.h <= 0:
            return
        sub = self.big.subsurface((dirty.x * k, dirty.y * k, dirty.w * k, dirty.h * k))
        self.layer.fill((0, 0, 0, 0), dirty)
        self.layer.blit(pygame.transform.smoothscale(sub, dirty.size), dirty.topleft)
        self.bounds = self.bounds.union(dirty) if self.bounds.w and self.bounds.h else dirty


def vector_length_px(magnitude, cap=120):
    if magnitude <= 1e-9 or not math.isfinite(magnitude):
        return 0.0
    return min(cap, 26 + 32 * math.log10(1 + magnitude)) * config.UI_SCALE


def draw_vector(surface, start, vec, color):
    """Arrow from `start` (screen) along world vector `vec`, log-scaled length."""
    mag = math.hypot(*vec)
    length = vector_length_px(mag)
    if length <= 0:
        return
    ux, uy = vec[0] / mag, -vec[1] / mag
    end = (start[0] + ux * length, start[1] + uy * length)
    u = config.UI_SCALE
    draw_smooth_arrow(surface, start, end, color, width=2.5 * u, head=9 * u, k=2 if u >= 1.5 else 3)
