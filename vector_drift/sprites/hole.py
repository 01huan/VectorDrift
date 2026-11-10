"""Hole sprites."""

import math

import pygame

from .. import image_assets


HOLE_SPIN_PERIOD_S = 8.0


def _hole_spin_angle(kind, t):
    direction = 1.0 if kind == "white" else -1.0
    return direction * 360.0 * float(t) / HOLE_SPIN_PERIOD_S


def draw_hole(surface, center, radius, t=0.0, kind="black", pair_index=1):
    try:
        cx, cy = float(center[0]), float(center[1])
        r = max(1.0, float(radius))
    except (TypeError, ValueError, OverflowError):
        return
    try:
        prefix = "black_hole" if kind != "white" else "white_hole"
        size = max(1, int(2 * r))
        for n in (int(pair_index), 1):
            key = f"{prefix}.{prefix}{n:02d}"
            if image_assets.get_spec(key) is None:
                continue
            img = image_assets.load_image(key, size_px=(size, size))
            if img is not None:
                img = pygame.transform.rotozoom(img, _hole_spin_angle(kind, t), 1.0)
                rect = img.get_rect(center=(int(cx), int(cy)))
                surface.blit(img, rect)
                return
    except Exception:
        pass
    try:
        if kind == "white":
            pygame.draw.circle(surface, (240, 240, 255), (int(cx), int(cy)), int(r))
            pygame.draw.circle(surface, (180, 180, 220), (int(cx), int(cy)), int(r), 2)
        else:
            pygame.draw.circle(surface, (10, 10, 20), (int(cx), int(cy)), int(r))
            pygame.draw.circle(surface, (120, 80, 220), (int(cx), int(cy)), int(r), 2)
    except (pygame.error, TypeError, ValueError, OverflowError):
        return


def draw_black_hole(surface, center, radius, t=0.0):
    draw_hole(surface, center, radius, t, kind="black")


def draw_white_hole(surface, center, radius, t=0.0):
    draw_hole(surface, center, radius, t, kind="white")
