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

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from . import config
from .data import SHIPS, LevelSpec, ObstacleSpec
from .expr_parser import parse_expression
from .physics import Flight, ForceField, Outcome
from .physics_core import segment_hits_circle
from .pickups import discs_overlap

DAILY_LEVEL_NAME = "Daily Challenge"
DAILY_SHIP = SHIPS["ship01"]
TARGET_RADIUS = 1.0                 # same as the fixed levels

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


# --- Reference path and target ---------------------------------------------------
START_X = -8.0
START_YS = (-4, -2, 0, 2, 4)
TARGET_TIME_SPAN = (0.4, 0.8)       # t* lies in this part of the time limit
MIN_TARGET_DISTANCE = 6.0           # m from the start
MIN_PATH_BEND = 1.5                 # m the path must stray from the start-target line
FIELD_REDRAWS = 100                 # field draws per attempt before the attempt fails
_FAR_AWAY = (1e6, 1e6)              # target of the probe flight: never reached


def _level(start, target, obstacles=(), pickups=(), time_limit=config.DAILY_TIME_LIMIT,
           target_radius=TARGET_RADIUS, name=DAILY_LEVEL_NAME):
    return LevelSpec(id=config.DAILY_LEVEL_ID, name=name, start=start, target_center=target,
                     target_radius=target_radius, ship_id=DAILY_SHIP.id, time_limit=time_limit,
                     lives=config.DAILY_LIVES, obstacles=tuple(obstacles), pickups=tuple(pickups))


def fly_reference(field, start, steps):
    """Positions of ``field`` flown from rest at ``start`` on an empty map.

    One point per step (index = step), ``steps`` steps at most; shorter when
    the flight left the map (its last point is then the one outside) or
    diverged. Uses the game's own Flight and config.DT.
    """
    probe = _level(start, _FAR_AWAY, time_limit=steps * config.DT, target_radius=0.0)
    flight = Flight(field.force_field(), DAILY_SHIP, probe)
    while flight.running:
        flight.step()
    return tuple(flight.trail)


def point_segment_distance(point, a, b):
    """Distance (m) from ``point`` to the segment a-b."""
    ax, ay = a
    dx, dy = b[0] - ax, b[1] - ay
    length2 = dx * dx + dy * dy
    u = 0.0
    if length2 > 0.0:
        u = max(0.0, min(1.0, ((point[0] - ax) * dx + (point[1] - ay) * dy) / length2))
    return math.hypot(point[0] - ax - u * dx, point[1] - ay - u * dy)


def _inside_map(point, margin=0.0):
    return (abs(point[0]) + margin <= config.WORLD_HALF_W
            and abs(point[1]) + margin <= config.WORLD_HALF_H)


def _enters_target_once(path, target):
    """True if the path, once it touches the target circle, stays on it up to t*.

    Touching is Flight's own segment test (target radius + hull), so a path
    that passes through the circle, leaves and comes back is refused: the
    real flight would already end on that first pass.
    """
    hit_radius = TARGET_RADIUS + DAILY_SHIP.hull_radius
    touching = [segment_hits_circle(path[i], path[i + 1], target, hit_radius)
                for i in range(len(path) - 1)]
    first = touching.index(True)        # the last step always ends on the target
    return all(touching[first:])


@dataclass(frozen=True)
class ReferenceRoute:
    """The reference answer's path from the start to the target (step t*)."""

    field: DailyField
    start: tuple
    target: tuple
    target_step: int                    # t* in steps of config.DT
    path: tuple                         # path[i] = position after i steps, i <= target_step


def _target_step_range():
    limit = config.DAILY_TIME_LIMIT / config.DT
    return round(TARGET_TIME_SPAN[0] * limit), round(TARGET_TIME_SPAN[1] * limit)


def _draw_route(rng):
    """One field, start and t*; None when the rules refuse them."""
    field = pick_field(rng)
    start = (START_X, float(rng.choice(START_YS)))
    step = rng.randint(*_target_step_range())
    # Flying past t* changes nothing below, so the flight stops there.
    path = fly_reference(field, start, step)
    if len(path) != step + 1 or not all(_inside_map(p) for p in path):
        return None                     # left the map before t*
    target = path[step]
    if not _inside_map(target, TARGET_RADIUS):
        return None
    if math.dist(start, target) < MIN_TARGET_DISTANCE:
        return None
    if max(point_segment_distance(p, start, target) for p in path) < MIN_PATH_BEND:
        return None                     # too close to a straight line
    if not _enters_target_once(path, target):
        return None
    return ReferenceRoute(field=field, start=start, target=target, target_step=step, path=path)


