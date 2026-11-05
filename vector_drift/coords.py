"""World (meters, y up, origin at plot center) <-> screen (pixels) mapping."""

import math

from . import config


class Viewport:
    """Plot rectangle on screen plus the world scale drawn in it.

    ``zoom`` is the camera zoom: 1 shows the usual map, 0.5 shows twice as
    much world each way. ``scale`` (px per m) and ``half_w`` / ``half_h``
    (visible half extents in m) already include it.
    """

    def __init__(self, rect=config.PLOT_RECT, scale=config.PIXELS_PER_METER, zoom=1.0):
        self.left, self.top, self.width, self.height = rect
        self.base_scale = scale
        self.zoom = zoom
        self.cx = self.left + self.width / 2
        self.cy = self.top + self.height / 2

    @property
    def scale(self):
        return self.base_scale * self.zoom

    @property
    def half_w(self):
        return self.width / self.scale / 2

    @property
    def half_h(self):
        return self.height / self.scale / 2

    @property
    def rect(self):
        return (self.left, self.top, self.width, self.height)

    def to_screen(self, x, y):
        return (self.cx + x * self.scale, self.cy - y * self.scale)

    def to_world(self, sx, sy):
        return ((sx - self.cx) / self.scale, (self.cy - sy) / self.scale)

    def length(self, meters):
        return meters * self.scale


MIN_ZOOM = 1e-9          # only guards against zero; there is no zoom-out limit


def fit_zoom(point, bounds, margin=0.5):
    """Camera zoom that keeps the whole map and ``point`` (the ship) on screen.

    1 while the point is on the map (``bounds``: half width, half height, m).
    Off the map, the largest zoom that still shows the map and the point with
    ``margin`` m to spare, the camera staying centred on the map, however far
    away the point is. The spare room grows from 0 at the map edge to
    ``margin`` a margin past it, so the zoom never jumps. A point that is not
    a finite number gives 1.
    """
    hx, hy = bounds
    x, y = abs(point[0]), abs(point[1])
    if not (math.isfinite(x) and math.isfinite(y)) or (x <= hx and y <= hy):
        return 1.0

    def need(v, half):
        return v + min(margin, v - half) if v > half else half

    zoom = min(hx / need(x, hx), hy / need(y, hy))
    return max(MIN_ZOOM, min(1.0, zoom))
