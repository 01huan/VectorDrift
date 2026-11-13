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

from .game_layout import ARRIVED, CAMERA_EASE_S, CAMERA_MARGIN_M, FLIGHT, PANNING


class GameUpdateMixin:

    def update(self, dt):
        self.t += dt
        if not self.hint_mode:
            self._update_ai()
            self._note_ai_answer_shown()
        try:
            self.editor.update(dt)
        except _RENDER_ERRORS as exc:
            log.warning("editor update contained: %r", exc)
        except Exception:  # noqa: BLE001 - last-resort guard: frame loop must live
            log.exception("unexpected editor failure")
        if self.pause_menu is None:     # paused: flight, banner and arrival wait
            self.pickup_fx.update(dt)
            self.ability_fx.update(dt)
            self._update_flight(dt)
            self._update_camera(dt)
            try:
                self._prefetch_arrows()
            except _RENDER_ERRORS as exc:
                log.warning("arrow prefetch contained: %r", exc)

    def _camera_target(self):
        """(zoom the camera eases toward, most it may lag behind while zooming out).

        Out while an unbound ship is off the map, else 1. The second value is
        the zoom that still keeps the whole ship on screen.
        """
        flight = self.flight
        if flight is None or not getattr(flight, "unbound", False) or self.state not in (FLIGHT, ARRIVED):
            return 1.0, 1.0
        pos = (flight.x, flight.y)
        return (fit_zoom(pos, flight.bounds, margin=CAMERA_MARGIN_M),
                fit_zoom(pos, flight.bounds, margin=0.5 * self.ship.length))

    def _update_camera(self, dt):
        """Ease the camera zoom toward its target (smooth out and back in).

        Zooming out never falls behind a fast ship: it stays on screen.
        """
        target, keep_ship = self._camera_target()
        zoom = self.camera.zoom
        if zoom == target:
            return
        zoom += (target - zoom) * (1.0 - math.exp(-dt / CAMERA_EASE_S))
        zoom = min(zoom, keep_ship)
        self.camera.zoom = target if abs(target - zoom) < 1e-3 else zoom

    def _update_ai(self):
        """Random levels: restart the solver on a new state, poll the running job."""
        key = self._state_key()
        if key != self._last_state_key:
            self._last_state_key = key
            self._kick_ai_for_state()
        # Poll the offline solver job on the main thread (never blocks PyGame).
        if self.ai_job is not None and not self.ai_job.running:
            job_key = self.ai_job_state_key
            current_key = self._state_key()
            if self.ai_job.error is not None:
                if job_key == current_key:
                    self.ai_status = "error"
                    self.ai_message = f"Solver Error: {self.ai_job.error}"
            else:
                if job_key == current_key:
                    self.ai_best_by_state[job_key] = self.ai_job.result
                    self.ai_result = self.ai_job.result
                    self.ai_status = "ready"
                    self.ai_message = (self.ai_job.result.message
                                       if self.ai_job.result is not None else "")
            self.ai_job = None
            self.ai_job_state_key = None

    def _update_flight(self, dt):
        if self.banner:
            title, sub, left = self.banner
            self.banner = (title, sub, left - dt) if left > dt else None

        if self.state == FLIGHT:
            try:
                outcome = self.flight.advance(dt, on_step=self._record_replay_frame)
            except _PHYSICS_ERRORS as exc:
                log.warning("flight advance (%s) -> DIVERGED: %r", type(exc).__name__, exc)
                outcome = Outcome.DIVERGED
                self.flight.outcome = Outcome.DIVERGED
            except Exception:  # noqa: BLE001 - internal bug vs DIVERGED must be loud
                log.exception("unexpected flight failure; forcing DIVERGED")
                outcome = Outcome.DIVERGED
                try:
                    self.flight.outcome = Outcome.DIVERGED
                except _RENDER_ERRORS:
                    pass
            try:
                self._sync_trail()
            except _RENDER_ERRORS as exc:
                log.warning("trail sync contained: %r", exc)
            except Exception:  # noqa: BLE001 - last-resort guard: frame loop must live
                log.exception("unexpected trail-sync failure")
            self._play_flight_sounds()
            try:
                self._drain_pickup_events()
            except _RENDER_ERRORS as exc:
                log.warning("pickup sync contained: %r", exc)
            except Exception:  # noqa: BLE001 - last-resort guard: frame loop must live
                log.exception("unexpected pickup-sync failure")
            if outcome is not Outcome.RUNNING:
                self._safe_end_flight(outcome)
        elif self.state == PANNING:
            self.pan.t += dt
            if self.pan.t >= config.CHECKPOINT_PAN_DURATION:
                self._finish_pan()
        elif self.state == ARRIVED:
            self.arrive_timer -= dt
            if self.arrive_timer <= 0:
                self.session.stats = {
                    "time": self.flight.time,
                    "total_time": self.total_time,
                    "attempts": self.attempts,
                    "lives_left": self.lives,
                    "max_lives": self.level.lives,
                    "fx": self.editor.lines[0].strip() or "0",
                    "fy": self.editor.lines[1].strip() or "0",
                    "solution_used": self.solution_used,
                    "clear_reward": self._clear_reward,
                    "coins_earned": (sum(amount for _key, amount in self._run_coins)
                                     + self._clear_reward),
                }
                from .win import WinScene
                self.manager.switch(WinScene(self.manager, self._snapshot()))

    def _record_replay_frame(self, flight=None):
        try:
            flight = flight or self.flight
            x, y, vx, vy = flight.x, flight.y, flight.vx, flight.vy
            force = getattr(flight, "_step_force", None)
            fx, fy = force if force is not None else flight.force
            frame = {
                "t": float(getattr(flight, "time", 0.0)),
                "x": float(x), "y": float(y),
                "vx": float(vx), "vy": float(vy),
                "fx": float(fx), "fy": float(fy),
            }
            teleports = getattr(flight, "teleports", 0)
            if teleports > self._replay_teleports:
                frame["warp"] = True
                self._replay_teleports = teleports
            self._replay_frames.append(frame)
        except Exception:
            pass

    # ------------------------------------------------------------------ draw

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
