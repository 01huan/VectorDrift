"""Pre-launch check: a formula undefined at the launch point blocks the launch."""
from types import SimpleNamespace

import pytest

from vector_drift.expr_parser import parse_expression
from vector_drift.physics import ForceField
from vector_drift.scenes.base import SceneManager

pytestmark = pytest.mark.usefixtures("pygame_display")


def field(fx, fy):
    return ForceField.from_exprs(parse_expression(fx), parse_expression(fy))


@pytest.mark.parametrize("fx, fy, pos, bad", [
    ("log(x)", "log(x)", (-7.0, 0.0), (0, 1)),
    ("log(x)", "y", (-7.0, 0.0), (0,)),
    ("0", "1/x", (0.0, 0.0), (1,)),
    ("log(x)", "log(x)", (3.0, 0.0), ()),
    ("1000000 * exp(x)", "0", (1.0, 0.0), (0,)),  # finite but above MAX_FORCE
    ("", "", (-7.0, 0.0), ()),
])
def test_invalid_components(fx, fy, pos, bad):
    assert field(fx, fy).invalid_components(*pos) == bad


def test_invalid_components_linear_field():
    assert ForceField(a=1.0, d=2.0).invalid_components(-7.0, 0.0) == ()
    assert ForceField(c=1e7).invalid_components(0.0, 0.0) == (0,)


@pytest.fixture
def scene():
    from vector_drift.scenes.game import GameScene
    audio = SimpleNamespace(play=lambda *a: None, start_loop=lambda *a: None,
                            stop_loop=lambda *a: None)
    manager = SceneManager(audio)
    manager.session.level_id = 1                 # start (-7, 0)
    return GameScene(manager)


def test_undefined_at_start_blocks_launch(scene):
    scene.editor.set_lines(["log(x)", "log(x)"])
    assert not scene.valid
    assert not scene.run_button.enabled
    for msg, _ in scene.editor.errors:
        assert "launch point (-7.00, 0.00)" in msg
    scene._try_launch()
    assert scene.flight is None
    assert scene.attempts == 0
    assert scene.lives == scene.level.lives


def test_only_the_undefined_line_is_flagged(scene):
    scene.editor.set_lines(["log(x)", "y"])
    assert scene.editor.errors[0] is not None
    assert scene.editor.errors[1] is None


def test_fixing_the_formula_clears_the_problem(scene):
    scene.editor.set_lines(["log(x)", "0"])
    scene.editor.set_lines(["log(x + 9)", "0"])
    assert scene.valid
    assert scene.editor.errors == [None, None]
    scene._try_launch()
    assert scene.flight is not None


def test_recheck_when_launch_point_moves_back_to_start(scene):
    scene.launch_pos = (3.0, 0.0)                # e.g. resumed after a timeout
    scene.editor.set_lines(["log(x)", "0"])
    assert scene.valid
    scene._try_launch()
    scene._abort()                               # abort sends the ship back to (-7, 0)
    assert scene.launch_pos == scene.level.start
    assert not scene.valid
    assert "(-7.00, 0.00)" in scene.editor.errors[0][0]
