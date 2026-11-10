"""Ship sprites."""

import math

import pygame

from .. import config
from .common import (SS, OUTLINE, GLASS, NOZZLE, _cached, _poly, _shade)
from .common import load_image

# Hull, wing and trim of the code-drawn grey rocket that marks a used life.
USED_LIFE_COLORS = ((70, 80, 108), (54, 62, 88), (64, 72, 98))
# Mean brightness (0-255) of that rocket's opaque pixels; a ship picture's
# used-life icon is dimmed to match.
USED_LIFE_BRIGHTNESS = 63


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


def draw_ship(surface, center, heading, size, ship, grey=False):
    try:
        cx, cy = float(center[0]), float(center[1])
        heading = float(heading)
    except (TypeError, ValueError, OverflowError):
        return
    if not (math.isfinite(cx) and math.isfinite(cy) and math.isfinite(heading)):
        return
    try:
        sw, sh = surface.get_size()
    except (pygame.error, TypeError, ValueError):
        return
    cull = config.MAX_PX_CULL
    if cx < -cull or cx > sw + cull or cy < -cull or cy > sh + cull:
        return
    center = (cx, cy)
    size = max(6, round(size))
    deg = math.degrees(heading)

    img = load_image(f"ship.{ship.id}", size_px=(size, size))
    if img is not None:
        if grey:
            picture = img
            img = _cached(("ship-grey", picture), lambda: _used_life_image(picture))
        try:
            rotated = pygame.transform.rotozoom(img, deg, 1.0)
            surface.blit(rotated, rotated.get_rect(center=center))
        except (pygame.error, TypeError, ValueError, OverflowError, MemoryError):
            return
        return

    colors = (USED_LIFE_COLORS if grey
              else (ship.hull_color, ship.wing_color, ship.trim_color))
    img = _cached(("ship", ship.id, size, grey), lambda: _render_ship(size, *colors))
    try:
        rotated = pygame.transform.rotozoom(img, deg, 1.0)
        surface.blit(rotated, rotated.get_rect(center=center))
    except (pygame.error, TypeError, ValueError, OverflowError, MemoryError):
        return


def _used_life_image(img):
    grey = pygame.transform.grayscale(img)
    level = pygame.surfarray.array3d(grey)[..., 0]
    opaque = pygame.surfarray.array_alpha(grey) > 128
    mean = float(level[opaque].mean()) if opaque.any() else 0.0
    if mean > USED_LIFE_BRIGHTNESS:
        k = round(256 * USED_LIFE_BRIGHTNESS / mean)
        grey.fill((k, k, k), special_flags=pygame.BLEND_RGB_MULT)
    return grey


def draw_ship_icon(surface, center, size, ship, alive=True):
    try:
        icon = ship_icon_surface(ship, size, alive)
        surface.blit(icon, icon.get_rect(center=center))
    except (pygame.error, TypeError, ValueError, OverflowError, MemoryError):
        return


def ship_icon_surface(ship, size, alive=True):
    img = load_image(f"ship.{ship.id}", size_px=(size, size))
    if img is not None:
        return _cached(("icon-image", img, alive), lambda: pygame.transform.rotozoom(
            img if alive else _used_life_image(img), 90, 1.0))

    def build():
        if alive:
            img = _render_ship(size, ship.hull_color, ship.wing_color, ship.trim_color)
        else:
            img = _render_ship(size, *USED_LIFE_COLORS)
        return pygame.transform.rotozoom(img, 90, 1.0)
    return _cached(("icon", ship.id, size, alive), build)
