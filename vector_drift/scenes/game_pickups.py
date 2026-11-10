"""Split from scenes/game.py to keep files manageable."""
import logging
import math
from dataclasses import replace

import pygame

from .. import config, render, sprites
from ..config import px
from ..desktop import set_cursor
from ..background import BackgroundBuilder
from ..coords import Viewport, fit_zoom
from ..data import (SHIPS, custom_level_to_snapshot, default_ship_id, get_level,
                    is_custom_level, level_holes, section_count, section_level, section_shift,
                    ship_unlocked)
from ..expr_parser import diagnose_expression
from ..hints import get_hint
from ..level_presets import is_dynamic_level
from ..physics import Flight, ForceField, Outcome
from ..pickups import EXTRATIME_DURATION, extratime_bonus_steps
from ..image_assets import COIN_BALANCE
from ..ui import (Button, CodeEditor, IconButton, coin_price_parts, draw_coins, draw_icon_row,
                  draw_panel_box, draw_text, icon_surface)
from ..solver import PSOSolver, PSOConfig, Solver, run_solver_async
from ..solver.interface import SolveResult
from .base import Scene
from .hint_popup import HintPopup, confirm_text
from .pause_menu import PauseMenu
from . import pickup_effects as pfx
from .game_section_pan import SectionPan
log = logging.getLogger(__name__)

# Physics-expected failures (bad user expression, overflow, huge-finite clamp).
# Anything outside this tuple is an internal bug: still contained as DIVERGED
# so the frame loop never dies, but logged at exception level for debugging.
_PHYSICS_ERRORS = (
    ArithmeticError, ValueError, TypeError, OverflowError,
    RecursionError, MemoryError,
)
# Rendering never raises for bad numbers; only these pygame/data errors are
# contained (never bare `Exception`, so real bugs stay visible in logs).
_RENDER_ERRORS = (
    pygame.error, ValueError, TypeError, OverflowError, MemoryError,
)

from .game_layout import *


