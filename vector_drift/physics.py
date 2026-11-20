"""Flight simulation with extensible force fields and semi-implicit Euler."""

import math

from . import config
from .expr_parser import singular_parts
from .data import level_holes
from .physics_core import (
    ForceField, Outcome, reflect_velocity, segment_circle_first_hit,
    segment_hits_circle,
)

# --- safety limits -----------------------------------------------------------
# Huge-but-finite forces (e.g. tan(pi/2) ~= 1.6e16) pass every isfinite() check
# yet tunnel through the target in one step (REACHED) and then crash pygame
# with 1e12-scale screen coordinates. Clamp here so they become DIVERGED.
# Canonical values live in config.py; aliases stay for backward compat.
MAX_FORCE = config.MAX_FORCE
# Single-step displacement guard (backstop for tunneling REACHED). Must allow
# legit fast crossings (Fx=1e5 moves ~14 m in one step) but catch 1e12-scale
# jumps that would fake a hit and crash the renderer.
MAX_STEP_M = config.MAX_STEP_M

# What a force evaluation may raise for a bad expression (same set step() catches).
_FORCE_ERRORS = (ArithmeticError, ValueError, TypeError, OverflowError,
                 RecursionError, MemoryError)
# Closest look at a suspected pole: well above float error at |coords| <= 10 m.
_POLE_PROBE_MIN_M = 1e-12


def _evaluates(function, point):
    try:
        function(*point)
    except _FORCE_ERRORS:
        return False
    return True


def _edge(on_start_side):
    """Bisect [0, 1] to float precision for where on_start_side(t) turns False."""
    lo, hi = 0.0, 1.0
    for _ in range(64):
        mid = (lo + hi) / 2
        if not lo < mid < hi:
            break
        if on_start_side(mid):
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def _toward(a, b, factor=1.0, min_dist=1e-9):
    """Direction from ``a`` toward ``b``, scaled by ``factor``: (ux, uy).

    Returns (0.0, 0.0) when the two points are not further than
    ``min_dist`` apart, so callers that add the result can skip their own
    "too close to point" branch.
    """
    dx, dy = b[0] - a[0], b[1] - a[1]
    dist = math.hypot(dx, dy)
    if not dist > min_dist:
        return (0.0, 0.0)
    return (factor * dx / dist, factor * dy / dist)


def _lerp(a, b, t):
    """Point at parameter ``t`` along a->b."""
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


