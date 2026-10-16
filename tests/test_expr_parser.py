
import math

import pytest

import vector_drift.expr_parser as ep
from vector_drift.expr_parser import (
    Expression,
    EvaluationError,
    LinearExpr,
    ParseError,
    diagnose,
    diagnose_expression,
    parse_expression,
    parse_linear,
    register_function,
    try_parse,
    try_parse_expression,
)


# ============================================================
# General expression parser
# ============================================================

@pytest.mark.parametrize(
    "text, x, y, expected",
    [
        ("", 0, 0, 0),
        ("   ", 0, 0, 0),
        ("42", 0, 0, 42),
        (".5", 0, 0, 0.5),
        ("1.25", 0, 0, 1.25),
        ("x", 3, 4, 3),
        ("y", 3, 4, 4),
        ("X + Y", 3, 4, 7),
        ("2x", 3, 4, 6),
        ("2*x", 3, 4, 6),
        ("2 x", 3, 4, 6),
        ("-x", 3, 4, -3),
        ("+y", 3, 4, 4),
        ("x + y + 1", 3, 4, 8),
        ("x - y", 3, 4, -1),
        ("2x - 3y + 5", 3, 4, -1),
        ("2(x + 1)", 3, 4, 8),
        ("(x + y) * 2", 3, 4, 14),
        ("(x + 1)(y + 1)", 3, 4, 20),
        ("2pi", 0, 0, 2 * math.pi),
        ("2e", 0, 0, 2 * math.e),
        ("pi", 0, 0, math.pi),
        ("e", 0, 0, math.e),
        ("1 / 2", 0, 0, 0.5),
        ("2^3", 0, 0, 8),
        ("2**3", 0, 0, 8),
        ("x^2", 3, 4, 9),
        ("x**2", 3, 4, 9),
        ("-x^2", 3, 4, -9),
        ("(-x)^2", 3, 4, 9),
        ("2^3^2", 0, 0, 512),
        ("x^-2", 2, 0, 0.25),
        ("2 + 3 * 4", 0, 0, 14),
        ("(2 + 3) * 4", 0, 0, 20),
        ("--x", 3, 0, 3),
        ("x + -y", 3, 4, -1),
        ("x - -y", 3, 4, 7),
        ("−x", 3, 0, -3),
    ],
)
def test_parse_expression_evaluate(text, x, y, expected):
    expr = parse_expression(text)

    assert isinstance(expr, Expression)
    assert expr.evaluate(x, y) == pytest.approx(expected)


def test_expression_is_callable():
    expr = parse_expression("2x - y + 1")

    assert expr(3, 4) == pytest.approx(3)
    assert expr.evaluate(x=3, y=4) == pytest.approx(3)


# ============================================================
# Arithmetic precedence and associativity
# ============================================================

@pytest.mark.parametrize(
    "text, expected",
    [
        ("2 + 3 * 4", 14),
        ("(2 + 3) * 4", 20),
        ("2 * 3 + 4", 10),
        ("8 / 4 * 2", 4),
        ("10 - 3 - 2", 5),
        ("2^3^2", 512),
        ("-2^2", -4),
        ("(-2)^2", 4),
        ("2^-2", 0.25),
        ("2**3", 8),
    ],
)
def test_operator_precedence(text, expected):
    assert parse_expression(text).evaluate() == pytest.approx(expected)


# ============================================================
# Built-in functions and constants
# ============================================================

@pytest.mark.parametrize(
    "text, x, y, expected",
    [
        ("sin(x)", math.pi / 2, 0, 1),
        ("cos(x)", 0, 0, 1),
        ("tan(x)", 0, 0, 0),
        ("asin(x)", 1, 0, math.pi / 2),
        ("acos(x)", 1, 0, 0),
        ("atan(x)", 1, 0, math.pi / 4),
        ("sinh(x)", 0, 0, 0),
        ("cosh(x)", 0, 0, 1),
        ("tanh(x)", 0, 0, 0),
        ("exp(x)", 0, 0, 1),
        ("log(x)", 1, 0, 0),
        ("log(8, 2)", 0, 0, 3),
        ("ln(e)", 0, 0, 1),
        ("log10(100)", 0, 0, 2),
        ("sqrt(x)", 9, 0, 3),
        ("abs(y)", 0, -5, 5),
        ("floor(x)", 2.9, 0, 2),
        ("ceil(x)", 2.1, 0, 3),
        ("min(x, y)", 3, 4, 3),
        ("max(x, y)", 3, 4, 4),
        ("sqrt(x^2 + y^2)", 3, 4, 5),
        ("sin(pi / 2)", 0, 0, 1),
        ("2sin(pi / 2)", 0, 0, 2),
    ],
)
def test_builtin_functions(text, x, y, expected):
    expr = parse_expression(text)

    assert expr.evaluate(x, y) == pytest.approx(expected)