def pick_route(rng, redraws=FIELD_REDRAWS):
    """Draw fields until one gives a fair route; None after ``redraws`` tries."""
    for _ in range(redraws):
        route = _draw_route(rng)
        if route is not None:
            return route
    return None


# --- Rocks -------------------------------------------------------------------------
ROCK_COUNT = (3, 6)
ROCK_RADII = (0.6, 0.8, 1.0)
ROCK_PATH_CLEARANCE = 0.6           # m between a rock (plus hull) and the reference path
ENDPOINT_CLEARANCE = 1.5            # m between a rock's edge and the start / target center
PLACEMENT_DRAWS = 300               # candidate spots per rock before the map is given up


def blocks_line(center, radius, route):
    """True if a rock here stops a ship flying straight from start to target."""
    return (point_segment_distance(center, route.start, route.target)
            < radius + DAILY_SHIP.hull_radius)


def rock_fits(center, radius, route, rocks):
    """The placement rules every rock must meet."""
    if not _inside_map(center, radius):
        return False
    if (math.dist(center, route.start) < radius + ENDPOINT_CLEARANCE
            or math.dist(center, route.target) < radius + ENDPOINT_CLEARANCE):
        return False
    if any(discs_overlap(center, radius, rock.center, rock.radius) for rock in rocks):
        return False
    clearance = radius + DAILY_SHIP.hull_radius + ROCK_PATH_CLEARANCE
    return all(point_segment_distance(center, route.path[i], route.path[i + 1]) >= clearance
               for i in range(len(route.path) - 1))


def _blocker_spot(rng, radius, route):
    """A random spot whose rock would block the start-target line."""
    (sx, sy), (tx, ty) = route.start, route.target
    length = math.dist(route.start, route.target)
    nx, ny = -(ty - sy) / length, (tx - sx) / length
    u = rng.random()
    reach = radius + DAILY_SHIP.hull_radius
    offset = rng.uniform(-reach, reach)
    return sx + u * (tx - sx) + offset * nx, sy + u * (ty - sy) + offset * ny


def _open_spot(rng, radius):
    return (rng.uniform(-config.WORLD_HALF_W + radius, config.WORLD_HALF_W - radius),
            rng.uniform(-config.WORLD_HALF_H + radius, config.WORLD_HALF_H - radius))


def place_rocks(rng, route):
    """3-6 rocks outside the path's safety tube, the first across the straight line.

    None when a rock finds no spot in PLACEMENT_DRAWS tries.
    """
    rocks = []
    for index in range(rng.randint(*ROCK_COUNT)):
        for _ in range(PLACEMENT_DRAWS):
            radius = rng.choice(ROCK_RADII)
            if index == 0:
                center = _blocker_spot(rng, radius, route)
                if not blocks_line(center, radius, route):
                    continue
            else:
                center = _open_spot(rng, radius)
            if rock_fits(center, radius, route, rocks):
                rocks.append(ObstacleSpec(center=center, radius=radius))
                break
        else:
            return None
    return tuple(rocks)


# --- Constant force check ------------------------------------------------------------
CONSTANT_FORCE_SIZES = (0.5, 1.0, 2.0)  # N, pushing straight at the target


def _flies_to_target(field, level):
    flight = Flight(field, DAILY_SHIP, level)
    while flight.running:
        flight.step()
    return flight.outcome is Outcome.REACHED


def constant_force_reaches(level):
    """True if a constant force aimed at the target reaches it on ``level``."""
    (sx, sy), (tx, ty) = level.start, level.target_center
    length = math.dist(level.start, level.target_center)
    ux, uy = (tx - sx) / length, (ty - sy) / length
    return any(_flies_to_target(ForceField(c=size * ux, f=size * uy), level)
               for size in CONSTANT_FORCE_SIZES)


@dataclass(frozen=True)
class Candidate:
    """A map being built: the reference route and what is placed around it."""

    route: ReferenceRoute
    rocks: tuple
    coins: tuple = ()

    def level(self):
        return _level(self.route.start, self.route.target, self.rocks, self.coins)


def build_candidate(rng):
    """Route, rocks and checks from one rng; None when this attempt fails."""
    route = pick_route(rng)
    if route is None:
        return None
    rocks = place_rocks(rng, route)
    if rocks is None:
        return None
    candidate = Candidate(route=route, rocks=rocks)
    if constant_force_reaches(candidate.level()):
        return None                     # a plain push would solve it
    return candidate
