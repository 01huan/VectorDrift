"""Level select: playable levels plus locked placeholders, and a way back to the main menu."""

import time

import pygame

from .. import config, render
from ..config import px
from ..data import all_levels, is_custom_level
from ..level_pages import (PER_PAGE, can_next, can_prev, clamp_page, levels_on_page,
                           page_count, restore_page, wheel_step)
from ..level_presets import get_preset, is_dynamic_level
from ..image_assets import COIN_BALANCE
from ..ui import Button, draw_coins, draw_text, icon_surface, wrap_text
from .base import Scene, InventoryMixin

CARDS_PER_PAGE = PER_PAGE    # 3x3 grid, every slot a level card
COLS = 3
CARD_W, CARD_H, GAP = 220, 150, 30
GRID_TOP = 180               # base px; leaves room for the page dots below the grid
TUTORIAL_LABEL = "Tutorial"  # replays the intro story (scenes/story.py)

# Page arrows (base px). Each "<" / ">" is a drawn chevron at a screen side,
# vertically centred on the grid; the click area is a tall strip around it.
# The strips (y 255..615) stay clear of Main Menu (bottom left, y >= 634) and
# of Shop / the inventory icon (top right, y <= 97).
ARROW_MARGIN = 12            # gap from the screen edge to the strip
ARROW_HIT_W, ARROW_HIT_H = 72, 360
ARROW_W, ARROW_H = 22, 48    # the chevron itself
ARROW_STROKE = 7
ARROW_DISABLED_ALPHA = 72    # about 28 % opacity
DOT_R, DOT_GAP = 4, 18       # page dots: radius and centre spacing
DOTS_BELOW_GRID = 14         # from the grid bottom to the dots' centre


def grid_origin():
    """Top-left of the 3x3 card grid, in base px."""
    grid_w = COLS * CARD_W + (COLS - 1) * GAP
    return (config.BASE_W - grid_w) // 2, GRID_TOP