# ============================================================
# Syntax errors
# ============================================================

@pytest.mark.parametrize(
    "text, message, pos",
    [
        ("@", "Unexpected character '@'", 0),
        ("x = 1", "Enter only the expression, without '='", 2),
        ("z", "Unknown symbol 'z'", 0),
        ("unknown(x)", "Unknown symbol 'unknown'", 0),
        ("sin()", "Function 'sin' requires at least one argument", 0),
        ("sin(1, 2)", "Invalid number of arguments for 'sin'", 0),
        ("sqrt(1, 2)", "Invalid number of arguments for 'sqrt'", 0),
        ("log()", "Function 'log' requires at least one argument", 0),
        ("min(1)", "Invalid number of arguments for 'min'", 0),
        ("max(1, 2, 3)", "Invalid number of arguments for 'max'", 0),
        ("(x + 1", "Expected ')'", 6),
        ("x + )", "Unexpected token ')'", 4),
        ("2 + * 3", "Unexpected token '*'", 4),
        ("1.2.3", "Invalid number (two decimal points)", 0),
        ("1,5", "Unexpected token ','", 1),
        ("x #", "Unexpected character '#'", 2),
    ],
)
def test_parse_expression_syntax_errors(text, message, pos):
    with pytest.raises(ParseError) as exc_info:
        parse_expression(text)

    assert exc_info.value.message == message
    assert exc_info.value.pos == pos


def test_try_parse_expression_success():
    expr, error = try_parse_expression("x^2 + y^2")

    assert error is None
    assert isinstance(expr, Expression)
    assert expr.evaluate(3, 4) == pytest.approx(25)


@pytest.mark.parametrize(
    "text, message",
    [
        ("z", "Unknown symbol 'z'"),
        ("sin()", "Function 'sin' requires at least one argument"),
        ("x = 1", "Enter only the expression, without '='"),
    ],
)
def test_try_parse_expression_failure(text, message):
    expr, error = try_parse_expression(text)

    assert expr is None
    assert error == message


def test_diagnose_expression_success():
    expr, error, pos = diagnose_expression("x^2 + y^2")

    assert isinstance(expr, Expression)
    assert error is None
    assert pos is None


def test_diagnose_expression_failure():
    expr, error, pos = diagnose_expression("x + )")

    assert expr is None
    assert error == "Unexpected token ')'"
    assert pos == 4


# ============================================================
# Evaluation errors
# ============================================================

@pytest.mark.parametrize(
    "text, x, y",
    [
        ("1 / 0", 0, 0),
        ("1 / (x - 1)", 1, 0),
        ("sqrt(-1)", 0, 0),
        ("log(-1)", 0, 0),
        ("asin(2)", 0, 0),
        ("10^10000 * 10^10000", 0, 0),
        ("10^10000", 0, 0),
    ],
)
def test_evaluation_errors(text, x, y):
    expr = parse_expression(text)

    with pytest.raises(EvaluationError):
        expr.evaluate(x, y)


def test_expression_rejects_non_finite_variable_result():
    expr = parse_expression("x")

    with pytest.raises(EvaluationError, match="non-finite"):
        expr.evaluate(float("inf"), 0)


def test_expression_evaluation_does_not_fail_during_parsing():
    expr = parse_expression("1 / x")

    with pytest.raises(EvaluationError):
        expr.evaluate(0, 0)


# ============================================================
# Legacy linear parser
# ============================================================

