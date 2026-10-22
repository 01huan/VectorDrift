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
"""
import math
import re
from dataclasses import dataclass
from typing import Callable

from . import config


_NUMBER_RE = re.compile(r"(?:\d+(?:\.\d*)?|\.\d+)")
_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z_0-9]*")

# --- safety limits (DoS / huge-finite-value guards) ---------------------------
# Canonical values live in config.py; these aliases stay for backward compat.
# Parser-level backstop: UI caps input at config.MAX_EXPR_LEN, but pasted text,
# restored sessions, or direct API calls can bypass it. These limits make the
# parser itself safe.
MAX_TEXT_LEN = config.MAX_EXPR_TEXT_LEN
MAX_NUMBER_DIGITS = config.MAX_NUMBER_DIGITS
MAX_ABS_RESULT = config.MAX_EXPR_RESULT


def _significant_digits(raw: str) -> int:
    """Count significant digits so tiny fractions aren't mis-killed.

    e.g. ``0.00000000000000000001`` has 20 chars but a single significant
    digit (1e-20) and must be accepted; ``999...9`` (20 nines) stays rejected
    via the magnitude check.
    """
    s = raw.replace(".", "").lstrip("0")
    if not s:
        return 1  # literal is zero
    # Strip exponent suffix if a future _NUMBER_RE ever captures one.
    for sep in ("e", "E"):
        if sep in raw:
            s = s.split(sep)[0].lstrip("0") or "1"
            break
    return len(s)

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


class ParseError(ValueError):
    """An expression has invalid syntax."""

    def __init__(self, message, pos=0):
        super().__init__(message)
        self.message = message
        self.pos = pos


class EvaluationError(ValueError):
    """A valid expression could not be evaluated."""


@dataclass(frozen=True)
class _Token:
    kind: str
    value: object
    pos: int


@dataclass(frozen=True)
class LinearExpr:
    """Legacy linear expression: x coefficient, y coefficient, constant."""

    x: float = 0.0
    y: float = 0.0
    c: float = 0.0


@dataclass(frozen=True)
class Expression:
    """A parsed expression that can be evaluated for any x and y."""

    _node: tuple

    def evaluate(self, x=0.0, y=0.0):
        try:
            result = _evaluate(self._node, {"x": x, "y": y})
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


def _tokenize(text):
    tokens = []
    i = 0
    n = len(text)

    while i < n:
        ch = text[i]

        if ch.isspace():
            i += 1
            continue

        if ch.isdigit() or ch == ".":
            match = _NUMBER_RE.match(text, i)
            if not match:
                raise ParseError("Invalid number", i)

            end = match.end()
            if end < n and text[end] == ".":
                raise ParseError("Invalid number (two decimal points)", i)

            raw = match.group()
            if _significant_digits(raw) > MAX_NUMBER_DIGITS:
                raise ParseError("Number too large", i)
            try:
                value = float(raw)
            except (ValueError, OverflowError) as exc:
                raise ParseError("Number too large", i) from exc
            if not math.isfinite(value) or abs(value) > MAX_ABS_RESULT:
                raise ParseError("Number too large", i)
            tokens.append(_Token("num", value, i))
            i = end
            continue

        if ch.isalpha() or ch == "_":
            match = _IDENT_RE.match(text, i)
            word = match.group()
            tokens.append(_Token("ident", word.lower(), i))
            i = match.end()
            continue

        if ch == "*" and i + 1 < n and text[i + 1] == "*":
            tokens.append(_Token("op", "^", i))
            i += 2
            continue

        if ch in "+-−*/^(),":
            value = "-" if ch == "−" else ch
            tokens.append(_Token("op", value, i))
            i += 1
            continue

        if ch == "=":
            raise ParseError("Enter only the expression, without '='", i)

        raise ParseError(f"Unexpected character '{ch}'", i)

    # Insert implicit multiplication:
    # 2x, 2(x+1), (x+1)y, 2pi, 2sin(x).
    expanded = []

    def ends_atom(token):
        if token.kind == "num":
            return True
        if token.kind == "op" and token.value == ")":
            return True
        if token.kind == "ident":
            return token.value in {"x", "y", "pi", "e"}
        return False

    def starts_atom(token):
        if token.kind == "num":
            return True
        if token.kind == "op" and token.value == "(":
            return True
        if token.kind == "ident":
            return (
                token.value in {"x", "y", "pi", "e"}
                or token.value in FUNCTIONS
            )
        return False

    for token in tokens:
        if expanded and ends_atom(expanded[-1]) and starts_atom(token):
            expanded.append(_Token("op", "*", token.pos))
        expanded.append(token)

    expanded.append(_Token("eof", None, n))
    return expanded


class _Parser:
    def __init__(self, text):
        self.text = text
        self.tokens = _tokenize(text)
        self.i = 0

    def peek(self):
        return self.tokens[self.i]

    def advance(self):
        token = self.peek()
        self.i += 1
        return token

    def accept(self, value):
        token = self.peek()
        if token.kind == "op" and token.value == value:
            return self.advance()
        return None

    def expect(self, value):
        token = self.accept(value)
        if token is None:
            raise ParseError(f"Expected '{value}'", self.peek().pos)
        return token

    def parse(self):
        if self.peek().kind == "eof":
            return ("num", 0.0)

        node = self.expression()

        if self.peek().kind != "eof":
            token = self.peek()
            raise ParseError(
                f"Unexpected token '{token.value}'", token.pos
            )

        return node

    # expression := term (('+' | '-') term)*
    def expression(self):
        node = self.term()

        while self.peek().kind == "op" and self.peek().value in ("+", "-"):
            op = self.advance().value
            right = self.term()
            node = ("binary", op, node, right)

        return node

    # term := unary (('*' | '/') unary)*
    def term(self):
        node = self.unary()

        while self.peek().kind == "op" and self.peek().value in ("*", "/"):
            op = self.advance().value
            right = self.unary()
            node = ("binary", op, node, right)

        return node

    # -x^2 means -(x^2); x^-2 is also valid.
    def unary(self):
        if self.accept("+"):
            return self.unary()

        if self.accept("-"):
            return ("neg", self.unary())

        return self.power()

    # power := atom ['^' unary]
    # Right associative: x^2^3 == x^(2^3).
    def power(self):
        node = self.atom()

        if self.accept("^"):
            node = ("binary", "^", node, self.unary())

        return node

    def atom(self):
        token = self.advance()

        if token.kind == "num":
            return ("num", token.value)

        if token.kind == "op" and token.value == "(":
            node = self.expression()
            self.expect(")")
            return node

        if token.kind == "ident":
            name = token.value

            if name == "x" or name == "y":
                return ("var", name)

            if name in CONSTANTS:
                return ("num", CONSTANTS[name])

            if name not in FUNCTIONS:
                raise ParseError(f"Unknown symbol '{name}'", token.pos)

            self.expect("(")
            args = []

            if not (
                self.peek().kind == "op"
                and self.peek().value == ")"
            ):
                args.append(self.expression())

                while self.accept(","):
                    args.append(self.expression())

            self.expect(")")

            # Reject empty function calls such as sin().
            if not args:
                raise ParseError(
                    f"Function '{name}' requires at least one argument",
                    token.pos,
                )

            

            if name in expected_args:
                expected = expected_args[name]

                if isinstance(expected, int):
                    valid_count = len(args) == expected
                else:
                    minimum, maximum = expected
                    valid_count = (
                        len(args) >= minimum
                        and (maximum is None or len(args) <= maximum)
                    )

                if not valid_count:
                    raise ParseError(
                        f"Invalid number of arguments for '{name}'",
                        token.pos,
                    )

            return ("call", name, tuple(args))

        if token.kind == "eof":
            raise ParseError("Expression ends unexpectedly", token.pos)

        raise ParseError(
            f"Unexpected token '{token.value}'", token.pos
        )


def _evaluate(node, variables):
    kind = node[0]

    if kind == "num":
        return node[1]

    if kind == "var":
        return variables[node[1]]

    if kind == "neg":
        return -_evaluate(node[1], variables)

    if kind == "binary":
        op, left, right = node[1], node[2], node[3]
        a = _evaluate(left, variables)
        b = _evaluate(right, variables)

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
        values = [_evaluate(arg, variables) for arg in args]
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


def parse_expression(text):
    """Parse a general expression into an Expression object."""
    if not isinstance(text, str):
        raise ParseError("Expression must be text", 0)
    if len(text) > MAX_TEXT_LEN:
        raise ParseError("Expression too long", MAX_TEXT_LEN)
    try:
        return Expression(_Parser(text).parse())
    except RecursionError as exc:
        raise ParseError("Expression is nested too deeply", 0) from exc


def try_parse_expression(text):
    """Return (Expression, None) or (None, error message)."""
    try:
        return parse_expression(text), None
    except ParseError as exc:
        return None, exc.message


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


def _linear_coefficients(node):
    """Convert an AST to linear coefficients, rejecting nonlinear terms."""
    kind = node[0]

    if kind == "num":
        return 0.0, 0.0, float(node[1])

    if kind == "var":
        return (
            (1.0, 0.0, 0.0)
            if node[1] == "x"
            else (0.0, 1.0, 0.0)
        )

    if kind == "neg":
        return tuple(-v for v in _linear_coefficients(node[1]))

    if kind != "binary":
        raise ValueError("Functions are not supported by parse_linear()")

    op, left_node, right_node = node[1], node[2], node[3]
    left = _linear_coefficients(left_node)
    right = _linear_coefficients(right_node)

    if op in ("+", "-"):
        sign = 1.0 if op == "+" else -1.0
        return tuple(left[i] + sign * right[i] for i in range(3))

    left_var = left[0] != 0 or left[1] != 0
    right_var = right[0] != 0 or right[1] != 0

    if op == "*":
        if left_var and right_var:
            raise ValueError("Expression is not linear")
        if left_var:
            return tuple(v * right[2] for v in left)
        if right_var:
            return tuple(v * left[2] for v in right)
        return 0.0, 0.0, left[2] * right[2]

    if op == "/":
        if right_var:
            raise ValueError("Cannot divide by a variable expression")
        if right[2] == 0:
            raise ValueError("Division by zero")
        return tuple(v / right[2] for v in left)

    if op == "^":
        if right_var:
            raise ValueError("Variable exponent is not linear")
        exponent = right[2]

        if exponent == 1:
            return left

        if exponent == 0:
            return 0.0, 0.0, 1.0

        if not left_var:
            return 0.0, 0.0, left[2] ** exponent

        raise ValueError("Expression is not linear")

    raise ValueError(f"Unsupported operator '{op}'")


def parse_linear(text):
    """Backward-compatible parser for linear expressions only."""
    expression = parse_expression(text)

    try:
        a, b, c = _linear_coefficients(expression._node)
    except (ValueError, ArithmeticError, OverflowError) as exc:
        raise ParseError(str(exc), 0) from exc

    if not all(math.isfinite(v) for v in (a, b, c)):
        raise ParseError("Number too large", 0)
    # Keep parser-level backstop effective downstream: linear coefficients
    # feed ForceField directly, so clamp to the same ceiling as evaluate().
    if any(abs(v) > MAX_ABS_RESULT for v in (a, b, c)):
        raise ParseError("Number too large", 0)

    return LinearExpr(a, b, c)


def try_parse(text):
    """Return (LinearExpr, None) or (None, error message)."""
    try:
        return parse_linear(text), None
    except ParseError as exc:
        return None, exc.message


def diagnose(text):
    """Return (LinearExpr, None, None) or (None, message, position)."""
    try:
        return parse_linear(text), None, None
    except ParseError as exc:
        return None, exc.message, exc.pos