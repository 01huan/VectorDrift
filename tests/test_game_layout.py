from vector_drift.scenes import game_layout as gl


def test_stage_constants():
    assert gl.SETUP == "setup"
    assert gl.FLIGHT == "flight"
    assert gl.ARRIVED == "arrived"
    assert gl.PANNING == "panning"


def test_zoom_roundtrip_helpers():
    assert gl.zoom_level(1.0) == 0
    assert gl.level_zoom(0) == 1.0
    assert gl.level_zoom(3) == 0.5
    assert gl.zoom_level(0.5) == 3


def test_ease_in_out_bounds():
    assert gl.ease_in_out(0.0) == 0.0
    assert gl.ease_in_out(1.0) == 1.0
    assert 0.0 < gl.ease_in_out(0.5) < 1.0


def test_pan_offsets_at_endpoints():
    old, new = gl.pan_offsets((2.0, -3.0), 0.0)
    assert old == (-0.0, 0.0)
    assert new == (2.0, -3.0)
    old, new = gl.pan_offsets((2.0, -3.0), 1.0)
    assert old == (-2.0, 3.0)
    assert new == (0.0, 0.0)


def test_fmt_pair_and_clock():
    assert gl.fmt_pair(1.0, 2.5, "m") == "(1.00, 2.50) m"
    assert gl.fmt_pair(float("inf"), 2.5, "m") == "\u2014 m"
    assert gl.fmt_pair("x", 2.5, "m") == "\u2014 m"
    assert gl.fmt_clock(7.34) == "07:34"
    assert gl.fmt_clock(-1.0) == "00:00"


def test_layout_constants_respect_px():
    assert gl.SHIP_BOX.width == gl.px(110)
    assert gl.CONTENT_W == gl.px(320) - 2 * gl.px(20)
    assert gl.RUN_GREEN == (137, 209, 133)
