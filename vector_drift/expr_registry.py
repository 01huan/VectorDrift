"""Built-in constants and functions of the expression language.

The dicts are intentionally module-level and mutable: ``register_function``
extends ``FUNCTIONS`` in place, and the lexer/parser/evaluator all read the
same objects (so tests may patch ``vector_drift.expr_parser.FUNCTIONS``).
"""

import math
import re
from typing import Callable

CONSTANTS = {
    "pi": math.pi,
    "e": math.e,
}

FUNCTIONS: dict[str, Callable] = {
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "asin": math.asin,
    "acos": math.acos,
    "atan": math.atan,
    "sinh": math.sinh,
    "cosh": math.cosh,
    "tanh": math.tanh,
    "exp": math.exp,
    "log": math.log,
    "ln": math.log,
    "log10": math.log10,
    "sqrt": math.sqrt,
    "abs": abs,
    "floor": math.floor,
    "ceil": math.ceil,
    "min": min,
    "max": max,
}

# Validate the argument count for built-in functions.
expected_args = {
    "sin": 1,
    "cos": 1,
    "tan": 1,
    "asin": 1,
    "acos": 1,
    "atan": 1,
    "sinh": 1,
    "cosh": 1,
    "tanh": 1,
    "exp": 1,
    "log": (1, 2),
    "ln": 1,
    "log10": 1,
    "sqrt": 1,
    "abs": 1,
    "floor": 1,
    "ceil": 1,
    "min": 2,
    "max": 2,
}


def register_function(name, function):
    """Register a custom mathematical function.

    Example:
        register_function("cube", lambda value: value ** 3)
        expr = parse_expression("cube(x)")
    """
    if not isinstance(name, str) or not re.fullmatch(
        r"[A-Za-z_][A-Za-z_0-9]*", name
    ):
        raise ValueError("Invalid function name")

    name = name.lower()

    if name in {"x", "y"} or name in CONSTANTS:
        raise ValueError("Function name conflicts with a variable or constant")

    if not callable(function):
        raise TypeError("function must be callable")

    FUNCTIONS[name] = function


__all__ = ["CONSTANTS", "FUNCTIONS", "expected_args", "register_function"]
