"""Tokenizer for the expression language.

Turns text into tokens and inserts the implicit multiplications the language
allows (``2x``, ``2(x+1)``, ``(x+1)y``, ``2pi``, ``2sin(x)``).
"""

import math
import re
from dataclasses import dataclass

from .expr_errors import ParseError
from .expr_limits import MAX_ABS_RESULT, MAX_NUMBER_DIGITS
from .expr_registry import FUNCTIONS

_NUMBER_RE = re.compile(r"(?:\d+(?:\.\d*)?|\.\d+)")
_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z_0-9]*")


@dataclass(frozen=True)
class Token:
    kind: str
    value: object
    pos: int


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


def tokenize(text):
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
            tokens.append(Token("num", value, i))
            i = end
            continue

        if ch.isalpha() or ch == "_":
            match = _IDENT_RE.match(text, i)
            word = match.group()
            tokens.append(Token("ident", word.lower(), i))
            i = match.end()
            continue

        if ch == "*" and i + 1 < n and text[i + 1] == "*":
            tokens.append(Token("op", "^", i))
            i += 2
            continue

        if ch in "+-−*/^(),":
            value = "-" if ch == "−" else ch
            tokens.append(Token("op", value, i))
            i += 1
            continue

        if ch == "=":
            raise ParseError("Enter only the expression, without '='", i)

        raise ParseError(f"Unexpected character '{ch}'", i)

    # Insert implicit multiplication: 2x, 2(x+1), (x+1)y, 2pi, 2sin(x).
    expanded = []
    for token in tokens:
        if expanded and ends_atom(expanded[-1]) and starts_atom(token):
            expanded.append(Token("op", "*", token.pos))
        expanded.append(token)

    expanded.append(Token("eof", None, n))
    return expanded


# Backward-compatible private alias.
_tokenize = tokenize


__all__ = [
    "Token", "_Token", "_tokenize", "tokenize", "_significant_digits",
    "ends_atom", "starts_atom",
    "_NUMBER_RE", "_IDENT_RE",
]

# Private alias used by older imports.
_Token = Token
