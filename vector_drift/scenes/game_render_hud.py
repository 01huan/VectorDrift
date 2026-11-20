"""Left-panel rendering for GameScene: level row, ship, lives, clock, telemetry."""
import math
import sys as _sys

import pygame

from .. import config, render, sprites
from ..abilities import all_abilities, charge_count
from ..ability_icons import draw_ability_icon
from ..config import px
from ..daily_level import is_daily_level
from ..data import level_number
from ..ui import draw_panel_box, get_font, wrap_text
from . import pickup_effects as pfx
from .game_layout import (
    ABILITY_EMPTY_ALPHA, ABILITY_ICON, ABILITY_LABEL_Y, ARRIVED, CX, FLIGHT, LEGEND_LABEL_Y,
    LEGEND_Y, LEVEL_ROW_Y, LOGO_W, LOGO_Y, PAD, SHIP_BOX, SHIP_MASS_Y, SHIP_NAME_Y,
    SHIP_TEXT_X, STATUS_Y, TELEMETRY_ROW_H, ability_slot_rects, fmt_clock, fmt_pair,
)

TOOLTIP_W = 240              # logical px: the ability tooltip's width
TOOLTIP_PAD = 10


def _gm():
    return _sys.modules["vector_drift.scenes.game"]


def draw_text(*a, **k):
    return _gm().draw_text(*a, **k)


SLOT_TEXT_OUTLINE = (6, 9, 20)


def _outlined(surface, text, pos, size, color, anchor):
    """Small bold text with a dark 1 px outline, readable over an icon."""
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, 1), (-1, 1), (1, -1)):
        draw_text(surface, text, (pos[0] + dx, pos[1] + dy), size, SLOT_TEXT_OUTLINE, kind="bold",
                  anchor=anchor)
    draw_text(surface, text, pos, size, color, kind="bold", anchor=anchor)


