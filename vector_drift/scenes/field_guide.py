"""Field guide: what every rock, portal and pickup does.

FieldGuideScene is the page of cards, one section per category of
tutorial.toml's [guide]. Opening a card plays its clip in GuideDemoScene:
the ordinary game screen (same physics, drawing and pickup effects) flying
a fixed force, with the left panel showing the item's name and text instead
of the formulas. A clip runs until its time cap (or until the flight ends),
holds a moment and plays again; an item with several parts plays them one
after another. Nothing in the Field guide counts for coins, progress,
replays or achievements (TutorialGameScene).
"""

import pygame

from .. import config, render, sprites
from ..config import px
from ..tutorial import tutorial
from ..ui import Button, draw_text, wrap_text
from . import pickup_effects as pfx
from .base import Scene
from .game_layout import CX, FLIGHT, LOGO_W, LOGO_Y, SETUP, fmt_clock
from .tutorial_play import TutorialGameScene, borrow_session

HOLD = "guide_hold"             # a clip ended: its last frame stays this long
HOLD_S = 0.5
START_DELAY_S = 0.3             # the first clip starts this long after opening
NAME_Y, TEXT_Y, PART_Y, CLOCK_Y = 140, 190, 330, 380      # left panel (logical px)
TEXT_SIZE = 17

# Card grid (logical px)
CARD_W, CARD_H, CARD_GAP = 170, 120, 20
HEADER_H = 30                   # section name above its cards
SECTION_GAP = 28
GRID_TOP = 140
ICON_R = 28


def back_to_tutorial_menu(manager):
    """Leaving the Field guide: level select with the Tutorial menu open."""
    from .levels import LevelSelectScene
    try:
        return LevelSelectScene(manager, tutorial_menu=True)
    except TypeError:                   # (before the Tutorial menu exists)
        return LevelSelectScene(manager)


