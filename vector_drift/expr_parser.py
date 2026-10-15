"""Parser for linear force expressions of the form  p*x + q*y + r.

Accepted:  2x, 2*x, -x, x/2, 1/2x, -3/4 y, .5, y + x + 1, "" (= 0)
Rejected with a readable reason: products, powers, parentheses, functions,
repeated terms, unknown symbols, division by zero, dangling operators.
"""

import math
import re
from dataclasses import dataclass

FUNCTION_NAMES = {"sin", "cos", "tan", "exp", "log", "ln", "sqrt", "abs"}
_NUMBER_RE = re.compile(r"\d+(?:\.\d*)?|\.\d+")
_LETTERS_RE = re.compile(r"[A-Za-z_]+")
_BRACKETS = "()[]{}"


@dataclass(frozen=True)
class LinearExpr:
    x: float = 0.0      # coefficient of x
    y: float = 0.0      # coefficient of y
    c: float = 0.0      # constant term


class ParseError(ValueError):
    def __init__(self, message, pos=0):
        super().__init__(message)
        self.message = message
        self.pos = pos


@dataclass(frozen=True)
class _Tok:
    kind: str           # "num", "var", "op"
    value: object
    pos: int


def _tokenize(text):
    tokens = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch.isspace():
            i += 1
            continue
        if ch.isdigit() or ch == ".":
            m = _NUMBER_RE.match(text, i)
            if not m:
                raise ParseError("Invalid number '.'", i)
            end = m.end()
            if end < n and text[end] == ".":
                raise ParseError("Invalid number (two decimal points)", i)
            tokens.append(_Tok("num", float(m.group()), i))
            i = end
            continue
        if ch.isalpha() or ch == "_":
            m = _LETTERS_RE.match(text, i)
            word = m.group()
            lower = word.lower()
            after = m.end()
            while after < n and text[after].isspace():
                after += 1
            if lower in FUNCTION_NAMES or (after < n and text[after] == "("):
                raise ParseError("Functions are not supported", i)
            if lower.startswith("e") and i > 0 and (text[i - 1].isdigit() or text[i - 1] == "."):
                raise ParseError("Scientific notation is not supported", i)
            if lower in ("x", "y"):
                tokens.append(_Tok("var", lower, i))
            elif set(lower) <= {"x", "y"}:
                raise ParseError("Products of variables are not supported", i)
            else:
                raise ParseError(f"Unknown symbol '{word}'", i)
            i = m.end()
            continue
        if ch in "+-−":
            tokens.append(_Tok("op", "-" if ch != "+" else "+", i))
            i += 1
            continue
        if ch == "*":
            if i + 1 < n and text[i + 1] == "*":
                raise ParseError("Powers are not supported", i)
            tokens.append(_Tok("op", "*", i))
            i += 1
            continue
        if ch == "/":
            tokens.append(_Tok("op", "/", i))
            i += 1
            continue
        if ch == "^":
            raise ParseError("Powers are not supported", i)
        if ch in _BRACKETS:
            raise ParseError("Parentheses are not supported", i)
        if ch == ",":
            raise ParseError("Use '.' for decimals", i)
        if ch == "=":
            raise ParseError("Enter only the right-hand side", i)
        raise ParseError(f"Unexpected character '{ch}'", i)
    return tokens


