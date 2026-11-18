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
    assert gl.SHIP_BOX.size == (gl.px(56), gl.px(56))
    assert gl.CONTENT_W == gl.px(320) - 2 * gl.px(20)
    assert gl.RUN_GREEN == (137, 209, 133)


def test_seven_ability_slots_fill_the_panel_content_width():
    rects = gl.ability_slot_rects(7)
    assert [r.size for r in rects] == [(gl.px(34), gl.px(34))] * 7
    assert all(b.x - a.right == gl.px(7) for a, b in zip(rects, rects[1:]))
    assert rects[0].x == gl.px(gl.PAD)
    assert rects[-1].right - rects[0].x == gl.px(gl.CONTENT_W) == gl.px(280)


def test_panel_rows_run_top_to_bottom_without_overlap():
    # ship row, lives / clock, ABILITIES header, slots, then the editor
    assert gl.LEVEL_ROW_Y + 18 <= gl.SHIP_BOX.y / gl.config.UI_SCALE
    assert gl.SHIP_BOX.bottom / gl.config.UI_SCALE < gl.STATUS_Y - 10
    assert gl.STATUS_Y + 14 < gl.ABILITY_LABEL_Y - 5
    assert gl.ABILITY_LABEL_Y + 6 <= gl.ABILITY_SLOTS_Y
    assert gl.ABILITY_SLOTS_Y + gl.ABILITY_SLOT < gl.EDITOR_Y
    assert gl.LEGEND_Y < gl.BUTTONS_Y
