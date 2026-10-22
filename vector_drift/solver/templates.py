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


def get_template(key: str) -> FieldTemplate:
    if key not in TEMPLATES:
        raise KeyError(f"Unknown field template: {key}")
    return TEMPLATES[key]


def template_keys() -> tuple[str, ...]:
    return tuple(TEMPLATES)
