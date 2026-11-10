"""Diagnostics and singularity analysis for parsed expressions."""

from .expr_errors import ParseError
from .expr_evaluator import Expression
from .expr_grammar import parse_expression


def diagnose_expression(text):
    """Return (Expression, None, None) or (None, message, position)."""
    try:
        return parse_expression(text), None, None
    except ParseError as exc:
        return None, exc.message, exc.pos


def singular_parts(expression):
    """Sub-expressions whose zeros are where `expression` can be infinite.

    Only a few operations blow up at a finite input: a / b at b = 0, tan(u)
    at cos(u) = 0, log(u) at u = 0 and u ^ (negative) at u = 0. Each such
    argument is split into the factors that reach zero together with it
    (abs(v), v^2, v*w, sqrt(v)), so that 1/x^2 reports x: a zero of x shows
    up as a sign change, a zero of x^2 never would. Anything that isn't an
    Expression has no parts.
    """
    if not isinstance(expression, Expression):
        return ()
    parts = []
    _collect_singular(expression._node, parts)
    return tuple(Expression(node) for node in dict.fromkeys(parts) if node[0] != "num")


def _collect_singular(node, out):
    kind = node[0]
    if kind == "neg":
        _collect_singular(node[1], out)
    elif kind == "binary":
        op, left, right = node[1], node[2], node[3]
        if op == "/":
            out.extend(_zero_factors(right))
        elif op == "^" and not (right[0] == "num" and right[1] >= 0):
            out.extend(_zero_factors(left))
        _collect_singular(left, out)
        _collect_singular(right, out)
    elif kind == "call":
        name, args = node[1], node[2]
        if name == "tan":
            out.append(("call", "cos", args))
        elif name in ("log", "ln", "log10"):
            out.extend(_zero_factors(args[0]))
            if len(args) == 2:      # log(u, base) divides by log(base): base = 1
                out.extend(_zero_factors(("binary", "-", args[1], ("num", 1.0))))
        for arg in args:
            _collect_singular(arg, out)


def _zero_factors(node):
    """Factors of `node` whose zeros are its zeros (abs, sqrt, powers, products)."""
    kind = node[0]
    if kind == "neg":
        return _zero_factors(node[1])
    if kind == "call" and node[1] in ("abs", "sqrt"):
        return _zero_factors(node[2][0])
    if kind == "binary":
        op, left, right = node[1], node[2], node[3]
        if op == "*":
            return _zero_factors(left) + _zero_factors(right)
        if op == "/":
            return _zero_factors(left)
        if op == "^" and right[0] == "num" and right[1] > 0:
            return _zero_factors(left)
    return [node]


__all__ = [
    "diagnose_expression", "singular_parts", "_collect_singular",
    "_zero_factors",
]
