"""Daily challenge generator: one map per day, the same for every player.

Everything is decided by the day's seed, so these tests can pin exact days.
"""

import math
import random
import re
from datetime import date, datetime, timedelta, timezone

import pytest

from vector_drift import config, daily_level
from vector_drift.daily_level import (COIN_RADIUS, CONSTANT_TERMS, DAILY_SHIP,
                                      FALLBACK_TARGET_STEP, NONZERO_COEFFS, START_X, START_YS,
                                      TARGET_RADIUS, TEMPLATES, DailyField, ReferenceRoute,
                                      blocks_line, build_candidate, coin_fits,
                                      constant_force_reaches, daily_seed, daily_today,
                                      fallback_map, fly_reference, format_linear, generate_daily,
                                      pick_field, pick_route, place_rocks, point_segment_distance,
                                      rock_fits)
from vector_drift.data import LevelSpec, ObstacleSpec, PickupSpec
from vector_drift.expr_parser import parse_expression
from vector_drift.physics import Flight, ForceField, Outcome
from vector_drift.physics_core import segment_hits_circle

HULL = DAILY_SHIP.hull_radius
STEPS_PER_SECOND = round(1 / config.DT)
# Seeds for the per-stage checks, in chunks so pytest -n spreads them out.
STAGE_SEEDS = 200
CHUNK = 20
SEED_CHUNKS = [range(i, i + CHUNK) for i in range(0, STAGE_SEEDS, CHUNK)]


def _chunk_id(seeds):
    return f"seeds{seeds.start}-{seeds.stop - 1}"


def test_today_switches_at_midnight_taiwan_time():
    before = datetime(2026, 11, 19, 15, 59, tzinfo=timezone.utc)
    after = datetime(2026, 11, 19, 16, 0, tzinfo=timezone.utc)

    assert daily_today(before) == date(2026, 11, 19)
    assert daily_today(after) == date(2026, 11, 20)


def test_today_accepts_any_aware_time():
    new_york = timezone(timedelta(hours=-5))

    assert daily_today(datetime(2026, 11, 19, 11, 0, tzinfo=new_york)) == date(2026, 11, 20)


def test_today_without_an_argument_is_a_date():
    assert isinstance(daily_today(), date)


def test_seed_is_the_date_and_generator_version():
    assert config.DAILY_GENERATOR_VERSION == 1
    assert daily_seed(date(2026, 11, 19)) == 2026111901
    assert daily_seed(date(2027, 1, 2)) == 2027010201


# --- Force field templates ---------------------------------------------------

PROBE_POINTS = [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0), (2.0, 3.0), (-1.5, 0.5), (-8.0, -4.0)]


def _linear(const, x_coeff, y_coeff, x, y):
    return const + x_coeff * x + y_coeff * y


def test_fields_from_1000_seeds_parse_to_the_chosen_coefficients():
    for seed in range(1000):
        field = pick_field(random.Random(seed))
        a, b, c, d, e, f = field.coeffs
        for text, (const, x_coeff, y_coeff) in ((field.fx, (a, b, c)), (field.fy, (d, e, f))):
            assert ".0" not in text, (seed, text)
            assert not re.search(r"(?<![\d.])1[xy]", text), (seed, text)
            assert not re.search(r"[+-]\s*[+-]", text), (seed, text)
            expr = parse_expression(text)
            for x, y in PROBE_POINTS:
                assert expr.evaluate(x, y) == _linear(const, x_coeff, y_coeff, x, y), (seed, text)


def test_template_coefficient_rules_hold():
    seen = set()
    for seed in range(1000):
        field = pick_field(random.Random(seed))
        a, b, c, d, e, f = field.coeffs
        seen.add(field.template)
        assert a in CONSTANT_TERMS and d in CONSTANT_TERMS
        if field.template == "swing":
            assert (b, c, e) == (0, 0, 0) and f < 0
        elif field.template == "side_swing":
            assert (c, e, f) == (0, 0, 0) and b < 0
        elif field.template == "parabola":
            assert (b, c, f) == (0, 0, 0) and e != 0
        elif field.template == "rotation":
            assert (b, f) == (0, 0) and c * e < 0
        else:
            assert field.template == "two_axis"
            assert (c, e) == (0, 0) and b in NONZERO_COEFFS and f in NONZERO_COEFFS
    assert seen == set(TEMPLATES)


