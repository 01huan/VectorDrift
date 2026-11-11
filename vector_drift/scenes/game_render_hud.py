"""Left-panel rendering for GameScene: level row, ship, lives, clock, telemetry."""
import math
import sys as _sys

import pygame

from .. import config, render, sprites
from ..config import px
from ..ui import draw_panel_box, icon_surface
from . import pickup_effects as pfx
from .game_layout import (
    ARRIVED, CX, FLIGHT, LEGEND_LABEL_Y, LEGEND_Y, LEVEL_ROW_Y, LOGO_W,
    LOGO_Y, SHIP_BOX, SHIP_LABEL_Y, SHIP_MASS_Y, SHIP_NAME_Y, STATUS_Y,
    TELEMETRY_ROW_H, fmt_clock, fmt_pair,
)


def _gm():
    return _sys.modules["vector_drift.scenes.game"]


def draw_text(*a, **k):
    return _gm().draw_text(*a, **k)


class GameHudRenderMixin:

    # ------------------------------------------------------------------ left panel
    def _draw_panel(self, surface):
        panel = pygame.Rect(0, 0, config.PANEL_W, config.WINDOW_H)
        pygame.draw.rect(surface, config.PANEL_BG, panel)
        pygame.draw.line(surface, config.PANEL_EDGE, panel.topright, panel.bottomright, max(2, px(2)))
        cx = px(CX)

        if not sprites.draw_logo(surface, (cx, px(LOGO_Y)), px(LOGO_W)):
            draw_text(surface, "VECTOR DRIFT", (cx, px(LOGO_Y)), 26, config.TEXT, kind="bold", anchor="center")

        # Level row: "LV1" + level-select button
        draw_text(surface, f"LV{self.level.id}", (px(CX - 26), px(LEVEL_ROW_Y)), 22, config.TEXT,
                  kind="bold", anchor="center")
        self.level_button.draw(surface)

        # Current ship
        draw_text(surface, "Current ship", (cx, px(SHIP_LABEL_Y)), 15, config.TEXT_DIM, anchor="center")
        draw_panel_box(surface, SHIP_BOX, fill=config.BG)
        unlocked = self._ship_unlocked
        sprites.draw_ship(surface, SHIP_BOX.center, math.pi / 4 + 0.12 * math.sin(self.t * 1.3),
                          px(76), self.ship, grey=not unlocked)
        if not unlocked:
            lock = icon_surface("lock", px(22), config.TEXT_DIM)
            surface.blit(lock, lock.get_rect(bottomright=(SHIP_BOX.right - px(6), SHIP_BOX.bottom - px(6))))
        self.prev_ship.draw(surface)
        self.next_ship.draw(surface)
        draw_text(surface, self.ship.name, (cx, px(SHIP_NAME_Y)), 18,
                  config.TEXT if unlocked else config.TEXT_DIM, kind="bold", anchor="center")
        if unlocked:
            draw_text(surface, f"Mass: {self.ship.mass:g} kg", (cx, px(SHIP_MASS_Y)), 15, config.TEXT_DIM,
                      anchor="center")
        else:
            draw_text(surface, f"Lv{self.ship.unlock_level}+", (cx, px(SHIP_MASS_Y)), 15, config.WARNING,
                      kind="bold", anchor="center")

        # Lives + clock (the lives show the ship that would fly, not a locked one on display)
        icon_step = px(18)
        first = px(CX - 52) - icon_step * (self.level.lives - 1) // 2
        for i in range(self.level.lives):
            # A life pickup's newly lit icon jumps.
            size = round(px(18) * self.pickup_fx.pop_scale(pfx.LIFE, i))
            sprites.draw_ship_icon(surface, (first + i * icon_step, px(STATUS_Y)), size,
                                   self.flyable_ship, alive=i < self.lives)
        time_left = self._shown_time_left()
        time_color = config.WARNING if self.state == FLIGHT and time_left < 1.0 else config.TEXT
        if self.pickup_fx.popping(pfx.TIMER):
            time_color = pfx.EXTRATIME_COLOR        # extratime arrived: green flash
        draw_text(surface, fmt_clock(time_left), (px(CX + 62), px(STATUS_Y)),
                  round(24 * self.pickup_fx.pop_scale(pfx.TIMER)), time_color,
                  kind="mono", anchor="center")

        # Vector_field / PROBLEMS / TELEMETRY panel
        self.editor.draw(surface)
        self.run_button.draw(surface)
        self._draw_telemetry(surface, self.editor.footer_body)

        # Longest arrow legend
        draw_text(surface, "Longest arrow", (cx, px(LEGEND_LABEL_Y)), 14, config.TEXT_DIM, anchor="center")
        render.draw_legend(surface, (cx, px(LEGEND_Y)), self.max_force)

        if self.hint_mode:
            # Hint button (fixed levels): usable any time before the win.
            self.ai_button.enabled = self.hint is not None and self.state != ARRIVED
            self.ai_button.label = "Hint"
        else:
            # AI assistant button (offline solver): always open, solving is free.
            self.ai_button.enabled = True
            self.ai_button.label = ("AI Solver" if self.ai_status != "error"
                                    else "AI Solver (Failed)")
        self.ai_button.draw(surface)

    def _draw_telemetry(self, surface, area):
        in_flight = self.flight is not None
        x, y, vx, vy, fx, fy = self._ship_state()
        rows = [
            ("Position", fmt_pair(x, y, "m"), config.TEXT),
            ("Velocity", fmt_pair(vx, vy, "m/s"), config.VELOCITY_VEC),
            ("Speed", f"{math.hypot(vx, vy):.2f} m/s", config.VELOCITY_VEC),
            ("Force", fmt_pair(fx, fy, "N"), config.FORCE_VEC),
        ]
        for i, (label, value, color) in enumerate(rows):
            ry = area.y + px(TELEMETRY_ROW_H * i + TELEMETRY_ROW_H // 2 + 2)
            draw_text(surface, label, (area.x + px(12), ry), 13, config.TEXT_DIM, anchor="midleft")
            if not in_flight:
                value, color = "—", config.TEXT_FAINT
            draw_text(surface, value, (area.right - px(12), ry), 13, color, kind="mono", anchor="midright")
