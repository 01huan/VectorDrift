"""Force-field formula templates for the offline solver.

Every template renders to ``(fx_text, fy_text)`` strings that are valid
input for ``expr_parser.parse_expression``.  The parser only knows ``x`` and
``y`` (plus ``pi``/``e`` and math functions), so the target position is
baked into the expression as a numeric constant.

Templates are the *structure* of the force field; PSO searches the numeric
parameters.  Later stages (genetic programming, ...) may add new templates
or search over template structure itself.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable

from ..data import LevelSpec
from ..expr_parser import parse_expression


@dataclass(frozen=True)
class FieldTemplate:
    """A parameterized force-field structure."""

    key: str
    name: str
    param_names: tuple[str, ...]      # names PSO will search
    param_defaults: tuple[float, ...] # default / starting values
    param_bounds: tuple[tuple[float, float], ...]  # (min, max) per param
    render: Callable[[LevelSpec, dict[str, float]], tuple[str, str]]


# ------------------------------------------------------------------ helpers
def _target_constants(level: LevelSpec) -> tuple[float, float]:
    tx, ty = level.target_center
    return float(tx), float(ty)


def _validate(level: LevelSpec, fx_text: str, fy_text: str) -> None:
    """Raise if either expression cannot be parsed by the game's parser."""
    parse_expression(fx_text)
    parse_expression(fy_text)


# ------------------------------------------------------------------ templates
def _render_target_attract(level: LevelSpec,
                           params: dict[str, float]) -> tuple[str, str]:
    """Constant acceleration toward the target.

    Fx = a * (tx - x)     Fy = a * (ty - y)
    Simple, but tends to overshoot; good baseline.
    """
    tx, ty = _target_constants(level)
    a = float(params["a"])
    fx = f"{a:g}*({tx:g} - x)"
    fy = f"{a:g}*({ty:g} - y)"
    _validate(level, fx, fy)
    return fx, fy


def _render_attract_damp(level: LevelSpec,
                         params: dict[str, float]) -> tuple[str, str]:
    """Attraction toward target with distance-dependent damping.

    dist = sqrt((tx-x)^2 + (ty-y)^2)
    Fx = a * (tx - x) / (1 + b * dist)
    Fy = a * (ty - y) / (1 + b * dist)

    Far away: strong pull.  Near the target: weaker pull, reducing overshoot.
    All functions (sqrt, ^) are supported by the parser.
    """
    tx, ty = _target_constants(level)
    a = float(params["a"])
    b = float(params["b"])
    fx = (f"{a:g}*({tx:g} - x)/(1 + {b:g}*sqrt(({tx:g} - x)^2 + ({ty:g} - y)^2))")
    fy = (f"{a:g}*({ty:g} - y)/(1 + {b:g}*sqrt(({tx:g} - x)^2 + ({ty:g} - y)^2))")
    _validate(level, fx, fy)
    return fx, fy


def _render_general_poly(level: LevelSpec,
                         params: dict[str, float]) -> tuple[str, str]:
    """General bivariate quadratic force field (structure-search target).

    Fx = c0 + c1*x + c2*y + c3*x^2 + c4*y^2 + c5*x*y
    Fy = d0 + d1*x + d2*y + d3*x^2 + d4*y^2 + d5*x*y

    12 free parameters; PSO can discover curved, rotating, or saddle fields.
    """
    names = ["c0", "c1", "c2", "c3", "c4", "c5",
             "d0", "d1", "d2", "d3", "d4", "d5"]
    p = [float(params[n]) for n in names]
    (c0, c1, c2, c3, c4, c5,
     d0, d1, d2, d3, d4, d5) = p
    fx = (f"{c0:g} + {c1:g}*x + {c2:g}*y + {c3:g}*x^2 + {c4:g}*y^2 + {c5:g}*x*y")
    fy = (f"{d0:g} + {d1:g}*x + {d2:g}*y + {d3:g}*x^2 + {d4:g}*y^2 + {d5:g}*x*y")
    _validate(level, fx, fy)
    return fx, fy


def _render_swirl_attract(level: LevelSpec,
                          params: dict[str, float]) -> tuple[str, str]:
    """Rotation around the world center plus attraction to target.

    Helps ships curve around obstacles that block the direct line.

    Fx = a*(tx - x) + s*(y - cy)
    Fy = a*(ty - y) - s*(x - cx)
    """
    tx, ty = _target_constants(level)
    cx, cy = 0.0, 0.0  # world center
    a = float(params["a"])
    s = float(params["s"])
    fx = f"{a:g}*({tx:g} - x) + {s:g}*(y - {cy:g})"
    fy = f"{a:g}*({ty:g} - y) - {s:g}*(x - {cx:g})"
    _validate(level, fx, fy)
    return fx, fy