def _grid_size():
    rows = -(-CARDS_PER_PAGE // COLS)
    return COLS * CARD_W + (COLS - 1) * GAP, rows * CARD_H + (rows - 1) * GAP


def _arrow_rect(direction):
    """Click strip of the "<" (direction -1) or ">" (+1) arrow, in screen px."""
    _, top = grid_origin()
    _, grid_h = _grid_size()
    rect = pygame.Rect(0, 0, px(ARROW_HIT_W), px(ARROW_HIT_H))
    rect.centery = px(top + grid_h / 2)
    if direction < 0:
        rect.left = px(ARROW_MARGIN)
    else:
        rect.right = config.WINDOW_W - px(ARROW_MARGIN)
    return rect


class PageArrow:
    """A drawn chevron beside the grid that turns the page.

    Disabled (no page that way): drawn faint, no hover, clicks do nothing.
    """

    def __init__(self, direction, rect):
        self.direction = direction      # -1: "<" previous page, +1: ">" next page
        self.rect = rect
        self.enabled = False
        self.hover = False

    def update_hover(self, pos):
        self.hover = self.enabled and self.rect.collidepoint(pos)

    def glyph_rect(self):
        glyph = pygame.Rect(0, 0, px(ARROW_W), px(ARROW_H))
        glyph.center = self.rect.center
        return glyph

    def color(self):
        return config.TEXT if self.hover else config.TEXT_DIM

    def draw(self, surface, k=3):
        """Supersampled chevron (like render.draw_smooth_arrow), then scaled down."""
        glyph = self.glyph_rect()
        stroke = max(2, px(ARROW_STROKE))
        pad = stroke
        w, h = glyph.w + 2 * pad, glyph.h + 2 * pad
        big = pygame.Surface((w * k, h * k), pygame.SRCALPHA)
        near, far = pad * k, (pad + glyph.w) * k
        tip_x, back_x = (near, far) if self.direction < 0 else (far, near)
        points = [(back_x, pad * k), (tip_x, (pad + glyph.h / 2) * k), (back_x, (pad + glyph.h) * k)]
        color = self.color()
        pygame.draw.lines(big, color, False, points, stroke * k)
        for point in points:            # round joint and caps
            pygame.draw.circle(big, color, point, stroke * k / 2)
        small = pygame.transform.smoothscale(big, (w, h))
        if not self.enabled:
            small.set_alpha(ARROW_DISABLED_ALPHA)
        surface.blit(small, small.get_rect(center=self.rect.center))


class LevelSelectScene(InventoryMixin, Scene):
    music = "menu"

    def __init__(self, manager):
        super().__init__(manager)
        self.background = render.make_space_background((config.WINDOW_W, config.WINDOW_H), seed=5,
                                                       star_count=260)
        self.levels = {lv.id: lv for lv in all_levels()}
        # Level-select pages are driven by planned/base levels only.  Custom
        # (player-created / community) IDs live in their own registry and must
        # never extend this 1..N range or leak state between runs/tests.
        custom_ids = set(getattr(self.manager.session, "custom_level_ids", ())) 
        base_level_ids = [
            lv.id for lv in all_levels()
            if not is_custom_level(lv.id) and lv.id not in custom_ids
        ]
        highest = max(max(base_level_ids, default=0), config.PLANNED_LEVELS)
        self.level_ids = list(range(1, highest + 1))
        # Back on the page the player left, or on the page of the level they
        # played on to (level_pages.restore_page).
        self.page = restore_page(getattr(self.session, "level_select_page", None),
                                 getattr(self.session, "level_id", None), self.level_ids)
        self.hover = None
        self._init_inventory()
        self.cards = []
        self.prev_arrow = PageArrow(-1, _arrow_rect(-1))
        self.next_arrow = PageArrow(1, _arrow_rect(1))
        self._last_wheel = None     # time of the last wheel event (one gesture, one page)
        self.menu_button = Button((px(40), config.WINDOW_H - px(86), px(180), px(46)), "Main Menu",
                                  style="plain", font_size=17)
        self.shop_button = Button((config.WINDOW_W - px(180), px(20), px(160), px(40)), "Shop",
                                 style="primary", font_size=17)
        self.editor_button = Button((config.WINDOW_W - px(360), px(20), px(160), px(40)), "Level Editor",
                                   style="plain", font_size=17)
        self.tutorial_button = Button((config.WINDOW_W - px(540), px(20), px(160), px(40)), TUTORIAL_LABEL,
                                     style="plain", font_size=17)
        self._rebuild_cards()

    def _start(self, level_id):
        self.audio.play("click")
        self.session.level_id = level_id
        self.session.level_select_page = (self.page, level_id)
        self.session.fx_text = self.session.fy_text = ""
        self.session.editor_history = None      # a new start: no undo into another run
        self.session.ship_id = None             # start on the level's newest ship
        # Fresh solvable layout for dynamic levels on every entry; static
        # levels always come from get_level().
        self.session.random_seed = None
        self.session.level_source = "levels"
        if is_dynamic_level(level_id):
            import random as _random
            self.session.random_seed = _random.SystemRandom().randint(0, 2 ** 31 - 1)
        from .game import GameScene
        self.manager.switch(GameScene(self.manager))

    def _to_menu(self):
        self.audio.play("click")
        from .menu import MenuScene
        self.manager.switch(MenuScene(self.manager))

    def _open_shop(self):
        self.audio.play("click")
        from .shop import ShopScene
        self.manager.switch(ShopScene(self.manager))

    def _open_tutorial(self):
        self.audio.play("click")
        from .story import StoryScene
        self.manager.switch(StoryScene(self.manager))

    def handle_event(self, event):
        if self._handle_inventory_event(event):
            return
        if event.type == pygame.MOUSEMOTION:
            self.hover = next((lid for lid, r in self.cards if r.collidepoint(event.pos)), None)
            self.prev_arrow.update_hover(event.pos)
            self.next_arrow.update_hover(event.pos)
            self.shop_button.handle_event(event)
            self.editor_button.handle_event(event)
            self.tutorial_button.handle_event(event)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for lid, rect in self.cards:
                if rect.collidepoint(event.pos):
                    if lid in self.levels:
                        self._start(lid)
                    else:
                        self.audio.play("error")
                    return
            for arrow in (self.prev_arrow, self.next_arrow):
                if arrow.rect.collidepoint(event.pos):
                    self._turn(arrow.direction)     # a disabled arrow does nothing
                    return
            if self.shop_button.handle_event(event) == "click":
                self._open_shop()
                return
            if self.tutorial_button.handle_event(event) == "click":
                self._open_tutorial()
                return
            if self.editor_button.handle_event(event) == "click":
                self.audio.play("click")
                from .level_editor_menu import LevelEditorMenuScene
                self.manager.switch(LevelEditorMenuScene(self.manager))
                return
        elif event.type == pygame.MOUSEWHEEL:
            step, self._last_wheel = wheel_step(event.y, self._now(), self._last_wheel)
            if step:
                self._turn(step)
            return
        elif event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_LEFT, pygame.K_RIGHT):
                self._turn(-1 if event.key == pygame.K_LEFT else 1)
                return
            if event.key == pygame.K_ESCAPE:
                self._to_menu()
                return
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                fallback = next(iter(self.levels))
                self._start(self.session.level_id if self.session.level_id in self.levels else fallback)
                return
        if self.menu_button.handle_event(event) == "click":
            self._to_menu()
        if self.shop_button.handle_event(event) == "click":
            self._open_shop()
        if self.editor_button.handle_event(event) == "click":
            self.audio.play("click")
            from .level_editor_menu import LevelEditorMenuScene
            self.manager.switch(LevelEditorMenuScene(self.manager))

    def draw(self, surface):
        surface.blit(self.background, (0, 0))
        draw_coins(surface, int(self.session.money), (px(12), px(12)), 16, config.TEXT, icon=COIN_BALANCE)
        cx = config.WINDOW_W // 2
        draw_text(surface, "SELECT LEVEL", (cx, px(110)), 40, config.TEXT, kind="bold", anchor="center")
        draw_text(surface, "Choose a mission", (cx, px(152)), 16, config.TEXT_DIM, anchor="center")
        for lid, rect in self.cards:
            self._draw_card(surface, lid, rect)
        self.prev_arrow.draw(surface)
        self.next_arrow.draw(surface)
        self._draw_page_dots(surface)
        self.tutorial_button.draw(surface)
        self.editor_button.draw(surface)
        self.shop_button.draw(surface)
        self.menu_button.draw(surface)
        self._draw_inventory_button(surface)
        self._draw_inventory_popup(surface)

    @property
    def page_count(self):
        return page_count(len(self.level_ids), CARDS_PER_PAGE)

    @staticmethod
    def _now():
        """Clock for the wheel cooldown (tests replace it)."""
        return time.monotonic()

    def grid_rect(self):
        """The 3x3 card grid on screen (whole grid, even on a short last page)."""
        left, top = grid_origin()
        w, h = _grid_size()
        return pygame.Rect(px(left), px(top), px(w), px(h))

    def _rebuild_cards(self):
        left, top = grid_origin()
        self.page = clamp_page(self.page, self.page_count)
        self.cards = []
        for slot, lid in enumerate(levels_on_page(self.level_ids, self.page, CARDS_PER_PAGE)):
            col, row = slot % COLS, slot // COLS
            rect = pygame.Rect(
                px(left + col * (CARD_W + GAP)),
                px(top + row * (CARD_H + GAP)),
                px(CARD_W), px(CARD_H),
            )
            self.cards.append((lid, rect))
        self.prev_arrow.enabled = can_prev(self.page)
        self.next_arrow.enabled = can_next(self.page, self.page_count)
        for arrow in (self.prev_arrow, self.next_arrow):
            arrow.hover = arrow.hover and arrow.enabled
        # Remembered across scenes, with the level that was current then.
        self.session.level_select_page = (self.page, getattr(self.session, "level_id", None))

    def _turn(self, step):
        """Move one page back (-1) or on (+1); nothing toward a disabled side."""
        allowed = can_prev(self.page) if step < 0 else can_next(self.page, self.page_count)
        if not allowed:
            return False
        self.audio.play("click")
        self.page += -1 if step < 0 else 1
        self._rebuild_cards()
        return True

    def _next_page(self):
        return self._turn(1)

    def _prev_page(self):
        return self._turn(-1)

    def page_dots(self):
        """((x, y), filled) per page: centred under the grid, filled for this page."""
        grid = self.grid_rect()
        n = self.page_count
        y = grid.bottom + px(DOTS_BELOW_GRID)
        first = grid.centerx - px(DOT_GAP) * (n - 1) / 2
        return [((round(first + px(DOT_GAP) * k), y), k == self.page) for k in range(n)]

    def _draw_page_dots(self, surface):
        """Display only: the dots are not clickable."""
        radius = max(2, px(DOT_R))
        for center, filled in self.page_dots():
            if filled:
                pygame.draw.circle(surface, config.TEXT, center, radius)
            else:
                pygame.draw.circle(surface, config.TEXT_DIM, center, radius, max(1, px(1)))

    def _draw_card(self, surface, lid, rect):
        level = self.levels.get(lid)
        line_w = max(1, px(1))
        if level is None:
            pygame.draw.rect(surface, (14, 19, 36), rect, border_radius=px(6))
            pygame.draw.rect(surface, config.PANEL_EDGE, rect, line_w, border_radius=px(6))
            lock = icon_surface("lock", px(34), config.TEXT_FAINT)
            surface.blit(lock, lock.get_rect(center=(rect.centerx, rect.y + px(52))))
            draw_text(surface, f"Level {lid}", (rect.centerx, rect.y + px(94)), 16, config.TEXT_FAINT,
                      kind="bold", anchor="center")
            draw_text(surface, "Coming soon", (rect.centerx, rect.y + px(118)), 13, config.TEXT_FAINT,
                      anchor="center")
            return

        hover = self.hover == lid
        pygame.draw.rect(surface, config.EDITOR_LINE_HL if hover else config.PANEL_BG, rect, border_radius=px(6))
        pygame.draw.rect(surface, config.ACCENT if hover else config.EDITOR_BORDER, rect,
                         max(2, px(2)) if hover else line_w, border_radius=px(6))
        draw_text(surface, str(lid), (rect.x + px(18), rect.y + px(10)), 44, config.TEXT, kind="bold")
        name_y, status_y = rect.y + px(78), rect.y + px(116)
        lines, size = [], 13
        if is_dynamic_level(lid):
            try:
                blurb = get_preset(lid).card_blurb
            except KeyError:
                blurb = "New maze every visit"
            # Wrap to the card (two lines at most, shrinking the font if needed);
            # a second line lifts the name and pushes the status down.
            width = rect.w - px(36)
            while size > 10 and len(wrap_text(blurb, size, width)) > 2:
                size -= 1
            lines = wrap_text(blurb, size, width)[:2]
            extra = (len(lines) - 1) * (size + 2)
            name_y -= px(extra // 2)
            status_y = name_y + px(46 + extra)
        draw_text(surface, level.name, (rect.x + px(18), name_y), 17, config.TEXT, kind="bold")
        for k, line in enumerate(lines):
            draw_text(surface, line, (rect.x + px(18), name_y + px(22 + k * (size + 2))), size,
                      config.ACCENT)
        best = self.session.records.get(lid)
        if best is None:
            draw_text(surface, "Not cleared yet", (rect.x + px(18), status_y), 13, config.TEXT_DIM, anchor="midleft")
        else:
            check = icon_surface("check", px(16), config.SUCCESS)
            surface.blit(check, check.get_rect(midleft=(rect.x + px(16), status_y)))
            draw_text(surface, f"Best {best:.2f} s", (rect.x + px(38), status_y), 13, config.SUCCESS,
                      anchor="midleft")