class GameHudRenderMixin:
    # Tutorial scenes hide these (lives row; Hint / AI Solver and Lab buttons;
    # the ability slots, since abilities do nothing there).
    show_lives = True
    show_assists = True
    show_level_row = True
    show_abilities = True

    # ------------------------------------------------------------------ left panel
    def level_label(self):
        """The level row's text: "LV<number>", or "DAILY" on the daily challenge."""
        if is_daily_level(self.level.id):
            return "DAILY"
        return f"LV{level_number(self.level.id)}"

    def _draw_panel(self, surface):
        panel = pygame.Rect(0, 0, config.PANEL_W, config.WINDOW_H)
        pygame.draw.rect(surface, config.PANEL_BG, panel)
        pygame.draw.line(surface, config.PANEL_EDGE, panel.topright, panel.bottomright, max(2, px(2)))
        cx = px(CX)

        if not sprites.draw_logo(surface, (cx, px(LOGO_Y)), px(LOGO_W)):
            draw_text(surface, "VECTOR DRIFT", (cx, px(LOGO_Y)), 26, config.TEXT, kind="bold", anchor="center")

        # Level row: "LV1" + level-select button (the number shown, not the id)
        if self.show_level_row:
            draw_text(surface, self.level_label(), (px(CX - 26), px(LEVEL_ROW_Y)), 22, config.TEXT,
                      kind="bold", anchor="center")
            self.level_button.draw(surface)

        # Ship row: the level's ship in a small frame, its name and mass beside it.
        draw_panel_box(surface, SHIP_BOX, fill=config.BG)
        sprites.draw_ship(surface, SHIP_BOX.center, math.pi / 4 + 0.12 * math.sin(self.t * 1.3),
                          px(40), self.ship)
        draw_text(surface, self.ship.name, (px(SHIP_TEXT_X), px(SHIP_NAME_Y)), 18, config.TEXT,
                  kind="bold", anchor="midleft")
        draw_text(surface, f"Mass: {self.ship.mass:g} kg", (px(SHIP_TEXT_X), px(SHIP_MASS_Y)), 15,
                  config.TEXT_DIM, anchor="midleft")

        # Lives + clock
        icon_step = px(18)
        first = px(CX - 52) - icon_step * (self.level.lives - 1) // 2
        for i in range(self.level.lives if self.show_lives else 0):
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

        if self.show_abilities:
            self._draw_ability_slots(surface)

        # Vector_field / PROBLEMS / TELEMETRY panel
        self.editor.draw(surface)
        self.run_button.draw(surface)
        self._draw_telemetry(surface, self.editor.footer_body)

        # Longest arrow legend
        draw_text(surface, "Longest arrow", (cx, px(LEGEND_LABEL_Y)), 14, config.TEXT_DIM, anchor="center")
        render.draw_legend(surface, (cx, px(LEGEND_Y)), self.max_force)

        if not self.show_assists:
            return
        if self.daily_answer:
            # Answer button (daily map): like Hint, usable any time before the win.
            self.ai_button.enabled = self.state != ARRIVED
            self.ai_button.label = "Answer"
        elif self.hint_mode:
            # Hint button (fixed levels): usable any time before the win.
            self.ai_button.enabled = self.hint is not None and self.state != ARRIVED
            self.ai_button.label = "Hint"
        else:
            # AI assistant button (offline solver): always open, solving is free.
            self.ai_button.enabled = True
            self.ai_button.label = ("AI Solver" if self.ai_status != "error"
                                    else "AI Solver (Failed)")
        self.ai_button.draw(surface)
        self.lab_button.draw(surface)

    # ------------------------------------------------------------------ abilities
    def _ability_slots(self):
        """[(ability, real-px rect)] in shop order: every ability, owned or not."""
        abilities = all_abilities()
        return list(zip(abilities, ability_slot_rects(len(abilities))))

    def _draw_ability_slots(self, surface):
        draw_text(surface, "ABILITIES", (px(PAD), px(ABILITY_LABEL_Y)), 11, config.TEXT_DIM,
                  kind="bold", anchor="midleft")
        for ability, rect in self._ability_slots():
            count = charge_count(self.session, ability.id)
            slot = pygame.Surface(rect.size, pygame.SRCALPHA)
            local = slot.get_rect()
            draw_panel_box(slot, local, fill=config.BG)
            draw_ability_icon(slot, ability.id, local.center, px(ABILITY_ICON))
            _outlined(slot, ability.key, (px(3), px(1)), 9, config.TEXT, "topleft")
            _outlined(slot, str(count), (local.right - px(3), local.bottom), 11,
                      config.TEXT if count else config.TEXT_DIM, "bottomright")
            if count <= 0:
                slot.set_alpha(ABILITY_EMPTY_ALPHA)
            surface.blit(slot, rect)

    def _hovered_ability(self):
        if not self.show_abilities:
            return None
        pos = getattr(self, "_mouse_pos", (-1, -1))
        for ability, rect in self._ability_slots():
            if rect.collidepoint(pos):
                return ability, rect
        return None

    def _draw_ability_tooltip(self, surface):
        """Name and description of the ability slot under the mouse."""
        if (self.pause_menu is not None or self.hint_popup is not None or self.ai_popup
                or getattr(self, "lab_popup", False)):
            return
        hovered = self._hovered_ability()
        if hovered is None:
            return
        ability, slot = hovered
        width = px(TOOLTIP_W)
        lines = wrap_text(ability.description, 13, width - px(2 * TOOLTIP_PAD))
        name_h = get_font(14, "bold").get_height()
        line_h = get_font(13).get_height()
        box = pygame.Rect(0, 0, width, px(2 * TOOLTIP_PAD + 4) + name_h + line_h * len(lines))
        box.topleft = (slot.x, slot.bottom + px(6))
        box.right = min(box.right, config.WINDOW_W - px(4))
        box.left = max(box.left, px(4))
        pygame.draw.rect(surface, config.PANEL_BG, box, border_radius=px(5))
        pygame.draw.rect(surface, config.ACCENT, box, width=max(1, px(1)), border_radius=px(5))
        x, y = box.x + px(TOOLTIP_PAD), box.y + px(TOOLTIP_PAD)
        draw_text(surface, f"{ability.name} ({ability.key})", (x, y), 14, config.TEXT, kind="bold")
        y += name_h + px(4)
        for line in lines:
            draw_text(surface, line, (x, y), 13, config.TEXT_DIM)
            y += line_h

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