def _render_rich_combo(level: LevelSpec,
                       params: dict[str, float]) -> tuple[str, str]:
    """Rich combination of trig, log, polynomial and cross terms.

    Fx = a*sin(b*x) + c*log(abs(y)+1) + d*x^2 + e*x*y + f*(tx - x)
    Fy = g*sin(h*y) + i*log(abs(x)+1) + j*y^2 + k*x*y + l*(ty - y)

    log(abs(...)+1) is safe at 0 and for negative inputs; the parser
    supports sin, cos, log, ^ and abs.
    """
    tx, ty = _target_constants(level)
    a = float(params["a"]); b = float(params["b"]); c = float(params["c"])
    d = float(params["d"]); e = float(params["e"]); f = float(params["f"])
    g = float(params["g"]); h = float(params["h"]); i = float(params["i"])
    j = float(params["j"]); k = float(params["k"]); l = float(params["l"])
    fx = (f"{a:g}*sin({b:g}*x) + {c:g}*log(abs(y)+1) + {d:g}*x^2 + "
          f"{e:g}*x*y + {f:g}*({tx:g} - x)")
    fy = (f"{g:g}*sin({h:g}*y) + {i:g}*log(abs(x)+1) + {j:g}*y^2 + "
          f"{k:g}*x*y + {l:g}*({ty:g} - y)")
    _validate(level, fx, fy)
    return fx, fy


def _render_trig_poly(level: LevelSpec,
                      params: dict[str, float]) -> tuple[str, str]:
    """Lightweight trig + polynomial field.

    Fx = a*sin(x) + b*cos(y) + c*x^2 + d*x*y + e
    Fy = f*sin(y) + g*cos(x) + h*y^2 + i*x*y + j
    """
    a = float(params["a"]); b = float(params["b"]); c = float(params["c"])
    d = float(params["d"]); e = float(params["e"])
    f = float(params["f"]); g = float(params["g"]); h = float(params["h"])
    i = float(params["i"]); j = float(params["j"])
    fx = (f"{a:g}*sin(x) + {b:g}*cos(y) + {c:g}*x^2 + {d:g}*x*y + {e:g}")
    fy = (f"{f:g}*sin(y) + {g:g}*cos(x) + {h:g}*y^2 + {i:g}*x*y + {j:g}")
    _validate(level, fx, fy)
    return fx, fy

def _render_all_in_one(level: LevelSpec,
                       params: dict[str, float]) -> tuple[str, str]:
    """Combined force field using all existing template structures.

    Combines:
    - Target attraction
    - Distance-dependent damping
    - General quadratic terms
    - Swirl around the world center
    - Trigonometric and polynomial terms
    - Logarithmic nonlinear terms

    PSO optimizes all numeric parameters.
    """
    tx, ty = _target_constants(level)

    # Target attraction and distance damping
    a = float(params["a"])
    b = float(params["b"])

    # Swirl
    s = float(params["s"])

    # General quadratic field: Fx
    c0 = float(params["c0"])
    c1 = float(params["c1"])
    c2 = float(params["c2"])
    c3 = float(params["c3"])
    c4 = float(params["c4"])
    c5 = float(params["c5"])

    # General quadratic field: Fy
    d0 = float(params["d0"])
    d1 = float(params["d1"])
    d2 = float(params["d2"])
    d3 = float(params["d3"])
    d4 = float(params["d4"])
    d5 = float(params["d5"])

    # Trigonometric + polynomial terms
    p1 = float(params["p1"])
    p2 = float(params["p2"])
    p3 = float(params["p3"])
    p4 = float(params["p4"])
    p5 = float(params["p5"])
    p6 = float(params["p6"])
    p7 = float(params["p7"])
    p8 = float(params["p8"])
    p9 = float(params["p9"])
    p10 = float(params["p10"])

    # Rich nonlinear terms
    r1 = float(params["r1"])
    r2 = float(params["r2"])
    r3 = float(params["r3"])
    r4 = float(params["r4"])
    r5 = float(params["r5"])
    r6 = float(params["r6"])
    r7 = float(params["r7"])
    r8 = float(params["r8"])
    r9 = float(params["r9"])
    r10 = float(params["r10"])
    r11 = float(params["r11"])
    r12 = float(params["r12"])

    # Distance to target
    dist = (
        f"sqrt(({tx:g} - x)^2 + ({ty:g} - y)^2)"
    )

    # Attraction with distance-dependent damping
    attract_x = (
        f"{a:g}*({tx:g} - x)/(1 + {b:g}*{dist})"
    )
    attract_y = (
        f"{a:g}*({ty:g} - y)/(1 + {b:g}*{dist})"
    )

    # Swirl around the world center (0, 0)
    swirl_x = f"{s:g}*y"
    swirl_y = f"-({s:g}*x)"

    # General quadratic terms
    poly_x = (
        f"{c0:g} + {c1:g}*x + {c2:g}*y + "
        f"{c3:g}*x^2 + {c4:g}*y^2 + {c5:g}*x*y"
    )
    poly_y = (
        f"{d0:g} + {d1:g}*x + {d2:g}*y + "
        f"{d3:g}*x^2 + {d4:g}*y^2 + {d5:g}*x*y"
    )

    # Trigonometric + polynomial terms
    trig_x = (
        f"{p1:g}*sin(x) + {p2:g}*cos(y) + "
        f"{p3:g}*x^2 + {p4:g}*x*y + {p5:g}"
    )
    trig_y = (
        f"{p6:g}*sin(y) + {p7:g}*cos(x) + "
        f"{p8:g}*y^2 + {p9:g}*x*y + {p10:g}"
    )

    # Rich trig/log/polynomial terms
    rich_x = (
        f"{r1:g}*sin({r2:g}*x) + "
        f"{r3:g}*log(abs(y)+1) + "
        f"{r4:g}*x^2 + {r5:g}*x*y + "
        f"{r6:g}*({tx:g} - x)"
    )
    rich_y = (
        f"{r7:g}*sin({r8:g}*y) + "
        f"{r9:g}*log(abs(x)+1) + "
        f"{r10:g}*y^2 + {r11:g}*x*y + "
        f"{r12:g}*({ty:g} - y)"
    )

    # Combine all components
    fx = (
        f"({attract_x}) + ({swirl_x}) + "
        f"({poly_x}) + ({trig_x}) + ({rich_x})"
    )
    fy = (
        f"({attract_y}) + ({swirl_y}) + "
        f"({poly_y}) + ({trig_y}) + ({rich_y})"
    )

    _validate(level, fx, fy)
    return fx, fy