class Flight:
    """One launch of the ship, initially at rest.

    Advance with advance(frame_dt) or step().
    `start` defaults to the level start; pass another point to resume.
    """

    def __init__(
        self,
        field,
        ship,
        level,
        start=None,
        bounds=(config.WORLD_HALF_W, config.WORLD_HALF_H),
        dt=config.DT,
        pickups=None,
        holes=None,
    ):
        if not math.isfinite(dt) or dt <= 0:
            raise ValueError("dt must be a finite positive number")

        if not math.isfinite(ship.mass) or ship.mass <= 0:
            raise ValueError("Ship mass must be a finite positive number")

        self.field = field
        # Sub-expressions whose zeros may be points of infinite force (_pole_between).
        self._singular_parts = tuple(dict.fromkeys(
            part
            for expr in (getattr(field, "fx_expr", None), getattr(field, "fy_expr", None))
            for part in singular_parts(expr)
        ))
        self.mass = ship.mass
        self.hull_radius = ship.hull_radius
        self.hit_radius = level.target_radius + ship.hull_radius
        self.target = level.target_center
        self._init_obstacles(level, ship)
        self._init_pickups(level, pickups)
        self._init_holes(level, holes)
        self.bounds = bounds
        # Unbound pickup: from then on this flight cannot go out of bounds.
        self.unbound = False
        # Magnet pickup: pulls the ship toward the target while active.
        self.magnet_remaining = 0.0
        self.magnet_force = 0.0
        # Active abilities (purchased in shop): charges available this flight.
        self.boost_charges = 0
        self.boost_impulse = 5.0
        self.shield_pulse_charges = 0
        self.magnet_charges = 0
        self.time_freeze_charges = 0
        self.phase_charges = 0
        self.brake_charges = 0
        self.blink_charges = 0
        self.time_freeze_remaining = 0.0
        self.phase_remaining = 0.0
        self.dt = dt
        self.max_steps = round(level.time_limit / dt)
        self._frozen_steps = 0

        self.x, self.y = level.start if start is None else start
        self.vx = self.vy = 0.0
        self.bounces = 0
        self.steps = 0
        self.outcome = Outcome.RUNNING
        self.trail = [(self.x, self.y)]
        self._accumulator = 0.0
        self.shield_remaining = 0.0  # seconds of shield left (next bumper passed / edge bounced)
        self.hole_teleported = False  # True if this step's hole teleport moved the ship
        self.teleports = 0            # black-hole passes so far (the scene plays "warp" per pass)
        self.flings = 0               # times a point of infinite force flung the ship
        # Indices into trail where a new stroke starts (the ship came out of a
        # white hole): the trail is not joined across a teleport.
        self.trail_breaks = []

    def _init_obstacles(self, level, ship):
        # (center, radius incl. hull, restitution), precomputed so step() stays cheap.
        # obstacle_specs is kept (mutable list) so pickup effects (shockwave) can
        # remove obstacles mid-flight; obstacles is rebuilt alongside it.
        self.obstacle_specs = list(getattr(level, "obstacles", ()) or ())
        self.obstacles = tuple(
            ((o.center[0], o.center[1]), o.radius + ship.hull_radius, o.restitution)
            for o in self.obstacle_specs
        )

    def _init_pickups(self, level, pickups):
        # Runtime pickups (consumed flag lives on PickupState, never on spec).
        # Shared by reference when the caller passes them (GameScene passes
        # its run-level list so consumed pickups persist across lives);
        # otherwise built fresh from level.pickups. No config = no pickups.
        from .pickups import PickupState
        if pickups is None:
            specs = getattr(level, "pickups", ()) or ()
            self.pickups = tuple(PickupState.from_spec(s) for s in specs)
        else:
            self.pickups = tuple(pickups)
        self.pickup_events = []  # event dicts from triggered pickups (scene/tests)

    def _init_holes(self, level, holes):
        # Black/white hole pairs (wormholes). Persist for the whole flight.
        if holes is None:
            holes = level_holes(level)
        self.holes = []
        for h in (holes or ()):
            try:
                bc = getattr(h, "black_center", None)
                wc = getattr(h, "white_center", None)
                r = getattr(h, "radius", 0.5)
                if bc is None and isinstance(h, (tuple, list)):
                    # (black_center, white_center, radius?) or (black, white)
                    bc = h[0]; wc = h[1]
                    r = h[2] if len(h) > 2 else r
                self.holes.append(((float(bc[0]), float(bc[1])),
                                  (float(wc[0]), float(wc[1])), float(r)))
            except (TypeError, ValueError, IndexError, AttributeError):
                continue
        self.portals = self.holes
        self.wormholes = self.holes

    @property
    def time(self):
        return (self.steps - self._frozen_steps) * self.dt

    @property
    def time_left(self):
        return max(0.0, (self.max_steps - self.steps) * self.dt)

    @property
    def force(self):
        try:
            return self.field.at(self.x, self.y)
        except _FORCE_ERRORS:
            return (math.nan, math.nan)

    @property
    def running(self):
        return self.outcome is Outcome.RUNNING

    def _tick_effects(self):
        self.steps += 1
        if self.time_freeze_remaining > 0.0:
            self._frozen_steps += 1
        self.time_freeze_remaining = max(0.0, self.time_freeze_remaining - self.dt)
        self.phase_remaining = max(0.0, self.phase_remaining - self.dt)
        self.shield_remaining = max(0.0, self.shield_remaining - self.dt)
        self.magnet_remaining = max(0.0, self.magnet_remaining - self.dt)

    def step(self):
        if not self.running:
            return self.outcome

        self._step_force = None
        try:
            fx, fy = self.field.at(self.x, self.y)
            # Magnet pickup: pull toward the target while active.
            if self.magnet_remaining > 0.0:
                pull_x, pull_y = _toward((self.x, self.y), self.target, self.magnet_force)
                fx = fx + pull_x
                fy = fy + pull_y
            self._step_force = (fx, fy)

            # Semi-implicit Euler: update velocity before position.
            vx = self.vx + fx / self.mass * self.dt
            vy = self.vy + fy / self.mass * self.dt

            nx = self.x + vx * self.dt
            ny = self.y + vy * self.dt

        except _FORCE_ERRORS:
            self._tick_effects()
            self.outcome = Outcome.DIVERGED
            return self.outcome

        self._tick_effects()
 
        if not all(math.isfinite(v) for v in (nx, ny, vx, vy)):
            self.outcome = Outcome.DIVERGED
            return self.outcome

        # Tunneling guard: a single step must not jump across the world.
        # Huge-but-finite F (tan(pi/2)) would otherwise fake a REACHED hit.
        if math.hypot(nx - self.x, ny - self.y) > MAX_STEP_M:
            self.outcome = Outcome.DIVERGED
            return self.outcome

        p0 = (self.x, self.y)
        solid = self._solid_obstacles(p0)

        self.vx, self.vy = vx, vy
        # Samples only see the force at step ends, so a point of infinite
        # force in between (tan(x) at x = pi/2, 1/x^2 at x = 0) is stepped
        # over: its kicks are whatever the nearby samples happen to give.
        # Passing through one flings the ship off the field instead (unless
        # a bumper comes first).
        pole = self._pole_between(p0, (nx, ny))
        if pole is not None and not self._bumper_before(p0, (nx, ny), pole[0], solid):
            self._fling(p0, (nx, ny), *pole)
            return self.outcome

        self.x, self.y = nx, ny
        # Pickups and the target see the piecewise path the ship flew
        # (p0 -> bounce contact -> ... -> final), not the open chord across it.
        # That path ends at the first black hole on it (see _bounce_along_path).
        legs, white = self._bounce_along_path(p0, solid)
        reached = any(
            segment_hits_circle(leg_a, leg_b, self.target, self.hit_radius)
            for leg_a, leg_b in legs
        )
        # A black hole teleports the ship to the paired white hole with the
        # velocity it went in with, unless the target came first on the path.
        self.hole_teleported = False
        if white is not None and not reached:
            self._teleport(white)
        # Pickups use the same segment test (no tunneling); one shared call
        # handles every kind — no per-kind branches in the loop.
        for leg_a, leg_b in legs:
            self._take_pickups(leg_a, leg_b)

        if reached:
            self.outcome = Outcome.REACHED
        elif not self.unbound and (abs(self.x) > self.bounds[0] or abs(self.y) > self.bounds[1]):
            self.outcome = Outcome.OUT_OF_BOUNDS
        elif self.steps >= self.max_steps:
            self.outcome = Outcome.TIMEOUT

        return self.outcome

    def _pole_between(self, p0, p1):
        """(t, direction) of the first point of infinite force on p0->p1, else None.

        Candidates are where a singular part of the field changes sign (see
        expr_parser.singular_parts: denominators, tan's cos, log's argument)
        and where the force stops being evaluable. _blow_up() then keeps
        only those the force really grows towards.
        """
        def at(t):
            return _lerp(p0, p1, t)

        def same_sign(part, t, sign):
            try:
                return part.evaluate(*at(t)) * sign > 0.0
            except _FORCE_ERRORS:
                return False

        candidates = []
        if not _evaluates(self.field.at, p1):
            candidates.append(_edge(lambda t: _evaluates(self.field.at, at(t))))
        for part in self._singular_parts:
            try:
                s0, s1 = part.evaluate(*p0), part.evaluate(*p1)
            except _FORCE_ERRORS:
                continue
            if s0 * s1 < 0.0:
                candidates.append(_edge(lambda t: same_sign(part, t, s0)))
        for t in sorted(candidates):
            direction = self._blow_up(at(t), p0)
            if direction is not None:
                return t, direction
        return None

    def _blow_up(self, point, p0):
        """Unit force just before `point` if the force is infinite there, else None.

        Walks in from p0 (distances shrinking tenfold down to 1e-12 m): some
        component must grow every time, and either stop being evaluable
        (past MAX_FORCE) or end up at least 1.5x its value at p0. So 1/x,
        tan(x) and log(abs(x)) at 0 count, while a removable point (sin(x)/x),
        a jump (floor) or a plain domain edge (sqrt(x)) does not.
        """
        dist = math.dist(p0, point)
        if dist < _POLE_PROBE_MIN_M:
            return None
        ux, uy = (point[0] - p0[0]) / dist, (point[1] - p0[1]) / dist
        sizes, near = [], None
        growing = [True, True]
        d = dist
        while d >= _POLE_PROBE_MIN_M:
            try:
                f = self.field.at(point[0] - ux * d, point[1] - uy * d)
            except _FORCE_ERRORS:
                break               # beyond MAX_FORCE (or undefined) right next to it
            size = (abs(f[0]), abs(f[1]))
            if sizes:
                growing = [g and s > l for g, s, l in zip(growing, size, sizes[-1])]
            sizes.append(size)
            near = f
            d /= 10.0
        else:
            if len(sizes) < 2:
                return None         # a single sample shows no growth
            growing = [g and l >= 1.5 * s for g, l, s in zip(growing, sizes[-1], sizes[0])]
        norm = math.hypot(*near) if near is not None else 0.0
        if norm == 0.0 or not any(growing):
            return None

        return near[0] / norm, near[1] / norm

    def _first_hole(self, start, end):
        """(t, white center) of the first black hole touched on start->end, else None.

        First along the path, whatever order the holes are listed in.
        """
        first = None
        for black, white, radius in (self.holes or []):
            try:
                t = segment_circle_first_hit(start, end, black, radius + self.hull_radius)
            except (TypeError, ValueError, OverflowError):
                continue
            if t is not None and (first is None or t < first[0]):
                first = (t, white)
        return first

    def _enter_hole(self, start, end, legs, before=1.0):
        """End this step's path at the first black hole on start->end, if any.

        Only a hole touched no later than parameter ``before`` (the next
        bounce on this leg) counts. The path then stops at the hole entry:
        the last leg runs start->entry, the ship and the trail's stroke end
        there. Returns the paired white hole, else None.
        """
        hole = self._first_hole(start, end)
        if hole is None or hole[0] > before:
            return None
        t, white = hole
        entry = _lerp(start, end, t)
        legs.append((start, entry))
        self.x, self.y = entry
        self.trail.append(entry)
        return white

    def _teleport(self, white):
        """Come out of the white hole: a new trail stroke starts there; velocity is kept."""
        self.trail_breaks.append(len(self.trail))
        self.x, self.y = white[0], white[1]
        self.trail.append((self.x, self.y))
        self.hole_teleported = True
        self.teleports += 1

    def _take_pickups(self, p0, p1):
        """Trigger the pickups on p0->p1, apply them to this flight, keep the events."""
        from .pickups import check_pickups_segment
        events = check_pickups_segment(self.pickups, p0, p1, self.hull_radius, ctx=self)
        self._apply_pickup_events(events)
        self.pickup_events.extend(events)

    def _apply_pickup_events(self, events):
        """Apply pickup events to this flight: the one place for these rules.

        step() calls it the moment a pickup triggers, so GameScene and the
        solver fly by the same rules; callers only add presentation (sound).
        Private because calling it again would apply the same events twice
        (one extratime pickup granting 6 s). extratime extends max_steps by
        extratime_bonus_steps() (elapsed steps are never rewound, so flight
        time and scores stay true). The shield protects the ship for its
        duration (a new one overwrites what is left) against the next
        collision, whichever comes first: a bumper is passed, the map edge
        bounces the ship back elastically (also when flung by a point of
        infinite force); either uses the protection up (_bounce_along_path,
        _fling). shockwave needs nothing here: its effect already removed the
        obstacles from this flight. unbound means the rest of this flight is
        never out of bounds, however far it goes; Unbound takes precedence at
        the edge, so crossing it does not use the shield, which stays for the
        bumpers.
        """
        from .pickups import (EXTRATIME_DURATION, SHIELD_DURATION,
                              extratime_bonus_steps)
        for event in events:
            kind = event.get("kind")
            if kind == "extratime":
                duration = float(event.get("extratime_duration", EXTRATIME_DURATION))
                self.max_steps = max(self.max_steps + extratime_bonus_steps(self.dt, duration),
                                     self.steps)
            elif kind == "shield":
                self.shield_remaining = float(event.get("shield_duration", SHIELD_DURATION))
            elif kind == "unbound":
                self.unbound = True

    def _solid_obstacles(self, p0):
        """The bumpers that can bounce the ship this step.

        All but those it starts the step overlapping (closer than radius +
        hull, the collision reach): the bumper the shield broke on,
        or the one a resumed launch starts in (time ran out while passing
        it). The ship passes through such a bumper until it is fully out;
        reflecting there would only bounce it back and forth inside. Once
        out, hitting it again bounces as usual.
        """
        return tuple(ob for ob in self.obstacles if math.dist(p0, ob[0]) >= ob[1])

    def _bumper_before(self, p0, p1, t, obstacles):
        """True if the segment p0->p1 hits one of ``obstacles`` before parameter t.

        Same rules as _bounce_along_path: under shield protection the first
        bumper touched is passed, so only a later one can block. A phased ship
        passes through every bumper, so none of them block the way to a pole.
        """
        if self.phase_remaining > 0.0:
            return False
        hits = sorted(hit for center, radius, _ in obstacles
                      if (hit := segment_circle_first_hit(p0, p1, center, radius)) is not None)
        if self.shield_remaining > 0.0:
            hits = hits[1:]
        return bool(hits) and hits[0] < t

    def _use_shield(self, center):
        """Protection is used up on touching a bumper or the map edge; the scene plays shield_break."""
        self.shield_remaining = 0.0
        self.pickup_events.append({"kind": "shield_used", "center": center})

    def _edge_can_bounce(self):
        """True while the shield would bounce the ship off the map edge.

        Unbound comes first: an unbound ship has no edge, so the shield is
        not used there and stays for a bumper.
        """
        return self.shield_remaining > 0.0 and not self.unbound

    def _edge_crossing(self, start, end):
        """Parameter t in [0, 1] where start->end first leaves the bounds, else None."""
        hits = []
        for s, e, bound in zip(start, end, self.bounds):
            if abs(e) > bound and e != s:
                edge = math.copysign(bound, e)
                hits.append(max(0.0, (edge - s) / (e - s)))
        return min(hits) if hits else None

    def _bounce_off_edge(self, start, end, t):
        """Elastic bounce off the map edge at start + t*(end-start); uses the shield.

        The rest of the step is mirrored back inside: every component the
        end point is out on (both in a corner) flips, the speed is kept.
        Returns the (start, end) of the remaining leg.
        """
        contact = [s + (e - s) * t for s, e in zip(start, end)]
        new_end = list(end)
        velocity = [self.vx, self.vy]
        for i, bound in enumerate(self.bounds):
            contact[i] = max(-bound, min(bound, contact[i]))
            if abs(end[i]) > bound:
                new_end[i] = 2.0 * math.copysign(bound, end[i]) - end[i]
                velocity[i] = -velocity[i]
        self.vx, self.vy = velocity
        contact = tuple(contact)
        self._use_shield(contact)
        self.trail.append(contact)
        return contact, tuple(new_end)

    def _fling(self, p0, p1, t, direction):
        """Reach the pole at p0 + t*(p1-p0), then shoot straight off the field.

        Pickups and the target on the way to the pole still count; past it
        the ship leaves along `direction` and the flight is OUT_OF_BOUNDS,
        unless a shield is up: then it bounces off the edge it reaches, the
        shield is used and the flight goes on (the step back may reach the
        target like any other step).
        An unbound ship cannot go out of bounds: it stops at the pole and the
        flight is DIVERGED instead (infinite force, no way to fly on).
        """
        pole = _lerp(p0, p1, t)
        self._take_pickups(p0, pole)
        self.trail.append(pole)
        if segment_hits_circle(p0, pole, self.target, self.hit_radius):
            self.x, self.y = pole
            self.outcome = Outcome.REACHED
            return
        self.flings += 1
        if self.unbound:
            self.x, self.y = pole
            self.outcome = Outcome.DIVERGED
            return
        reach = max(0.0, min(
            (bound - c * math.copysign(1.0, d)) / abs(d)
            for c, d, bound in zip(pole, direction, self.bounds) if d
        ))
        dx, dy = direction
        self.x, self.y = pole[0] + dx * reach, pole[1] + dy * reach
        self.vx, self.vy = dx * reach / self.dt, dy * reach / self.dt   # all in one step
        if self._edge_can_bounce():
            # The shield bounces the ship off the edge it was flung to (both
            # components in a corner) and the flight goes on as usual.
            edge = []
            velocity = [self.vx, self.vy]
            for i, (c, bound) in enumerate(zip((self.x, self.y), self.bounds)):
                at_edge = abs(c) >= bound * (1.0 - 1e-9)
                edge.append(max(-bound, min(bound, c)))
                if at_edge:
                    velocity[i] = -velocity[i]
            self.x, self.y = edge
            self.vx, self.vy = velocity
            self._use_shield((self.x, self.y))
            self.trail.append((self.x, self.y))
            return
        self.trail.append((self.x, self.y))
        self.outcome = Outcome.OUT_OF_BOUNDS

    def _bounce_along_path(self, p0, obstacles):
        """Reflect off ``obstacles`` hit along this step's path (closest first).

        Under shield protection the first bumper touched is passed instead
        of reflected, and touching it uses the protection up. The ship then
        starts the next steps inside that bumper, which _solid_obstacles
        leaves out until the ship is through. The map edge shares that one
        protection: if the edge comes first the ship bounces off it
        (_bounce_off_edge) and later bumpers reflect as usual; once the
        protection is gone, leaving the map is OUT_OF_BOUNDS in step().

        Events are taken in the order the ship meets them: the first black
        hole on the path ends it at the hole entry (_enter_hole), so nothing
        after it (bounce, shield use, rest of the path) happens this step.

        Returns (legs, white): the flown legs [(start, end), ...] and the
        white hole to come out of, or None when no black hole was hit.
        """
        legs = []
        if self.phase_remaining > 0.0 or (not obstacles and not self._edge_can_bounce()):
            end = (self.x, self.y)
            white = self._enter_hole(p0, end, legs)
            if white is None:
                self.trail.append(end)
                legs.append((p0, end))
            return legs, white
        obstacles = list(obstacles)
        start = p0
        end = (self.x, self.y)
        for _ in range(max(1, len(obstacles) * 2) + 1):
            earliest = None  # (t, obstacle)
            for obstacle in obstacles:
                t = segment_circle_first_hit(start, end, obstacle[0], obstacle[1])
                if t is not None and (earliest is None or t < earliest[0]):
                    earliest = (t, obstacle)
            # The map edge competes with the bumpers for the one shield:
            # whichever the ship touches first takes it.
            edge_t = self._edge_crossing(start, end) if self._edge_can_bounce() else None
            edge_first = edge_t is not None and (earliest is None or edge_t <= earliest[0])
            if not edge_first and earliest is None:
                break
            # A black hole before this bounce (or shield use) ends the path.
            white = self._enter_hole(start, end, legs, edge_t if edge_first else earliest[0])
            if white is not None:
                return legs, white
            if edge_first:
                contact, new_end = self._bounce_off_edge(start, end, edge_t)
                legs.append((start, contact))
                start, end = contact, new_end
                continue
            t, obstacle = earliest
            center, radius, restitution = obstacle
            if self.shield_remaining > 0.0:
                self._use_shield(center)
                obstacles.remove(obstacle)          # carried through this one
                continue
            hx, hy = _lerp(start, end, t)
            nx, ny = hx - center[0], hy - center[1]
            dist = math.hypot(nx, ny)
            if dist < 1e-9:
                # Dead-center hit: fall back to incoming direction.
                nx, ny = -self.vx, -self.vy
                dist = math.hypot(nx, ny)
                if dist < 1e-9:
                    nx, ny, dist = 1.0, 0.0, 1.0
            nx, ny = nx / dist, ny / dist
            self.vx, self.vy = reflect_velocity(self.vx, self.vy, nx, ny,
                                                restitution)
            # Nudge off the surface so the next test starts outside.
            legs.append((start, (hx, hy)))
            hx, hy = hx + nx * 1e-6, hy + ny * 1e-6
            # Remaining leg re-emitted from the contact point.
            frac = 1.0 - t
            end = (hx + self.vx * self.dt * frac, hy + self.vy * self.dt * frac)
            start = (hx, hy)
            self.bounces += 1
            self.trail.append((hx, hy))
        white = self._enter_hole(start, end, legs)
        if white is not None:
            return legs, white
        self.x, self.y = end
        self.trail.append((self.x, self.y))
        legs.append((start, end))
        return legs, None

    ABILITY_CHARGE_ATTRS = {
        "ability_boost": "boost_charges",
        "ability_shield_pulse": "shield_pulse_charges",
        "ability_magnet": "magnet_charges",
        "ability_time_freeze": "time_freeze_charges",
        "ability_phase": "phase_charges",
        "ability_brake": "brake_charges",
        "ability_blink": "blink_charges",
    }

    def set_ability_charges(self, charges):
        charges = charges if isinstance(charges, dict) else {}
        for ability_id, attr in self.ABILITY_CHARGE_ATTRS.items():
            try:
                setattr(self, attr, max(0, int(charges.get(ability_id, 0))))
            except (TypeError, ValueError):
                setattr(self, attr, 0)

    def boost(self, impulse=None):
        if self.boost_charges <= 0 or not self.running:
            return False
        imp = self.boost_impulse if impulse is None else float(impulse)
        speed = math.hypot(self.vx, self.vy)
        if speed < 1e-9:
            push_x, push_y = _toward((self.x, self.y), self.target, imp)
            self.vx += push_x
            self.vy += push_y
        else:
            self.vx += imp * self.vx / speed
            self.vy += imp * self.vy / speed
        self.boost_charges -= 1
        return True

    def shield_pulse(self):
        if not self.running or self.shield_pulse_charges <= 0:
            return False
        self.shield_remaining = max(self.shield_remaining, 3.0)
        self.shield_pulse_charges -= 1
        return True

    def magnet_pulse(self, duration=None, force=None):
        if not self.running or self.magnet_charges <= 0:
            return False
        self.magnet_remaining = float(duration) if duration is not None else 3.0
        self.magnet_force = float(force) if force is not None else 6.0
        self.magnet_charges -= 1
        return True

    def time_freeze(self, duration=3.0):
        if self.time_freeze_charges <= 0 or not self.running:
            return False
        try:
            duration = float(duration)
        except (TypeError, ValueError):
            return False
        if duration <= 0.0:
            return False
        added_steps = max(1, round(duration / self.dt))
        self.time_freeze_remaining += duration
        self.max_steps += added_steps
        self.time_freeze_charges -= 1
        return True

    def phase_shift(self, duration=2.5):
        if self.phase_charges <= 0 or not self.running:
            return False
        try:
            duration = float(duration)
        except (TypeError, ValueError):
            return False
        if duration <= 0.0:
            return False
        self.phase_remaining = max(self.phase_remaining, duration)
        self.phase_charges -= 1
        return True

    def retro_burn(self, factor=0.4):
        if self.brake_charges <= 0 or not self.running:
            return False
        try:
            factor = min(1.0, max(0.0, float(factor)))
        except (TypeError, ValueError):
            factor = 0.4
        self.vx *= factor
        self.vy *= factor
        self.brake_charges -= 1
        return True

    def blink(self, distance=2.5):
        if self.blink_charges <= 0 or not self.running:
            return False
        try:
            distance = float(distance)
        except (TypeError, ValueError):
            return False
        if distance <= 0.0:
            return False
        speed = math.hypot(self.vx, self.vy)
        if speed > 1e-9:
            dx, dy = self.vx / speed, self.vy / speed
        else:
            dx, dy = _toward((self.x, self.y), self.target)
            if dx == 0.0 and dy == 0.0:
                return False
        self.trail.append((self.x, self.y))
        self.trail_breaks.append(len(self.trail))
        self.x, self.y = self.x + dx * distance, self.y + dy * distance
        self.trail.append((self.x, self.y))
        self.teleports += 1
        from vector_drift.physics_core import segment_hits_circle
        if segment_hits_circle((self.x, self.y), (self.x, self.y),
                               self.target, self.hit_radius):
            self.outcome = Outcome.REACHED
        elif not self.unbound and (abs(self.x) > self.bounds[0]
                                   or abs(self.y) > self.bounds[1]):
            self.outcome = Outcome.OUT_OF_BOUNDS
        self.blink_charges -= 1
        return True

    def advance(self, frame_dt, on_step=None):
        """Run fixed simulation steps fitting into elapsed frame time."""
        if not self.running:
            return self.outcome

        if not math.isfinite(frame_dt) or frame_dt < 0:
            raise ValueError("frame_dt must be a finite non-negative number")

        self._accumulator += min(frame_dt, config.MAX_FRAME_DT)

        while self._accumulator >= self.dt and self.running:
            self._accumulator -= self.dt
            self.step()
            if on_step is not None:
                on_step(self)

        return self.outcome

    def abort(self):
        if self.running:
            self.outcome = Outcome.ABORTED