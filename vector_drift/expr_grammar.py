"""Recursive-descent grammar for the expression language.

Produces the tuple node tree evaluated by :mod:`vector_drift.expr_evaluator`.
"""

from .expr_errors import ParseError
from .expr_evaluator import Expression
from .expr_lexer import tokenize
from .expr_limits import MAX_TEXT_LEN
from .expr_registry import CONSTANTS, FUNCTIONS, expected_args


class Parser:
    def __init__(self, text):
        self.text = text
        self.tokens = tokenize(text)
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


def parse_expression(text):
    """Parse a general expression into an Expression object."""
    if not isinstance(text, str):
        raise ParseError("Expression must be text", 0)
    if len(text) > MAX_TEXT_LEN:
        raise ParseError("Expression too long", MAX_TEXT_LEN)
    try:
        return Expression(Parser(text).parse())
    except RecursionError as exc:
        raise ParseError("Expression is nested too deeply", 0) from exc


def try_parse_expression(text):
    """Return (Expression, None) or (None, error message)."""
    try:
        return parse_expression(text), None
    except ParseError as exc:
        return None, exc.message


# Backward-compatible private alias.
_Parser = Parser


__all__ = ["Parser", "_Parser", "parse_expression", "try_parse_expression"]