def test_same_seed_gives_the_same_field():
    assert pick_field(random.Random(7)) == pick_field(random.Random(7))


@pytest.mark.parametrize("terms, text", [
    ((2, 0, -1), "-y + 2"),
    ((1, 0, -1), "-y + 1"),
    ((-3, 0.5, 0), "0.5x - 3"),
    ((0, -1, 0), "-x"),
    ((0, 1, 0), "x"),
    ((-0.5, 0, 0), "-0.5"),
    ((0, 0, 0), "0"),
    ((3, 0, 2), "2y + 3"),
    ((0.5, -0.25, 0), "-0.25x + 0.5"),
    ((-2, 0, 0.1), "0.1y - 2"),
])
def test_format_linear_writes_what_a_player_would_type(terms, text):
    assert format_linear(*terms) == text


# --- Reference path and target -------------------------------------------------

_ROUTES = {}


def _route(seed):
    """The route seed ``seed`` draws first (cached: later stages reuse it)."""
    if seed not in _ROUTES:
        rng = random.Random(seed)
        _ROUTES[seed] = (pick_route(rng), rng.getstate())
    return _ROUTES[seed]


def _inside_map(point, margin=0.0):
    return (abs(point[0]) + margin <= config.WORLD_HALF_W
            and abs(point[1]) + margin <= config.WORLD_HALF_H)


@pytest.mark.parametrize("seeds", SEED_CHUNKS, ids=_chunk_id)
def test_routes_have_a_fair_target(seeds):
    found = 0
    for seed in seeds:
        route, _ = _route(seed)
        if route is None:
            continue
        found += 1
        start, target, path, k = route.start, route.target, route.path, route.target_step
        assert start[0] == START_X and start[1] in START_YS
        assert 0.4 * config.DAILY_TIME_LIMIT <= k / STEPS_PER_SECOND <= 0.8 * config.DAILY_TIME_LIMIT
        assert len(path) == k + 1 and path[0] == start and path[-1] == target
        assert all(_inside_map(p) for p in path), seed
        assert _inside_map(target, TARGET_RADIUS), seed
        assert math.dist(start, target) >= 6.0, seed
        assert max(point_segment_distance(p, start, target) for p in path) >= 1.5, seed
        touching = [segment_hits_circle(path[i], path[i + 1], target, TARGET_RADIUS + HULL)
                    for i in range(k)]
        first = touching.index(True)
        assert all(touching[first:]), f"seed {seed}: the path visits the target circle twice"
    assert found >= len(seeds) // 2          # some seeds give up after FIELD_REDRAWS draws


def test_route_path_is_the_reference_flight():
    """The path is what Flight flies with the typed answer, step for step."""
    route, _ = _route(3)
    level = LevelSpec(id=config.DAILY_LEVEL_ID, name="probe", start=route.start,
                      target_center=(1e6, 1e6), target_radius=0.0, ship_id=DAILY_SHIP.id,
                      time_limit=config.DAILY_TIME_LIMIT)
    flight = Flight(route.field.force_field(), DAILY_SHIP, level)
    for _ in range(route.target_step):
        flight.step()

    assert tuple(flight.trail) == route.path


def test_same_seed_gives_the_same_route():
    assert pick_route(random.Random(11)) == pick_route(random.Random(11))


# --- Rocks -----------------------------------------------------------------------

_ROCKS = {}


def _rocks(seed):
    """(route, rocks) of seed ``seed``; rocks come from the same rng after the route."""
    if seed not in _ROCKS:
        route, state = _route(seed)
        rocks = None
        if route is not None:
            rng = random.Random()
            rng.setstate(state)
            rocks = place_rocks(rng, route)
        _ROCKS[seed] = (route, rocks)
    return _ROCKS[seed]


def _path_distance(point, path):
    return min(point_segment_distance(point, path[i], path[i + 1]) for i in range(len(path) - 1))


@pytest.mark.parametrize("seeds", SEED_CHUNKS, ids=_chunk_id)
def test_rocks_stay_outside_the_safety_tube(seeds):
    placed = 0
    for seed in seeds:
        route, rocks = _rocks(seed)
        if rocks is None:
            continue
        placed += 1
        assert 3 <= len(rocks) <= 6, seed
        for i, rock in enumerate(rocks):
            r = rock.radius
            assert r in (0.6, 0.8, 1.0)
            assert _path_distance(rock.center, route.path) >= r + HULL + 0.6, seed
            assert _inside_map(rock.center, r), seed
            assert math.dist(rock.center, route.start) >= r + 1.5, seed
            assert math.dist(rock.center, route.target) >= r + 1.5, seed
            for other in rocks[i + 1:]:
                assert math.dist(rock.center, other.center) > r + other.radius, seed
        assert any(point_segment_distance(rock.center, route.start, route.target)
                   < rock.radius + HULL for rock in rocks), f"seed {seed}: nothing blocks the line"
    assert placed >= len(seeds) // 2


