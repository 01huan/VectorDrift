"""World (meters, y up, origin at plot center) <-> screen (pixels) mapping."""

from . import config


class Viewport:
    def __init__(self, rect=config.PLOT_RECT, scale=config.PIXELS_PER_METER):
        self.left, self.top, self.width, self.height = rect
        self.scale = scale
        self.cx = self.left + self.width / 2
        self.cy = self.top + self.height / 2
        self.half_w = self.width / scale / 2
        self.half_h = self.height / scale / 2

    @property
    def rect(self):
        return (self.left, self.top, self.width, self.height)

    def to_screen(self, x, y):
        return (self.cx + x * self.scale, self.cy - y * self.scale)

    def to_world(self, sx, sy):
        return ((sx - self.cx) / self.scale, (self.cy - sy) / self.scale)

    def length(self, meters):
        return meters * self.scale
