"""Safety limits for the expression language.

Canonical values live in config.py; these aliases stay for backward compat.
The parser-level limits are a backstop: the UI caps input length, but pasted
text, restored sessions, or direct API calls can bypass that cap.
"""

from . import config

MAX_TEXT_LEN = config.MAX_EXPR_TEXT_LEN
MAX_NUMBER_DIGITS = config.MAX_NUMBER_DIGITS
MAX_ABS_RESULT = config.MAX_EXPR_RESULT

__all__ = ["MAX_TEXT_LEN", "MAX_NUMBER_DIGITS", "MAX_ABS_RESULT"]