# --- the clip ------------------------------------------------------------------------------
class GuideDemoScene(TutorialGameScene):

    def __init__(self, manager, item, restore=None):
        self.item = item
        self.part_index = 0
        self.hold_left = 0.0
        self.start_wait = START_DELAY_S
        part = item.parts[0]
        super().__init__(manager, part.map.level(item.name), part.force[0], part.force[1], restore)
        self.back_button = Button((px(20), config.WINDOW_H - px(66), px(120), px(44)), "Back",
                                  style="plain", font_size=17)

    @property
    def part(self):
        return self.item.parts[self.part_index]

    # --- the loop ----------------------------------------------------------------------
    def _end_flight(self, outcome):
        """The flight ended before the cap: hold on its last frame (no miss, no banner)."""
        self.audio.stop_loop("thruster_loop")
        self._sync_trail()
        self._hold()

    def _hold(self):
        self.audio.stop_loop("thruster_loop")
        self.state = HOLD
        self.hold_left = HOLD_S
        self._refresh_buttons()

    def _update_flight(self, dt):
        if self.state == HOLD:
            self.hold_left -= dt
            if self.hold_left <= 0:
                self._next_clip()
            return
        if self.state == FLIGHT and self.flight is not None and self.flight.running:
            # Never fly past the cap, even on a long frame.
            dt = max(0.0, min(dt, self.part.cap - self.flight.time + 1e-9))
        super()._update_flight(dt)
        flight = self.flight
        if self.state == FLIGHT and flight is not None and flight.running \
                and flight.time >= self.part.cap - 1e-9:
            self._sync_trail()
            self._hold()

    def _next_clip(self):
        """Play the next part (or this one again): the map exactly as at the start."""
        self.part_index = (self.part_index + 1) % len(self.item.parts)
        part = self.part
        self._tutorial_level = part.map.level(self.item.name)
        self.full_level = self.level = self._tutorial_level
        self._load_section_props()
        self.flight = None
        self.launch_pos = self.level.start
        self.trail.clear()
        self._trail_count = 0
        self._clear_history()
        self.pickup_fx.clear()
        self.ability_fx.clear()
        self.banner = None
        self.camera.zoom = 1.0
        self.state = SETUP
        if list(part.force) != list(self.editor.lines):
            self.editor.set_lines(list(part.force), record=False)
            self.session.fx_text, self.session.fy_text = part.force
        self._validate()
        self.heading = self._heading_to_target()
        self._try_launch()

    def _camera_target(self):
        if self.state == HOLD:          # keep the view the clip ended on
            return self.camera.zoom, self.camera.zoom
        return super()._camera_target()

    def update(self, dt):
        super().update(dt)
        if self.flight is None and self.state == SETUP:
            self.start_wait -= dt
            if self.start_wait <= 0:
                self._try_launch()

    # --- input -------------------------------------------------------------------------
    def leave_to_guide(self):
        self.leave(FieldGuideScene(self.manager, restore=self.restore))

    def handle_event(self, event):
        if self.back_button.handle_event(event) == "click" or (
                event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
            self.audio.play("click")
            self.leave_to_guide()
        # Nothing else: the clip plays on its own.

    # --- drawing -----------------------------------------------------------------------
    def _fly_target(self, target):
        if target == pfx.TIMER:
            return (px(CX), px(CLOCK_Y))
        return super()._fly_target(target)

    def _draw_section(self, surface, level, pickups, holes, offset, **kwargs):
        # A clip without a planet: the map's props only (its target is far off-map).
        kwargs.setdefault("target", self.part.map.has_target)
        super()._draw_section(surface, level, pickups, holes, offset, **kwargs)

    def _draw_panel(self, surface):
        panel = pygame.Rect(0, 0, config.PANEL_W, config.WINDOW_H)
        pygame.draw.rect(surface, config.PANEL_BG, panel)
        pygame.draw.line(surface, config.PANEL_EDGE, panel.topright, panel.bottomright, max(2, px(2)))
        cx = px(CX)
        if not sprites.draw_logo(surface, (cx, px(LOGO_Y)), px(LOGO_W)):
            draw_text(surface, "VECTOR DRIFT", (cx, px(LOGO_Y)), 26, config.TEXT, kind="bold",
                      anchor="center")
        draw_text(surface, "FIELD GUIDE", (cx, px(NAME_Y - 36)), 13, config.TEXT_DIM, kind="bold",
                  anchor="center")
        draw_text(surface, self.item.name, (cx, px(NAME_Y)), 24, config.TEXT, kind="bold",
                  anchor="center")
        y = px(TEXT_Y)
        for line in wrap_text(self.part.text, TEXT_SIZE, px(270)):
            draw_text(surface, line, (cx, y), TEXT_SIZE, config.TEXT, anchor="midtop")
            y += px(TEXT_SIZE + 8)
        if len(self.item.parts) > 1:
            draw_text(surface, f"{self.part_index + 1} / {len(self.item.parts)}", (cx, px(PART_Y)), 14,
                      config.TEXT_DIM, anchor="center")
        if self.part.show_timer:
            time_left = self._shown_time_left()
            color = config.WARNING if self.state == FLIGHT and time_left < 1.0 else config.TEXT
            if self.pickup_fx.popping(pfx.TIMER):
                color = pfx.EXTRATIME_COLOR
            draw_text(surface, fmt_clock(time_left), (cx, px(CLOCK_Y)),
                      round(30 * self.pickup_fx.pop_scale(pfx.TIMER)), color, kind="mono",
                      anchor="center")
        self.back_button.draw(surface)


# --- the page of cards ----------------------------------------------------------------------
class FieldGuideScene(Scene):
    music = "menu"

    def __init__(self, manager, restore=None):
        super().__init__(manager)
        self.restore = restore if restore is not None else borrow_session(self.session)
        self.background = render.make_space_background((config.WINDOW_W, config.WINDOW_H), seed=11,
                                                       star_count=220)
        self.t = 0.0
        self.hover = None
        self.cards = []                 # (item, rect)
        self.headers = []               # (name, (x, y))
        self._layout()
        self.back_button = Button((px(40), config.WINDOW_H - px(86), px(160), px(46)), "Back",
                                  style="plain", font_size=17)

    def _layout(self):
        y = GRID_TOP
        for cat in tutorial().guide:
            self.headers.append((cat.name, (px(config.BASE_W // 2), px(y))))
            y += HEADER_H
            n = len(cat.items)
            row_w = n * CARD_W + (n - 1) * CARD_GAP
            x = (config.BASE_W - row_w) // 2
            for item in cat.items:
                self.cards.append((item, pygame.Rect(px(x), px(y), px(CARD_W), px(CARD_H))))
                x += CARD_W + CARD_GAP
            y += CARD_H + SECTION_GAP

    def open(self, item):
        self.audio.play("click")
        self.manager.switch(GuideDemoScene(self.manager, item, restore=self.restore))

    def leave(self):
        self.audio.play("click")
        from .tutorial_play import give_back_session
        give_back_session(self.session, self.restore)
        self.manager.switch(back_to_tutorial_menu(self.manager))

    def handle_event(self, event):
        if self.back_button.handle_event(event) == "click":
            self.leave()
            return
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.leave()
        elif event.type == pygame.MOUSEMOTION:
            self.hover = next((item for item, r in self.cards if r.collidepoint(event.pos)), None)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for item, rect in self.cards:
                if rect.collidepoint(event.pos):
                    self.open(item)
                    return

    def update(self, dt):
        self.t += dt

    def draw(self, surface):
        surface.blit(self.background, (0, 0))
        draw_text(surface, "FIELD GUIDE", (config.WINDOW_W // 2, px(64)), 40, config.TEXT, kind="bold",
                  anchor="center")
        draw_text(surface, "What every rock, portal and pickup does", (config.WINDOW_W // 2, px(104)), 16,
                  config.TEXT_DIM, anchor="center")
        for name, pos in self.headers:
            draw_text(surface, name, pos, 18, config.ACCENT, kind="bold", anchor="midtop")
        for item, rect in self.cards:
            self._draw_card(surface, item, rect)
        self.back_button.draw(surface)

    def _draw_card(self, surface, item, rect):
        hover = self.hover is item
        pygame.draw.rect(surface, config.EDITOR_LINE_HL if hover else config.PANEL_BG, rect,
                         border_radius=px(6))
        pygame.draw.rect(surface, config.ACCENT if hover else config.EDITOR_BORDER, rect,
                         max(2, px(2)) if hover else max(1, px(1)), border_radius=px(6))
        draw_card_icon(surface, item.icon, (rect.centerx, rect.y + px(48)), px(ICON_R), self.t)
        draw_text(surface, item.name, (rect.centerx, rect.bottom - px(20)), 15, config.TEXT,
                  kind="bold", anchor="center")


def draw_card_icon(surface, icon, center, radius, t=0.0):
    """The card's picture, drawn with the game's own sprites."""
    if icon == "rock":
        sprites.draw_obstacle(surface, center, radius, t, seed=0)
    elif icon == "holes":
        r = round(radius * 0.62)
        sprites.draw_hole(surface, (center[0] - r - px(6), center[1]), r, t, "black", 1)
        sprites.draw_hole(surface, (center[0] + r + px(6), center[1]), r, t, "white", 1)
    else:
        sprites.draw_pickup(surface, center, radius, t, kind=icon)
