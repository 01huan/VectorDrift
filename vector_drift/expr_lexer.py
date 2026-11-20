"""Tokenizer for the expression language.

Turns text into tokens and inserts the implicit multiplications the language
allows (``2x``, ``2(x+1)``, ``(x+1)y``, ``2pi``, ``2sin(x)``).
"""

import math
import re
from dataclasses import dataclass

from .expr_errors import ParseError
from .config import MAX_EXPR_RESULT as MAX_ABS_RESULT, MAX_NUMBER_DIGITS
from .expr_registry import FUNCTIONS

_NUMBER_RE = re.compile(r"(?:\d+(?:\.\d*)?|\.\d+)")
_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z_0-9]*")

_ATOM_WORDS = frozenset({"x", "y", "pi", "e"})


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
        return token.value in _ATOM_WORDS
    return False


def starts_atom(token):
    if token.kind == "num":
        return True
    if token.kind == "op" and token.value == "(":
        return True
    if token.kind == "ident":
        return (
            token.value in _ATOM_WORDS
            or token.value in FUNCTIONS
        )
    return False


def _read_number(text, i):
    """Read the number at ``text[i:]``; return (Token, end_pos)."""
    n = len(text)
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
    return Token("num", value, i), end


def _read_ident(text, i):
    """Read the identifier at ``text[i:]``; return (Token, end_pos)."""
    match = _IDENT_RE.match(text, i)
    if not match:
        raise ParseError(f"Unexpected character '{text[i]}'", i)
    return Token("ident", match.group().lower(), i), match.end()


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
            token, i = _read_number(text, i)
            tokens.append(token)
            continue

        if ch.isalpha() or ch == "_":
            token, i = _read_ident(text, i)
            tokens.append(token)
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
