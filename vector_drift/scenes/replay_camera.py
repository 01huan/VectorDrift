"""Unbound camera easing for the replay scene (mirrors GameScene)."""

import math

from .. import config
from ..coords import fit_zoom


class ReplayCameraMixin:

    def _camera_target(self):
        """(target_zoom, keep_ship_zoom) for the current frame.

        Mirrors GameScene._camera_target: zooms out while unbound ship is off-map.
        """
        cur = self.player.frame
        if cur is None or not self._unbound:
            return 1.0, 1.0
        pos = (cur.get("x", 0.0), cur.get("y", 0.0))
        # Replay uses the same bounds as the level
        bounds = getattr(self._level, "bounds", None)
        if bounds is None:
            bounds = (config.WORLD_HALF_W, config.WORLD_HALF_H)
        return (fit_zoom(pos, bounds, margin=self._camera_margin_m),
                fit_zoom(pos, bounds, margin=0.5 * self._ship.length))

    def _update_camera(self, dt):
        """Ease the camera zoom toward its target (smooth out and back in).

        Mirrors GameScene._update_camera.
        """
        if self._viewport is None:
            return
        target, keep_ship = self._camera_target()
        zoom = self._viewport.zoom
        if zoom == target:
            return
        zoom += (target - zoom) * (1.0 - math.exp(-dt / self._camera_ease_s))
        zoom = min(zoom, keep_ship)
        self._viewport.zoom = target if abs(target - zoom) < 1e-3 else zoom
