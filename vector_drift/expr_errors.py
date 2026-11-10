"""Exception types raised by the expression parser."""

__all__ = ["ParseError", "EvaluationError"]


class ParseError(ValueError):
    """An expression has invalid syntax."""

    def __init__(self, message, pos=0):
        super().__init__(message)
        self.message = message
        self.pos = pos


class EvaluationError(ValueError):
    """A valid expression could not be evaluated."""
