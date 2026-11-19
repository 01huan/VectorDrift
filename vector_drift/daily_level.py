"""Daily challenge: one generated map per day, the same for every player.

The map is built answer first: pick a simple force field, fly it on an
empty map, take a point of its path as the target and only then place the
rocks outside that path. So every daily map is solvable by construction and
the chosen force field is its reference answer.

Generation is decided by the day's seed alone (same day + same
DAILY_GENERATOR_VERSION -> the same map on every computer): it only uses a
``random.Random(seed)`` and the game's own Flight with config.DT. No global
``random``, clock or ``hash()``.

Pure logic: no Session, pygame or drawing.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from . import config
from .expr_parser import parse_expression
from .physics import ForceField

# Fixed offset, not zoneinfo: Windows without tzdata has no "Asia/Taipei",
# and Taiwan has no daylight saving time.
DAILY_TIMEZONE = timezone(timedelta(hours=config.DAILY_UTC_OFFSET_HOURS))


def daily_today(now=None):
    """Today's date in the daily-challenge time zone (UTC+8).

    ``now`` is an aware datetime (for tests); default is the current time.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    return now.astimezone(DAILY_TIMEZONE).date()


def daily_seed(day):
    """Seed of ``day``'s map: YYYYMMDD * 100 + DAILY_GENERATOR_VERSION."""
    return (day.year * 10000 + day.month * 100 + day.day) * 100 + config.DAILY_GENERATOR_VERSION


# --- Force field templates ---------------------------------------------------
# Every reference answer is linear: Fx = a + b*x + c*y, Fy = d + e*x + f*y,
# with "nice" coefficients only. A template fixes which terms exist and
# which of them must be non-zero (constant terms a and d may be 0).
NONZERO_COEFFS = (-3, -2, -1, -0.5, 0.5, 1, 2, 3)
CONSTANT_TERMS = (-3, -2, -1, -0.5, 0, 0.5, 1, 2, 3)
_NEGATIVE = tuple(v for v in NONZERO_COEFFS if v < 0)


def _swing(rng):
    """Fx = a, Fy = d + f*y (f < 0): an up-and-down swing while drifting."""
    a, d, f = rng.choice(CONSTANT_TERMS), rng.choice(CONSTANT_TERMS), rng.choice(_NEGATIVE)
    return a, 0, 0, d, 0, f


def _side_swing(rng):
    """Fx = a + b*x (b < 0), Fy = d: a left-right swing."""
    a, b, d = rng.choice(CONSTANT_TERMS), rng.choice(_NEGATIVE), rng.choice(CONSTANT_TERMS)
    return a, b, 0, d, 0, 0


def _parabola(rng):
    """Fx = a, Fy = d + e*x (e != 0)."""
    a, d, e = rng.choice(CONSTANT_TERMS), rng.choice(CONSTANT_TERMS), rng.choice(NONZERO_COEFFS)
    return a, 0, 0, d, e, 0


def _rotation(rng):
    """Fx = a + c*y, Fy = d + e*x (c and e of opposite signs)."""
    a, d = rng.choice(CONSTANT_TERMS), rng.choice(CONSTANT_TERMS)
    c = rng.choice(NONZERO_COEFFS)
    e = rng.choice(tuple(v for v in NONZERO_COEFFS if v * c < 0))
    return a, 0, c, d, e, 0


def _two_axis(rng):
    """Fx = a + b*x, Fy = d + f*y (b, f != 0, any sign)."""
    a, b = rng.choice(CONSTANT_TERMS), rng.choice(NONZERO_COEFFS)
    d, f = rng.choice(CONSTANT_TERMS), rng.choice(NONZERO_COEFFS)
    return a, b, 0, d, 0, f


# Ordered (rng.choice needs a stable order): name -> coefficient picker.
TEMPLATES = {
    "swing": _swing,
    "side_swing": _side_swing,
    "parabola": _parabola,
    "rotation": _rotation,
    "two_axis": _two_axis,
}


def _number(value):
    """A coefficient as typed: 2 not 2.0, 0.5 not .5."""
    return f"{value:g}"


def format_linear(const, x_coeff, y_coeff):
    """``const + x_coeff*x + y_coeff*y`` the way a player types it.

    Variable terms first, then the constant; 0 terms and coefficient 1 are
    left out; implicit multiplication (``0.5x``); a lone 0 is ``"0"``.
    """
    terms = [(value, name) for value, name in ((x_coeff, "x"), (y_coeff, "y"), (const, ""))
             if value != 0]
    if not terms:
        return "0"
    text = ""
    for i, (value, name) in enumerate(terms):
        size = abs(value)
        body = name if name and size == 1 else _number(size) + name
        if i == 0:
            text = ("-" if value < 0 else "") + body
        else:
            text += (" - " if value < 0 else " + ") + body
    return text


@dataclass(frozen=True)
class DailyField:
    """A reference answer: ``coeffs`` = (a, b, c, d, e, f) and its typed form."""

    template: str
    coeffs: tuple
    fx: str
    fy: str

    def force_field(self):
        """The field exactly as the game builds it from the typed answer."""
        return ForceField.from_exprs(parse_expression(self.fx), parse_expression(self.fy))


def pick_field(rng):
    """Draw a template (uniform), then its coefficients."""
    name = rng.choice(tuple(TEMPLATES))
    a, b, c, d, e, f = TEMPLATES[name](rng)
    return DailyField(template=name, coeffs=(a, b, c, d, e, f),
                      fx=format_linear(a, b, c), fy=format_linear(d, e, f))
