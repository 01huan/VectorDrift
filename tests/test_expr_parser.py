import pytest

from vector_drift.expr_parser import LinearExpr, diagnose, parse_linear, try_parse


@pytest.mark.parametrize("text, expected", [
    ("", (0, 0, 0)),
    ("   ", (0, 0, 0)),
    ("2x", (2, 0, 0)),
    ("2*x", (2, 0, 0)),
    ("x", (1, 0, 0)),
    ("-x", (-1, 0, 0)),
    ("+y", (0, 1, 0)),
    ("3 - y", (0, -1, 3)),
    ("y + x + 1", (1, 1, 1)),
    (" 2 x ", (2, 0, 0)),
    ("x/2", (0.5, 0, 0)),
    ("1/2x", (0.5, 0, 0)),
    ("2x/4", (0.5, 0, 0)),
    ("-3/4 y", (0, -0.75, 0)),
    (".5", (0, 0, 0.5)),
    ("1.5x - 2.25", (1.5, 0, -2.25)),
    ("3/4", (0, 0, 0.75)),
    ("X + Y", (1, 1, 0)),
    ("-0.5x + 2y - 1/3", (-0.5, 2, -1 / 3)),
    ("2−x", (-1, 0, 2)),          # unicode minus
])
def test_valid(text, expected):
    expr = parse_linear(text)
    assert (expr.x, expr.y, expr.c) == pytest.approx(expected)


@pytest.mark.parametrize("text, message", [
    ("x + x", "x appears more than once"),
    ("y - 2y", "y appears more than once"),
    ("2 + 3", "Constant term appears more than once"),
    ("xy", "Products of variables are not supported"),
    ("x*y", "Products of variables are not supported"),
    ("x y", "Products of variables are not supported"),
    ("x^2", "Powers are not supported"),
    ("x**2", "Powers are not supported"),
    ("(x)", "Parentheses are not supported"),
    ("2(x+1)", "Parentheses are not supported"),
    ("sin(x)", "Functions are not supported"),
    ("sqrt x", "Functions are not supported"),
    ("x/0", "Division by zero"),
    ("1/0x", "Division by zero"),
    ("1/x", "Cannot divide by a variable"),
    ("2x+", "Expression ends with an operator"),
    ("-", "Expression ends with an operator"),
    ("2*", "Expression ends with an operator"),
    ("++x", "Two signs in a row"),
    ("x + -y", "Two signs in a row"),
    ("x2", "Put the coefficient before the variable (2x)"),
    ("x*2", "Put the coefficient before the variable (2x)"),
    ("2x 3", "Missing '+' or '-' between terms"),
    ("2 3x", "Missing '+' or '-' between numbers"),
    ("2*3", "Write a single number instead of a product"),
    ("*x", "Unexpected '*'"),
    ("z", "Unknown symbol 'z'"),
    ("1e5", "Scientific notation is not supported"),
    (".", "Invalid number '.'"),
    ("1.2.3", "Invalid number (two decimal points)"),
    ("1,5x", "Use '.' for decimals"),
    ("2x = 1", "Enter only the right-hand side"),
    ("1/2/3", "Only one '/' per coefficient"),
    ("x#", "Unexpected character '#'"),
])
def test_invalid(text, message):
    expr, error = try_parse(text)
    assert expr is None
    assert error == message


def test_try_parse_success_returns_expr():
    expr, error = try_parse("2x - y + 1")
    assert error is None
    assert expr == LinearExpr(2, -1, 1)


@pytest.mark.parametrize("text, pos", [
    ("x^2", 1),
    ("2x + x", 5),
    ("2x+", 3),
    ("sin(x)", 0),
])
def test_diagnose_reports_error_position(text, pos):
    expr, error, where = diagnose(text)
    assert expr is None and error
    assert where == pos


def test_diagnose_ok():
    assert diagnose("x - 1") == (LinearExpr(1, 0, -1), None, None)