# --- Constant force check ----------------------------------------------------------

def _constant_flight(level, size):
    (sx, sy), (tx, ty) = level.start, level.target_center
    length = math.dist(level.start, level.target_center)
    field = ForceField(c=size * (tx - sx) / length, f=size * (ty - sy) / length)
    flight = Flight(field, DAILY_SHIP, level)
    while flight.running:
        flight.step()
    return flight.outcome


_CANDIDATES = {}


def _candidate(seed):
    if seed not in _CANDIDATES:
        _CANDIDATES[seed] = build_candidate(random.Random(seed))
    return _CANDIDATES[seed]


@pytest.mark.parametrize("seeds", [range(0, 25), range(25, 50)], ids=_chunk_id)
def test_no_constant_force_solves_a_candidate(seeds):
    built = 0
    for seed in seeds:
        candidate = _candidate(seed)
        if candidate is None:
            continue
        built += 1
        level = candidate.level()
        assert level.obstacles == candidate.rocks
        for size in (0.5, 1.0, 2.0):
            assert _constant_flight(level, size) is not Outcome.REACHED, (seed, size)
    assert built >= len(seeds) // 2


def test_constant_force_check_spots_an_open_shot():
    open_map = LevelSpec(id=config.DAILY_LEVEL_ID, name="open", start=(-8.0, 0.0),
                         target_center=(0.0, 0.0), target_radius=1.0, ship_id=DAILY_SHIP.id)
    walled = LevelSpec(id=config.DAILY_LEVEL_ID, name="walled", start=(-8.0, 0.0),
                       target_center=(0.0, 0.0), target_radius=1.0, ship_id=DAILY_SHIP.id,
                       obstacles=(ObstacleSpec(center=(-4.0, 0.0), radius=2.0),))

    assert constant_force_reaches(open_map)
    assert not constant_force_reaches(walled)


# --- Coins ---------------------------------------------------------------------------

@pytest.mark.parametrize("seeds", [range(0, 25), range(25, 50)], ids=_chunk_id)
def test_coins_lie_on_the_reference_path(seeds):
    built = 0
    for seed in seeds:
        candidate = _candidate(seed)
        if candidate is None:
            continue
        built += 1
        route, coins = candidate.route, candidate.coins
        k = route.target_step
        assert 1 <= len(coins) <= 2, seed
        assert candidate.level().pickups == coins
        for i, coin in enumerate(coins):
            assert isinstance(coin, PickupSpec) and coin.kind == "money"
            assert coin.radius == COIN_RADIUS == 0.45
            on_path = range(round(0.2 * k), round(0.9 * k) + 1)
            assert min(math.dist(coin.center, route.path[j]) for j in on_path) < 0.01, seed
            for rock in candidate.rocks:
                assert math.dist(coin.center, rock.center) > coin.radius + rock.radius, seed
            assert math.dist(coin.center, route.start) >= 1.5, seed
            assert math.dist(coin.center, route.target) > TARGET_RADIUS + coin.radius, seed
            for other in coins[i + 1:]:
                assert math.dist(coin.center, other.center) >= 2.0, seed
    assert built >= len(seeds) // 2


# --- The daily map -------------------------------------------------------------------

DAY = date(2026, 11, 19)


def _reaches(daily):
    field = ForceField.from_exprs(parse_expression(daily.fx), parse_expression(daily.fy))
    flight = Flight(field, DAILY_SHIP, daily.level)
    while flight.running:
        flight.step()
    return flight.outcome is Outcome.REACHED


def test_daily_map_is_a_daily_level():
    daily = generate_daily(DAY)
    level = daily.level

    assert daily.day == DAY and daily.seed == daily_seed(DAY)
    assert not daily.is_fallback and 1 <= daily.attempts <= config.DAILY_MAX_ATTEMPTS
    assert level.id == config.DAILY_LEVEL_ID == 900
    assert level.name == "Daily Challenge" and level.ship_id == "daybreak"
    assert level.time_limit == config.DAILY_TIME_LIMIT and level.lives == config.DAILY_LIVES
    assert level.target_radius == TARGET_RADIUS
    assert not level.holes and not level.sections
    assert {p.kind for p in level.pickups} == {"money"}
    assert _reaches(daily)


