"""Extensible mathematical expression parser.

Supported:
    2x, 2*x, -x, x/2, 1/2x
    x + y + 1
    (x + y) * 2
    x^2, x**2, -x^2
    sin(x), sqrt(x^2 + y^2), log(x), abs(y)
    pi, e
    Custom functions via register_function()

Variables: x, y
No eval() or arbitrary Python code execution.

The implementation is split into small modules:

* ``expr_registry``  -- constants, built-in functions, register_function
* ``expr_lexer``     -- tokenizer + implicit multiplication
* ``expr_grammar``   -- recursive-descent parser
* ``expr_evaluator`` -- node evaluation + the Expression value object
* ``expr_analysis``  -- diagnostics + singularity analysis
* ``expr_limits`` / ``expr_errors`` -- shared limits and exceptions

This module keeps the historical public import path and re-exports every
name callers used before the split.
"""

from .expr_analysis import (
    _collect_singular,
    _zero_factors,
    diagnose_expression,
    singular_parts,
)
from .expr_errors import EvaluationError, ParseError
from .expr_evaluator import Expression, _evaluate, evaluate_node
from .expr_grammar import Parser, _Parser, parse_expression, try_parse_expression
from .expr_lexer import (
    Token,
    _IDENT_RE,
    _NUMBER_RE,
    _Token,
    _significant_digits,
    _tokenize,
    ends_atom,
    starts_atom,
    tokenize,
)
from .expr_limits import MAX_ABS_RESULT, MAX_NUMBER_DIGITS, MAX_TEXT_LEN
from .expr_registry import (
    CONSTANTS,
    FUNCTIONS,
    expected_args,
    register_function,
)


__all__ = [
    "Expression", "ParseError", "EvaluationError",
    "parse_expression", "try_parse_expression", "diagnose_expression",
    "register_function", "singular_parts",
    "CONSTANTS", "FUNCTIONS", "expected_args",
    "MAX_TEXT_LEN", "MAX_NUMBER_DIGITS", "MAX_ABS_RESULT",
    "Token", "_Token", "tokenize", "_tokenize", "ends_atom", "starts_atom",
    "Parser", "_Parser", "evaluate_node", "_evaluate",
    "_collect_singular", "_zero_factors",
    "_NUMBER_RE", "_IDENT_RE", "_significant_digits",
]
