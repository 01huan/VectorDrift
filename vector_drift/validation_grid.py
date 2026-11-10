"""Coarse occupancy-grid path analysis used by the level validator."""

from __future__ import annotations

import math

from . import config
from .data import SHIPS

_RESOLUTION = 0.12


def _as_discs(obstacles, hull):
    """Normalise obstacles to [(center, radius + hull)] discs.

    Accepts ObstacleSpec objects or (center, radius) pairs.
    """
    discs = []
    for ob in obstacles:
        center = getattr(ob, "center", None)
        radius = getattr(ob, "radius", None)
        if center is None:
            center, radius = ob
        discs.append(((center[0], center[1]), radius + hull))
    return discs


def _inflated(obstacles, hull):
    return _as_discs(obstacles, hull)


def _build_grid(obstacles, resolution=_RESOLUTION):
    """Occupancy grid of the world; True = blocked by an inflated disc."""
    w = int(2 * config.WORLD_HALF_W / resolution) + 1
    h = int(2 * config.WORLD_HALF_H / resolution) + 1
    blocked = bytearray(w * h)
    for (cx, cy), r in obstacles:
        i0 = max(0, int((cx - r + config.WORLD_HALF_W) / resolution) - 1)
        i1 = min(w - 1, int((cx + r + config.WORLD_HALF_W) / resolution) + 1)
        j0 = max(0, int((cy - r + config.WORLD_HALF_H) / resolution) - 1)
        j1 = min(h - 1, int((cy + r + config.WORLD_HALF_H) / resolution) + 1)
        r2 = r * r
        for j in range(j0, j1 + 1):
            cy_cell = -config.WORLD_HALF_H + j * resolution
            dy = cy_cell - cy
            dy2 = dy * dy
            if dy2 > r2:
                continue
            half = math.sqrt(r2 - dy2)
            col0 = max(0, int((cx - half + config.WORLD_HALF_W) / resolution))
            col1 = min(w - 1, int((cx + half + config.WORLD_HALF_W) / resolution))
            row_base = j * w
            for i in range(col0, col1 + 1):
                blocked[row_base + i] = 1
    return blocked, w, h


def _cell(point, resolution=_RESOLUTION):
    i = int((point[0] + config.WORLD_HALF_W) / resolution)
    j = int((point[1] + config.WORLD_HALF_H) / resolution)
    i = max(0, min(int(2 * config.WORLD_HALF_W / resolution), i))
    j = max(0, min(int(2 * config.WORLD_HALF_H / resolution), j))
    return i, j


def _nearest_free(blocked, w, h, cell, max_radius=6):
    if not blocked[cell[1] * w + cell[0]]:
        return cell
    for radius in range(1, max_radius + 1):
        for dj in range(-radius, radius + 1):
            for di in range(-radius, radius + 1):
                if abs(di) != radius and abs(dj) != radius:
                    continue
                i, j = cell[0] + di, cell[1] + dj
                if 0 <= i < w and 0 <= j < h and not blocked[j * w + i]:
                    return (i, j)
    return None


def _astar(blocked, w, h, start, goal):
    """A* over the 8-connected grid. Returns (reachable, cost)."""
    import heapq

    if start is None or goal is None:
        return False, math.inf
    sx, sy = start
    gx, gy = goal
    if blocked[sy * w + sx] or blocked[gy * w + gx]:
        return False, math.inf

    def hfun(i, j):
        dx, dy = abs(i - gx), abs(j - gy)
        return max(dx, dy) + 0.4142 * min(dx, dy)

    start_index = sy * w + sx
    goal_index = gy * w + gx
    g_score = {start_index: 0.0}
    came_from = {}
    heap = [(hfun(sx, sy), 0.0, start_index)]
    closed = bytearray(w * h)
    neighbours = ((1, 0, 1.0), (0, 1, 1.0), (-1, 0, 1.0), (0, -1, 1.0),
                  (1, 1, 1.4142), (1, -1, 1.4142), (-1, 1, 1.4142),
                  (-1, -1, 1.4142))
    while heap:
        _, cost, index = heapq.heappop(heap)
        if closed[index]:
            continue
        closed[index] = 1
        if index == goal_index:
            return True, cost
        i, j = index % w, index // w
        for di, dj, step in neighbours:
            ni, nj = i + di, j + dj
            if not (0 <= ni < w and 0 <= nj < h):
                continue
            n_index = nj * w + ni
            if blocked[n_index] or closed[n_index]:
                continue
            tentative = cost + step
            if tentative < g_score.get(n_index, math.inf):
                g_score[n_index] = tentative
                came_from[n_index] = index
                heapq.heappush(heap,
                               (tentative + hfun(ni, nj), tentative, n_index))
    return False, math.inf


def _reachable(level, obstacles, start, goal, resolution=_RESOLUTION,
               nearest=True):
    hull = SHIPS.get(level.ship_id, SHIPS["ship01"]).hull_radius
    blocked, w, h = _build_grid(_as_discs(obstacles, hull), resolution)
    start_cell = _nearest_free(blocked, w, h, _cell(start, resolution))
    goal_cell = (_nearest_free(blocked, w, h, _cell(goal, resolution))
                 if nearest else _cell(goal, resolution))
    return _astar(blocked, w, h, start_cell, goal_cell)


__all__ = [
    "_RESOLUTION", "_as_discs", "_inflated", "_build_grid", "_cell",
    "_nearest_free", "_astar", "_reachable",
]