class _Parser:
    def __init__(self, text):
        self.text = text
        self.tokens = _tokenize(text)
        self.i = 0

    # -- token helpers ----------------------------------------------------
    def peek(self):
        return self.tokens[self.i] if self.i < len(self.tokens) else None

    def advance(self):
        tok = self.tokens[self.i]
        self.i += 1
        return tok

    def at_op(self, *ops):
        tok = self.peek()
        return tok is not None and tok.kind == "op" and tok.value in ops

    def end_pos(self):
        return len(self.text)

    # -- grammar ----------------------------------------------------------
    def parse(self):
        coeffs = {}
        if not self.tokens:
            return LinearExpr()
        while True:
            sign = 1.0
            if self.at_op("+", "-"):
                sign = -1.0 if self.advance().value == "-" else 1.0
                if self.at_op("+", "-"):
                    raise ParseError("Two signs in a row", self.peek().pos)
            if self.peek() is None:
                raise ParseError("Expression ends with an operator", self.end_pos())
            term_pos = self.peek().pos

            key, value = self.parse_term()
            if key in coeffs:
                name = "Constant term" if key == "c" else key
                raise ParseError(f"{name} appears more than once", term_pos)
            coeffs[key] = sign * value

            tok = self.peek()
            if tok is None:
                break
            if not self.at_op("+", "-"):
                raise ParseError("Missing '+' or '-' between terms", tok.pos)

        result = LinearExpr(**coeffs)
        for v in (result.x, result.y, result.c):
            if not math.isfinite(v):
                raise ParseError("Number too large", 0)
        return result

    def expect_number_after(self, op_tok):
        tok = self.peek()
        if tok is None:
            raise ParseError("Expression ends with an operator", self.end_pos())
        if tok.kind == "var":
            raise ParseError("Cannot divide by a variable", tok.pos)
        if tok.kind != "num":
            raise ParseError(f"Expected a number after '{op_tok.value}'", tok.pos)
        self.advance()
        if tok.value == 0:
            raise ParseError("Division by zero", tok.pos)
        return tok.value

    def parse_term(self):
        """Return (key, coefficient) where key is 'x', 'y' or 'c'."""
        coef = None
        tok = self.peek()

        if tok.kind == "num":
            coef = self.advance().value
            if self.at_op("/"):
                coef /= self.expect_number_after(self.advance())
                if self.at_op("/"):
                    raise ParseError("Only one '/' per coefficient", self.peek().pos)
            if self.at_op("*"):
                star = self.advance()
                nxt = self.peek()
                if nxt is None:
                    raise ParseError("Expression ends with an operator", self.end_pos())
                if nxt.kind == "num":
                    raise ParseError("Write a single number instead of a product", nxt.pos)
                if nxt.kind != "var":
                    raise ParseError("Expected x or y after '*'", star.pos)
        elif tok.kind == "op":
            raise ParseError(f"Unexpected '{tok.value}'", tok.pos)

        tok = self.peek()
        if tok is not None and tok.kind == "var":
            var = self.advance().value
            explicit_coef = coef is not None
            if coef is None:
                coef = 1.0
            if self.at_op("/"):
                coef /= self.expect_number_after(self.advance())
                if self.at_op("/"):
                    raise ParseError("Only one '/' per coefficient", self.peek().pos)
            nxt = self.peek()
            if nxt is not None:
                if nxt.kind == "var":
                    raise ParseError("Products of variables are not supported", nxt.pos)
                if nxt.kind == "num":
                    if explicit_coef:
                        raise ParseError("Missing '+' or '-' between terms", nxt.pos)
                    raise ParseError("Put the coefficient before the variable (2x)", nxt.pos)
                if nxt.kind == "op" and nxt.value == "*":
                    self.advance()
                    after = self.peek()
                    if after is None:
                        raise ParseError("Expression ends with an operator", self.end_pos())
                    if after.kind == "var":
                        raise ParseError("Products of variables are not supported", after.pos)
                    raise ParseError("Put the coefficient before the variable (2x)", after.pos)
            return var, coef

        # Constant term
        if tok is not None and tok.kind == "num":
            raise ParseError("Missing '+' or '-' between numbers", tok.pos)
        return "c", coef


def parse_linear(text):
    """Parse text into a LinearExpr. Raises ParseError on invalid input."""
    return _Parser(text).parse()


def try_parse(text):
    """Return (LinearExpr, None) on success or (None, error message)."""
    expr, error, _pos = diagnose(text)
    return expr, error


def diagnose(text):
    """Return (LinearExpr, None, None) or (None, error message, character index)."""
    try:
        return parse_linear(text), None, None
    except ParseError as exc:
        return None, exc.message, exc.pos