class GamePickupMixin:

    def _play_flight_sounds(self):
        """Bounce off a rock / pass through a black hole since the last frame."""
        flight = self.flight
        bounces = getattr(flight, "bounces", 0)
        if bounces > self._bounces_heard:
            self._bounces_heard = bounces
            self.audio.play("bounce")
        teleports = getattr(flight, "teleports", 0)
        if teleports > self._teleports_heard:
            self._teleports_heard = teleports
            self.audio.play("warp")

    def _drain_pickup_events(self):
        """Sync scene state and play sounds for new pickup events (once each).

        The Flight has already applied every effect to itself (see
        Flight._apply_pickup_events). Shockwave destroys obstacles: mirror
        flight.obstacle_specs back into the frozen level (dataclasses.replace
        -> new tuple) so rendering and the next launch both see the
        survivors. The other kinds only play their sound here.
        """
        from dataclasses import replace

        events = self.flight.pickup_events
        if not events:
            return
        try:
            self._replay_pickup_events.extend(events)
        except Exception:
            pass
        for event in events:
            if event.get("kind") == "shockwave":
                destroyed = event.get("destroyed") or ()
                if destroyed:
                    # shockwave_effect already rewrote flight.obstacle_specs to
                    # survivors; just mirror the same list into the frozen
                    # level so rendering / next launch see the survivors.
                    self.flight.obstacle_specs = tuple(
                        o for o in self.flight.obstacle_specs
                        if o not in destroyed
                    )
                    self.level = replace(
                        self.level, obstacles=self.flight.obstacle_specs
                    )
                self._add_pickup_fx(self._burst_fx, event)
                try:
                    self.audio.play("shockwave")
                except Exception:  # noqa: BLE001 - sfx slot is optional
                    log.debug("shockwave sfx skipped", exc_info=True)
            elif event.get("kind") == "extratime":
                # Flight._apply_pickup_events already extended the flight.
                self._add_pickup_fx(self._extratime_fx, event)
                try:
                    self.audio.play("extratime")
                except Exception:  # noqa: BLE001 - sfx slot is optional
                    log.debug("extratime sfx skipped", exc_info=True)
            elif event.get("kind") == "shield":
                # Flight._apply_pickup_events already started the effect.
                self._add_pickup_fx(self._burst_fx, event)
                try:
                    self.audio.play("shield")
                except Exception:  # noqa: BLE001 - sfx slot is optional
                    log.debug("shield sfx skipped", exc_info=True)
            elif event.get("kind") == "life":
                # Restore one life if not already full.
                lit = None
                if self.lives < self.level.lives:
                    self.lives += 1
                    lit = self.lives - 1        # the lives icon that just lit up
                self._add_pickup_fx(self._life_fx, event, lit)
                try:
                    self.audio.play("life")
                except Exception:  # noqa: BLE001 - sfx slot is optional
                    log.debug("life sfx skipped", exc_info=True)
            elif event.get("kind") == "money":
                # Each coin pays once: once ever on a fixed level, once per
                # map on a random level.  After a reveal coins pay nothing
                # and stay collectable for a later run.
                key = self._coin_key(event.get("center"))
                collected = self._collected_coins()
                if key not in collected:
                    collected.add(key)
                    amount = event.get("amount", 1)
                    if self.level.id not in getattr(self.session, "custom_level_ids", set()):
                        self.session.money.add(amount)
                        self._add_pickup_fx(self._money_fx, event, amount)   # only coins paid
                    self.money = self.session.money
                    self._run_coins.append((key, amount))
                    self._save_progress()
                try:
                    self.audio.play("money")
                except Exception:  # noqa: BLE001 - sfx slot is optional
                    log.debug("money sfx skipped", exc_info=True)
            elif event.get("kind") == "unbound":
                # Flight._apply_pickup_events already opened the map edge.
                self._add_pickup_fx(self._edge_fx, event)
                try:
                    self.audio.play("unbound")
                except Exception:  # noqa: BLE001 - sfx slot is optional
                    log.debug("unbound sfx skipped", exc_info=True)
            elif event.get("kind") == "shield_used":
                # The protection broke on a bumper (the ship still passes it).
                try:
                    self.audio.play("shield_break")
                except Exception:  # noqa: BLE001 - sfx slot is optional
                    log.debug("shield_break sfx skipped", exc_info=True)
        self.flight.pickup_events = []
        # self.pickups holds the SAME PickupState objects the Flight just
        # consumed (passed by reference), so no re-sync is needed: used
        # pickups stay gone for the rest of this run's lives.

    # ------------------------------------------------------------------ pickup effects
    def _add_pickup_fx(self, make, event, *args):
        """Start one pickup's effect. Presentation only: a bad event never stops the rules."""
        try:
            make(event, *args)
        except (AttributeError, KeyError, IndexError, *_RENDER_ERRORS) as exc:
            log.debug("pickup effect skipped: %r", exc)

    def _pickup_radius(self, center):
        """Radius (m) of the pickup at ``center`` (the event only names its centre)."""
        for pickup in self.pickups or ():
            if tuple(pickup.center) == tuple(center):
                return pickup.radius
        return pfx.DEFAULT_RADIUS_M

    def _burst_fx(self, event):
        center = tuple(event["center"])
        self.pickup_fx.burst(event["kind"], center, self._pickup_radius(center))

    def _extratime_fx(self, event):
        # The seconds the Flight really added (whole steps of its dt).
        dt = getattr(self.flight, "dt", config.DT)
        steps = extratime_bonus_steps(dt, float(event.get("extratime_duration", EXTRATIME_DURATION)))
        seconds = steps * dt
        self.pickup_fx.fly("extratime", pfx.TIMER, f"+{round(seconds, 2):g}", pfx.EXTRATIME_COLOR,
                           seconds, self.camera.to_screen(*event["center"]))

    def _money_fx(self, event, amount):
        self.pickup_fx.fly("money", pfx.COINS, f"+{amount}", pfx.MONEY_COLOR, amount,
                           self.camera.to_screen(*event["center"]))

    def _life_fx(self, event, lit_index):
        center = tuple(event["center"])
        self.pickup_fx.life(center, self._pickup_radius(center), lit_index)

    def _edge_fx(self, event):
        self.pickup_fx.edge(getattr(self.flight, "bounds",
                                    (config.WORLD_HALF_W, config.WORLD_HALF_H)))

    def _shown_time_left(self):
        """The clock: an extratime's seconds show once its "+N" reaches it."""
        if self.flight is None:
            return self.level.time_limit
        return max(0.0, self.flight.time_left - self.pickup_fx.pending(pfx.TIMER))

    def _shown_money(self):
        """The coin count: a coin shows once its "+N" reaches it."""
        return max(0, int(self.session.money) - int(self.pickup_fx.pending(pfx.COINS)))

    def _fly_target(self, target):
        """Screen point a "+N" text flies to: the clock or the coin count."""
        if target == pfx.TIMER:
            return (px(CX + 62), px(STATUS_Y))
        if self._coins_rect is not None:
            return self._coins_rect.center
        return (config.WINDOW_W - px(40), px(20))

    def _draw_pickup_fx(self, surface):
        """The effects drawn in the map (world positions through the camera)."""
        vp = self.camera
        for effect in self.pickup_fx.effects:
            try:
                if effect.style == "burst":
                    sprites.draw_pickup_burst(surface, vp.to_screen(*effect.center),
                                              vp.length(effect.radius), self.t, effect.kind,
                                              effect.progress, grow=pfx.BURST_SCALE)
                elif effect.style == "life":
                    sprites.draw_checkpoint_life(
                        surface, vp.to_screen(*effect.center),
                        vp.length(effect.radius * pfx.LIFE_RADIUS_SCALE), self.t,
                        self.flyable_ship, fade=effect.progress)
                elif effect.style == "edge":
                    self._draw_edge_flash(surface, effect)
            except _RENDER_ERRORS as exc:
                log.warning("pickup effect draw contained: %r", exc)

    def _draw_edge_flash(self, surface, effect):
        """Unbound: a bright frame moves out onto the map edge and fades.

        At zoom 1 the map edge is the plot's edge, so the frame starts
        EDGE_FLASH_IN inside it (anything further out would be clipped).
        """
        hx, hy = effect.bounds
        left, top = self.camera.to_screen(-hx, hy)
        right, bottom = self.camera.to_screen(hx, -hy)
        p = effect.progress
        width = max(2, px(pfx.EDGE_FLASH_WIDTH))
        inset = width / 2 + px(pfx.EDGE_FLASH_IN) * (1.0 - p)
        plot = pygame.Rect(self.camera.rect)
        frame = pygame.Rect(round(left + inset - plot.x), round(top + inset - plot.y),
                            round(right - left - 2 * inset), round(bottom - top - 2 * inset))
        if frame.w <= 0 or frame.h <= 0:
            return
        layer = pygame.Surface(plot.size, pygame.SRCALPHA)
        pygame.draw.rect(layer, (*UNBOUND_EDGE, round(255 * (1.0 - p))), frame, width)
        surface.blit(layer, plot.topleft)

    def _draw_fly_texts(self, surface):
        """The "+N" texts on their way from the pickup to the clock / coin count."""
        for effect in self.pickup_fx.effects:
            if effect.style != "fly":
                continue
            try:
                (x0, y0), (x1, y1) = effect.center, self._fly_target(effect.target)
                p = ease_in_out(effect.progress)
                draw_text(surface, effect.text, (x0 + (x1 - x0) * p, y0 + (y1 - y0) * p),
                          pfx.FLY_TEXT_SIZE, effect.color, kind="bold", anchor="center")
            except _RENDER_ERRORS as exc:
                log.warning("pickup text draw contained: %r", exc)

    def _safe_end_flight(self, outcome, banner=None):
        """End-of-flight bookkeeping that never raises out of update()."""
        try:
            self._end_flight(outcome)
        except _PHYSICS_ERRORS as exc:
            # State may be half-updated (lives/trail); log and force a
            # consistent SETUP so the next launch starts clean.
            log.warning("end-flight %s contained: %r", outcome, exc)
            self.flight = None
            self.launch_pos = self.level.start
            self.state = SETUP
            self._refresh_buttons()
        except Exception:  # noqa: BLE001 - last-resort guard: frame loop must live
            log.exception("unexpected end-flight failure")
            self.flight = None
            self.launch_pos = self.level.start
            self.state = SETUP
            try:
                self._refresh_buttons()
            except _RENDER_ERRORS:
                pass

        if banner is not None:
            try:
                title, sub = banner
                self.banner = (title, sub, config.BANNER_DURATION)
            except _RENDER_ERRORS as exc:
                log.warning("banner update contained: %r", exc)

    # ------------------------------------------------------------------ update

import sys as _sys
def _gm():
    return _sys.modules["vector_drift.scenes.game"]
def PSOConfig(*a, **k):
    return _gm().PSOConfig(*a, **k)
def draw_coins(*a, **k):
    return _gm().draw_coins(*a, **k)
def draw_icon_row(*a, **k):
    return _gm().draw_icon_row(*a, **k)
def draw_text(*a, **k):
    return _gm().draw_text(*a, **k)
def get_hint(*a, **k):
    return _gm().get_hint(*a, **k)
def get_level(*a, **k):
    return _gm().get_level(*a, **k)
def run_solver_async(*a, **k):
    return _gm().run_solver_async(*a, **k)


def GameScene(*a, **k):
    return _gm().GameScene(*a, **k)
