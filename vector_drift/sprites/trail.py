"""Trail and vector sprites."""

import math

import pygame

from .. import config
from .common import draw_smooth_arrow


class TrailLayer:
    def __init__(self, size, color=config.TRAIL, width=2.4, k=None):
        k = k or (3 if config.UI_SCALE < 1.5 else 2)
        self.k = k
        self.color = color
        self.width = width * config.UI_SCALE
        self.big = pygame.Surface((size[0] * k, size[1] * k), pygame.SRCALPHA)
        self.layer = pygame.Surface(size, pygame.SRCALPHA)
        self.bounds = pygame.Rect(0, 0, 0, 0)
        self.last = None

    def clear(self):
        if self.bounds.w and self.bounds.h:
            b, k = self.bounds, self.k
            self.big.fill((0, 0, 0, 0), (b.x * k, b.y * k, b.w * k, b.h * k))
            self.layer.fill((0, 0, 0, 0), b)
        self.bounds = pygame.Rect(0, 0, 0, 0)
        self.last = None

    def draw(self, surface, topleft, alpha=255):
        if self.bounds.w and self.bounds.h:
            try:
                self.layer.set_alpha(alpha)
                surface.blit(self.layer, (topleft[0] + self.bounds.x, topleft[1] + self.bounds.y), self.bounds)
                self.layer.set_alpha(255)
            except (pygame.error, TypeError, ValueError, OverflowError):
                try:
                    self.layer.set_alpha(255)
                except (pygame.error, TypeError, ValueError):
                    pass
                return

    def extend(self, points):
        if not points:
            return
        try:
            clean = []
            for p in points:
                x, y = float(p[0]), float(p[1])
                if math.isfinite(x) and math.isfinite(y):
                    clean.append((x, y))
            if self.last is not None:
                lx, ly = float(self.last[0]), float(self.last[1])
                if not (math.isfinite(lx) and math.isfinite(ly)):
                    self.last = None
            if not clean:
                return
            if self.last is not None:
                dx, dy = clean[0][0] - self.last[0], clean[0][1] - self.last[1]
                if math.hypot(dx, dy) > config.MAX_PX_CULL:
                    self.last = clean[-1]
                    return
        except (TypeError, ValueError, OverflowError):
            return
        k = self.k
        pts = ([self.last] if self.last is not None else []) + clean
        try:
            lw, lh = self.layer.get_size()
        except (pygame.error, TypeError, ValueError):
            return
        cull = config.MAX_PX_CULL
        def _clamp(p):
            return (min(max(p[0], -cull), lw + cull), min(max(p[1], -cull), lh + cull))
        try:
            line_w = max(1, round(self.width * k))
            radius = self.width * k / 2
            if self.last is None:
                c0 = _clamp(pts[0])
                pygame.draw.circle(self.big, self.color, (c0[0] * k, c0[1] * k), radius)
            for a, b in zip(pts, pts[1:]):
                if max(a[0], b[0]) < 0 or min(a[0], b[0]) > lw or max(a[1], b[1]) < 0 or min(a[1], b[1]) > lh:
                    continue
                ca, cb = _clamp(a), _clamp(b)
                pa, pb = (ca[0] * k, ca[1] * k), (cb[0] * k, cb[1] * k)
                pygame.draw.line(self.big, self.color, pa, pb, line_w)
                pygame.draw.circle(self.big, self.color, pb, radius)
        except (pygame.error, TypeError, ValueError, OverflowError, MemoryError):
            self.last = pts[-1]
            return
        self.last = pts[-1]

        margin = self.width + 2
        try:
            x0 = math.floor(min(p[0] for p in pts) - margin)
            y0 = math.floor(min(p[1] for p in pts) - margin)
            x1 = math.ceil(max(p[0] for p in pts) + margin)
            y1 = math.ceil(max(p[1] for p in pts) + margin)
            dirty = pygame.Rect(x0, y0, x1 - x0, y1 - y0).clip(self.layer.get_rect())
        except (TypeError, ValueError, OverflowError):
            return
        if dirty.w <= 0 or dirty.h <= 0:
            return
        try:
            sub = self.big.subsurface((dirty.x * k, dirty.y * k, dirty.w * k, dirty.h * k))
            self.layer.fill((0, 0, 0, 0), dirty)
            self.layer.blit(pygame.transform.smoothscale(sub, dirty.size), dirty.topleft)
        except (pygame.error, TypeError, ValueError, OverflowError, MemoryError):
            return
        self.bounds = self.bounds.union(dirty) if self.bounds.w and self.bounds.h else dirty


def vector_length_px(magnitude, cap=120):
    if magnitude <= 1e-9 or not math.isfinite(magnitude):
        return 0.0
    return min(cap, 26 + 32 * math.log10(1 + magnitude)) * config.UI_SCALE


def draw_vector(surface, start, vec, color):
    try:
        sx, sy = float(start[0]), float(start[1])
        vx, vy = float(vec[0]), float(vec[1])
    except (TypeError, ValueError, OverflowError):
        return
    if not all(math.isfinite(v) for v in (sx, sy, vx, vy)):
        return
    mag = math.hypot(vx, vy)
    length = vector_length_px(mag)
    if length <= 0:
        return
    ux, uy = vx / mag, -vy / mag
    end = (sx + ux * length, sy + uy * length)
    u = config.UI_SCALE
    try:
        draw_smooth_arrow(surface, (sx, sy), end, color, width=2.5 * u, head=9 * u, k=2 if u >= 1.5 else 3)
    except (pygame.error, TypeError, ValueError, OverflowError, MemoryError):
        return
