"""Field guide: what every rock, portal and pickup does, shown as a looping clip.

The tutorial screen's element list opens an item in a small popup
(tutorial_screen.DemoPopup); the popup plays it with GuideDemoScene: the
ordinary game screen (same physics, drawing and pickup effects) flying a
fixed force. Only the map is drawn - never the formulas; the popup shows
the item's name, its text, which part is playing and, for show_timer, the
clock. A clip runs until its time cap (or until the flight ends), holds a
moment and plays again; an item with several parts plays them one after
another. Nothing in a clip counts for coins, progress, replays or
achievements (TutorialGameScene).
"""

import pygame

from .. import config, sprites
from ..config import px
from . import pickup_effects as pfx
from .game_layout import FLIGHT, SETUP
from .tutorial_play import TutorialGameScene

HOLD = "guide_hold"             # a clip ended: its last frame stays this long
HOLD_S = 0.5
START_DELAY_S = 0.3             # the first clip starts this long after opening


# --- the clip ------------------------------------------------------------------------------
class GuideDemoScene(TutorialGameScene):

    def __init__(self, manager, item, restore=None):
        self.item = item
        self.part_index = 0
        self.hold_left = 0.0
        self.start_wait = START_DELAY_S
        self.timer_target = None        # where a "+N" flies to: the clock the popup shows
        part = item.parts[0]
        super().__init__(manager, part.map.level(item.name), part.force[0], part.force[1], restore)

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

    def handle_event(self, event):
        pass                            # the clip plays on its own

    # --- drawing -----------------------------------------------------------------------
    def _fly_target(self, target):
        if target == pfx.TIMER:
            if self.timer_target is not None:
                return self.timer_target
            plot = pygame.Rect(self.camera.rect)
            return (plot.right - px(60), plot.y + px(40))
        return super()._fly_target(target)

    def _draw_section(self, surface, level, pickups, holes, offset, **kwargs):
        # A clip without a planet: the map's props only (its target is far off-map).
        kwargs.setdefault("target", self.part.map.has_target)
        super()._draw_section(surface, level, pickups, holes, offset, **kwargs)

    def draw(self, surface):
        """The clip only: the map, its effects and the "+N" texts (never the formulas)."""
        surface.fill(config.BG)
        self._draw_plot(surface)
        self._draw_fly_texts(surface)


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