def test_same_day_gives_the_same_map():
    first, second = generate_daily(DAY), generate_daily(DAY)

    assert first == second
    assert (first.level.start, first.level.target_center, first.level.obstacles,
            first.level.pickups, first.fx, first.fy) == (
        second.level.start, second.level.target_center, second.level.obstacles,
        second.level.pickups, second.fx, second.fy)


def test_next_day_gives_another_map():
    today, tomorrow = generate_daily(DAY), generate_daily(DAY + timedelta(days=1))

    assert today.level != tomorrow.level or (today.fx, today.fy) != (tomorrow.fx, tomorrow.fy)
    assert today.level.target_center != tomorrow.level.target_center


def test_attempt_n_uses_its_own_seed(monkeypatch):
    firsts = []

    def failing(rng):
        firsts.append(rng.random())
        return None

    monkeypatch.setattr(daily_level, "build_candidate", failing)
    generate_daily(DAY)

    seed = daily_seed(DAY)
    assert firsts == [random.Random(seed * 1000 + n).random()
                      for n in range(config.DAILY_MAX_ATTEMPTS)]


def test_no_map_in_any_attempt_gives_the_fallback(monkeypatch, caplog):
    monkeypatch.setattr(daily_level, "build_candidate", lambda rng: None)

    with caplog.at_level("WARNING", logger="vector_drift.daily_level"):
        daily = generate_daily(DAY)

    assert daily == fallback_map(DAY)
    assert daily.is_fallback and daily.day == DAY and daily.seed == daily_seed(DAY)
    assert "fallback" in caplog.text


def test_a_crashing_generator_gives_the_fallback(monkeypatch, caplog):
    def broken(rng):
        raise RuntimeError("boom")

    monkeypatch.setattr(daily_level, "build_candidate", broken)

    with caplog.at_level("WARNING", logger="vector_drift.daily_level"):
        daily = generate_daily(DAY)

    assert daily == fallback_map(DAY)
    assert "boom" in caplog.text


def test_fallback_map_reaches_with_its_answer():
    daily = fallback_map(DAY)

    assert (daily.fx, daily.fy) == ("1", "-y + 2")
    assert daily.level.id == config.DAILY_LEVEL_ID
    assert _reaches(daily)


def test_fallback_map_follows_the_generator_rules():
    daily = fallback_map(DAY)
    level = daily.level
    field = DailyField(template="swing", coeffs=(1, 0, 0, 2, 0, -1), fx=daily.fx, fy=daily.fy)
    path = fly_reference(field, level.start, FALLBACK_TARGET_STEP)
    route = ReferenceRoute(field=field, start=level.start, target=level.target_center,
                           target_step=FALLBACK_TARGET_STEP, path=path)

    assert math.dist(path[-1], level.target_center) < 0.01
    assert 3 <= len(level.obstacles) <= 6
    for i, rock in enumerate(level.obstacles):
        assert rock_fits(rock.center, rock.radius, route, level.obstacles[:i])
    assert any(blocks_line(rock.center, rock.radius, route) for rock in level.obstacles)
    assert not constant_force_reaches(level)
    k = FALLBACK_TARGET_STEP
    for i, coin in enumerate(level.pickups):
        assert coin.kind == "money" and coin.radius == COIN_RADIUS
        assert min(math.dist(coin.center, path[j])
                   for j in range(round(0.2 * k), round(0.9 * k) + 1)) < 0.01
        assert coin_fits(coin.center, route, level.obstacles, level.pickups[:i])


# --- Thirty days in a row --------------------------------------------------------------

SOLVABLE_FROM = date(2026, 11, 19)
SOLVABLE_DAYS = 30


def test_daily_maps_for_30_days_are_solvable():
    for offset in range(SOLVABLE_DAYS):
        day = SOLVABLE_FROM + timedelta(days=offset)
        daily = generate_daily(day)
        assert not daily.is_fallback, f"{day} needed the fallback map"
        assert _reaches(daily), f"{day}: Fx = {daily.fx}, Fy = {daily.fy} misses"
