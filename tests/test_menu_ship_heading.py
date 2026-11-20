import math

import pytest

from vector_drift.scenes.menu import _orbit_pose

W = 0.35  # orbit angular speed used by the menu


def _angle_diff_deg(a, b):
    d = (a - b + math.pi) % (2 * math.pi) - math.pi
    return abs(math.degrees(d))


@pytest.mark.parametrize("th_deg", [0, 30, 45, 90, 135, 180, 225, 270, 315])
def test_menu_ship_nose_points_along_its_motion(th_deg):
    t = math.radians(th_deg) / W
    dt = 1e-4
    (x0, y0), _ = _orbit_pose(t - dt)
    (x1, y1), _ = _orbit_pose(t + dt)
    _, heading = _orbit_pose(t)
    # Screen y grows downward; flip it to get the math-convention travel angle.
    travel = math.atan2(-(y1 - y0), x1 - x0)
    assert _angle_diff_deg(heading, travel) < 1.0
