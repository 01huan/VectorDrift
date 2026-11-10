"""Evaluation of parsed expression nodes.

Also defines :class:`Expression`, the public value object returned by the
parser, because evaluation is the only thing it does.
"""

import math
from dataclasses import dataclass

from .expr_errors import EvaluationError
from .expr_limits import MAX_ABS_RESULT
from .expr_registry import FUNCTIONS


@dataclass(frozen=True)
class Expression:
    """A parsed expression that can be evaluated for any x and y."""

    _node: tuple

    def evaluate(self, x=0.0, y=0.0):
        try:
            result = evaluate_node(self._node, {"x": x, "y": y})
            result = float(result)
        except EvaluationError:
            raise
        except (ArithmeticError, ValueError, TypeError, OverflowError,
                RecursionError, MemoryError) as exc:
            raise EvaluationError(
                f"Cannot evaluate expression: {exc}"
            ) from exc

        if not math.isfinite(result) or abs(result) > MAX_ABS_RESULT:
            raise EvaluationError("Expression produced a non-finite value")

        return result

    __call__ = evaluate


def evaluate_node(node, variables):
    kind = node[0]

    if kind == "num":
        return node[1]

    if kind == "var":
        return variables[node[1]]

    if kind == "neg":
        return -evaluate_node(node[1], variables)

    if kind == "binary":
        op, left, right = node[1], node[2], node[3]
        a = evaluate_node(left, variables)
        b = evaluate_node(right, variables)

        if op == "+":
            return a + b
        if op == "-":
            return a - b
        if op == "*":
            return a * b
        if op == "/":
            if b == 0:
                raise ZeroDivisionError("division by zero")
            return a / b
        if op == "^":
            # Pre-check via log10 so 10^1e9 (OverflowError) and huge-but-finite
            # results (tunneling REACHED + pygame crash) both become diverged.
            try:
                if b == 0:
                    return 1.0
                if a == 0:
                    if b < 0:
                        raise ZeroDivisionError("0.0 cannot be raised to a negative power")
                    return 0.0
                abs_a = abs(a)
                if abs_a == 1.0:
                    if a == 1.0:
                        return 1.0
                    # (-1)^b: only integer exponents are real-valued.
                    if not math.isfinite(b) or b != math.floor(b):
                        raise ValueError("Negative base with non-integer exponent")
                    return 1.0 if int(math.fmod(abs(b), 2.0)) == 0 else -1.0
                if not (math.isfinite(a) and math.isfinite(b)):
                    result = a ** b
                    if not math.isfinite(result) or abs(float(result)) > MAX_ABS_RESULT:
                        raise OverflowError("Result too large")
                    return result
                log10_mag = math.log10(abs_a) * b
            except (ValueError, OverflowError, ZeroDivisionError):
                raise
            if log10_mag > math.log10(MAX_ABS_RESULT):
                raise OverflowError("Result too large")
            if log10_mag < -308:
                return 0.0
            result = a ** b
            if not math.isfinite(result):
                raise OverflowError("Result too large")
            if abs(float(result)) > MAX_ABS_RESULT:
                raise OverflowError("Result too large")
            return result

    if kind == "call":
        name, args = node[1], node[2]
        values = [evaluate_node(arg, variables) for arg in args]
        # Fast-path guard for exp-family: avoid materialising huge-but-finite
        # intermediates (exp(100) ~= 2.6e43) when we will reject them anyway.
        # Other functions rely on the final MAX_ABS_RESULT check in
        # Expression.evaluate(), so e.g. exp(10)/1e6 stays legal.
        if name == "exp" and len(values) == 1:
            try:
                v = float(values[0])
            except (TypeError, ValueError, OverflowError):
                pass
            else:
                if math.isfinite(v) and v > math.log(MAX_ABS_RESULT):
                    raise OverflowError("Result too large")
        return FUNCTIONS[name](*values)

    raise EvaluationError(f"Unknown expression node: {kind}")


# Backward-compatible private alias.
_evaluate = evaluate_node


__all__ = ["Expression", "evaluate_node", "_evaluate"]