TEMPLATES: dict[str, FieldTemplate] = {}


def _register(tpl: FieldTemplate) -> FieldTemplate:
    TEMPLATES[tpl.key] = tpl
    return tpl


_register(FieldTemplate(
    key="target_attract",
    name="Target Attraction",
    param_names=("a",),
    param_defaults=(1.0,),
    param_bounds=((0.01, 20.0),),
    render=_render_target_attract,
))

_register(FieldTemplate(
    key="attract_damp",
    name="Attraction + Distance Damping",
    param_names=("a", "b"),
    param_defaults=(1.0, 0.5),
    param_bounds=((0.01, 50.0), (0.0, 5.0)),
    render=_render_attract_damp,
))

_register(FieldTemplate(
    key="general_poly",
    name="General Quadratic Field",
    param_names=("c0", "c1", "c2", "c3", "c4", "c5",
                 "d0", "d1", "d2", "d3", "d4", "d5"),
    param_defaults=(0.0,) * 12,
    param_bounds=((-5.0, 5.0),) * 12,
    render=_render_general_poly,
))

_register(FieldTemplate(
    key="swirl_attract",
    name="Swirl + Attraction",
    param_names=("a", "s"),
    param_defaults=(1.0, 0.5),
    param_bounds=((0.01, 20.0), (-5.0, 5.0)),
    render=_render_swirl_attract,
))
_register(FieldTemplate(
    key="trig_poly",
    name="Trig + Polynomial",
    param_names=("a", "b", "c", "d", "e",
                 "f", "g", "h", "i", "j"),
    param_defaults=(0.5,) * 10,
    param_bounds=((-3.0, 3.0),) * 10,
    render=_render_trig_poly,
))

_register(FieldTemplate(
    key="rich_combo",
    name="Rich Trig/Log/Poly Combo",
    param_names=("a", "b", "c", "d", "e", "f",
                 "g", "h", "i", "j", "k", "l"),
    param_defaults=(0.5,) * 12,
    param_bounds=((-3.0, 3.0),) * 12,
    render=_render_rich_combo,
))

_ALL_IN_ONE_NAMES = (
    "a", "b", "s",
    "c0", "c1", "c2", "c3", "c4", "c5",
    "d0", "d1", "d2", "d3", "d4", "d5",
    "p1", "p2", "p3", "p4", "p5",
    "p6", "p7", "p8", "p9", "p10",
    "r1", "r2", "r3", "r4", "r5", "r6",
    "r7", "r8", "r9", "r10", "r11", "r12",
)

register_all_in_one = FieldTemplate(
    key="all_in_one",
    name="All-in-One Force Field",
    param_names=_ALL_IN_ONE_NAMES,
    param_defaults=(
        1.0, 0.5, 0.0,          # Attraction, damping, swirl
        *([0.0] * 12),          # General quadratic field
        *([0.0] * 10),          # Trig + polynomial field
        *([0.0] * 12),          # Rich nonlinear field
    ),
    param_bounds=(
        (0.01, 20.0),           # a
        (0.0, 5.0),             # b
        (-5.0, 5.0),            # s
        *([(-5.0, 5.0)] * 12),  # Quadratic coefficients
        *([(-3.0, 3.0)] * 10),  # Trig + polynomial coefficients
        *([(-3.0, 3.0)] * 12),  # Rich nonlinear coefficients
    ),
    render=_render_all_in_one,
)

_register(register_all_in_one)


def get_template(key: str) -> FieldTemplate:
    if key not in TEMPLATES:
        raise KeyError(f"Unknown field template: {key}")
    return TEMPLATES[key]


def template_keys() -> tuple[str, ...]:
    return tuple(TEMPLATES)