@pytest.mark.parametrize(
    "text, expected",
    [
        ("", (0, 0, 0)),
        ("   ", (0, 0, 0)),
        ("2x", (2, 0, 0)),
        ("2*x", (2, 0, 0)),
        ("x", (1, 0, 0)),
        ("-x", (-1, 0, 0)),
        ("+y", (0, 1, 0)),
        ("3 - y", (0, -1, 3)),
        ("y + x + 1", (1, 1, 1)),
        ("2(x + 1)", (2, 0, 2)),
        ("(x + y) * 2", (2, 2, 0)),
        ("x/2", (0.5, 0, 0)),
        ("1/2x", (0.5, 0, 0)),
        ("2x/4", (0.5, 0, 0)),
        ("-3/4 y", (0, -0.75, 0)),
        (".5", (0, 0, 0.5)),
        ("1.5x - 2.25", (1.5, 0, -2.25)),
        ("3/4", (0, 0, 0.75)),
        ("X + Y", (1, 1, 0)),
        ("-0.5x + 2y - 1/3", (-0.5, 2, -1 / 3)),
        ("2−x", (-1, 0, 2)),
        ("x + x", (2, 0, 0)),
        ("y - 2y", (0, -1, 0)),
        ("2 + 3", (0, 0, 5)),
        ("x*2", (2, 0, 0)),
        ("x^1", (1, 0, 0)),
        ("x^0", (0, 0, 1)),
        ("2^3", (0, 0, 8)),
        ("2^-1", (0, 0, 0.5)),
    ],
)
def test_parse_linear_valid(text, expected):
    expr = parse_linear(text)

    assert isinstance(expr, LinearExpr)
    assert (expr.x, expr.y, expr.c) == pytest.approx(expected)


@pytest.mark.parametrize(
    "text, message",
    [
        ("xy", "Unknown symbol 'xy'"),
        ("x*y", "Expression is not linear"),
        ("x y", "Expression is not linear"),
        ("x^2", "Expression is not linear"),
        ("x**2", "Expression is not linear"),
        ("x^y", "Variable exponent is not linear"),
        ("1/x", "Cannot divide by a variable expression"),
        ("1/0", "Division by zero"),
        ("sin(x)", "Functions are not supported by parse_linear()"),
    ],
)
def test_parse_linear_invalid(text, message):
    with pytest.raises(ParseError) as exc_info:
        parse_linear(text)

    assert exc_info.value.message == message


def test_try_parse_success():
    expr, error = try_parse("2x - y + 1")

    assert error is None
    assert expr == LinearExpr(2, -1, 1)


@pytest.mark.parametrize(
    "text, message",
    [
        ("x^2", "Expression is not linear"),
        ("x*y", "Expression is not linear"),
        ("1/x", "Cannot divide by a variable expression"),
    ],
)
def test_try_parse_failure(text, message):
    expr, error = try_parse(text)

    assert expr is None
    assert error == message


def test_diagnose_linear_success():
    assert diagnose("x - 1") == (
        LinearExpr(1, 0, -1),
        None,
        None,
    )


@pytest.mark.parametrize(
    "text, message, pos",
    [
        ("x^2", "Expression is not linear", 0),
        ("x*y", "Expression is not linear", 0),
        ("1/0", "Division by zero", 0),
        ("sin(x)", "Functions are not supported by parse_linear()", 0),
    ],
)
def test_diagnose_linear_failure(text, message, pos):
    expr, error, where = diagnose(text)

    assert expr is None
    assert error == message
    assert where == pos


# ============================================================
# Custom functions
# ============================================================

def test_register_custom_function():
    name = "test_cube_function"

    register_function(name, lambda value: value ** 3)

    try:
        expr = parse_expression(f"{name}(x)")

        assert expr.evaluate(3, 0) == pytest.approx(27)
    finally:
        ep.FUNCTIONS.pop(name, None)


def test_register_function_rejects_invalid_name():
    with pytest.raises(ValueError, match="Invalid function name"):
        register_function("bad-name", lambda x: x)


def test_register_function_rejects_variable_name():
    with pytest.raises(ValueError, match="conflicts"):
        register_function("x", lambda x: x)


def test_register_function_rejects_constant_name():
    with pytest.raises(ValueError, match="conflicts"):
        register_function("pi", lambda x: x)


def test_register_function_requires_callable():
    with pytest.raises(TypeError, match="callable"):
        register_function("not_callable", 123)


# ============================================================
# Numeric overflow and finite results
# ============================================================

def test_parse_linear_rejects_non_finite_coefficients():
    with pytest.raises(ParseError):
        parse_linear("10^10000")


def test_expression_result_is_float():
    expr = parse_expression("2^3")

    assert expr.evaluate() == 8.0
    assert isinstance(expr.evaluate(), float)
