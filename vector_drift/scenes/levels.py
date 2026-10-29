"""Level select: playable levels plus locked placeholders, and a way back to the main menu."""

import pygame

from .. import config, render
from ..config import px
from ..data import LEVELS, all_levels
from ..level_presets import get_preset, is_dynamic_level
from ..ui import Button, draw_text, icon_surface, wrap_text
from .base import Scene

PAGES = 3                    # number of level-select pages (extensible)
LEVELS_PER_PAGE = 7          # playable level cards on a non-final page
CARDS_PER_PAGE = 9           # 3x3 grid; last slot is "next page" on non-final pages
COLS = 3
CARD_W, CARD_H, GAP = 220, 150, 30


class LevelSelectScene(Scene):
    def __init__(self, manager):
        super().__init__(manager)
        self.background = render.make_space_background((config.WINDOW_W, config.WINDOW_H), seed=5,
                                                       star_count=260)
        self.levels = {lv.id: lv for lv in all_levels()}
        self.page = 0
        self.hover = None
        self.cards = []
        self.prev_button = None
        self.next_button = None
        self.menu_button = Button((px(40), config.WINDOW_H - px(86), px(180), px(46)), "Main Menu",
                                  style="plain", font_size=17)
        self.shop_button = Button((config.WINDOW_W - px(180), px(20), px(160), px(40)), "Shop",
                                 style="primary", font_size=17)
        self.store_button = self.shop_button
        self._rebuild_cards()

    def _start(self, level_id):
        self.audio.play("click")
        self.session.level_id = level_id
        self.session.fx_text = self.session.fy_text = ""
        self.session.ship_id = None             # start on the level's newest ship
        # Fresh solvable layout for dynamic levels on every entry; static
        # levels always come from get_level().
        self.session.random_seed = None
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

    def handle_event(self, event):
        if event.type == pygame.MOUSEMOTION:
            self.hover = next((lid for lid, r in self.cards if r.collidepoint(event.pos)), None)
            if self.next_button is not None:
                self.next_button.handle_event(event)
            if self.prev_button is not None:
                self.prev_button.handle_event(event)
            self.shop_button.handle_event(event)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for lid, rect in self.cards:
                if rect.collidepoint(event.pos):
                    if lid in self.levels:
                        self._start(lid)
                    else:
                        self.audio.play("error")
                    return
            if self.next_button is not None and self.next_button.handle_event(event) == "click":
                self._next_page()
                return
            if self.prev_button is not None and self.prev_button.handle_event(event) == "click":
                self._prev_page()
                return
            if self.shop_button.handle_event(event) == "click":
                self._open_shop()
                return
        elif event.type == pygame.KEYDOWN:
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
        if self.next_button is not None and self.next_button.handle_event(event) == "click":
            self._next_page()
        if self.prev_button is not None and self.prev_button.handle_event(event) == "click":
                self._prev_page()

    def draw(self, surface):
        surface.blit(self.background, (0, 0))
        draw_text(surface, f"Money: {int(self.session.money)}", (px(12), px(12)), 16, config.TEXT, kind="bold")
        cx = config.WINDOW_W // 2
        draw_text(surface, "SELECT LEVEL", (cx, px(110)), 40, config.TEXT, kind="bold", anchor="center")
        draw_text(surface, "Choose a mission", (cx, px(152)), 16, config.TEXT_DIM, anchor="center")
        for lid, rect in self.cards:
            self._draw_card(surface, lid, rect)
        if self.next_button is not None:
            self.next_button.draw(surface)
        if self.prev_button is not None:
            self.prev_button.draw(surface)
        self.shop_button.draw(surface)
        self.menu_button.draw(surface)

    def _page_level_ids(self, page):
        if page == 0:
            return range(1, LEVELS_PER_PAGE + 2)
        if page == PAGES - 1:
            start = (PAGES - 1) * LEVELS_PER_PAGE + 2
            return range(start, start + LEVELS_PER_PAGE + 1 + 1)
        start = LEVELS_PER_PAGE + 2 + (page - 1) * LEVELS_PER_PAGE
        return range(start, start + LEVELS_PER_PAGE+1)

    
    

    def _rebuild_cards(self):
        grid_w = COLS * CARD_W + (COLS - 1) * GAP
        left, top = (1280 - grid_w) // 2, 200
        self.cards = []

        if self.page > 0:
            self.prev_button = Button(
                pygame.Rect(
                    px(left), px(top), px(CARD_W), px(CARD_H)
                ),
                "Previous Page",
                style="primary",
                font_size=17,
            )
        else:
            self.prev_button = None

        if self.page < PAGES - 1:
            next_rect = pygame.Rect(
                px(left + 2 * (CARD_W + GAP)),
                px(top + 2 * (CARD_H + GAP)),
                px(CARD_W), px(CARD_H),
            )
            self.next_button = Button(
                next_rect, "Next Page",
                style="primary", font_size=17
            )
        else:
            self.next_button = None

        for idx, lid in enumerate(self._page_level_ids(self.page)):
            if self.page == 0:
                slot = idx
            elif self.page == PAGES - 1:
                slot = idx + 1
            else:
                # Middle pages: skip top-left and bottom-right.
                slot = idx + 1
                if slot >= 8:
                    slot += 1

            col, row = slot % COLS, slot // COLS
            rect = pygame.Rect(
                px(left + col * (CARD_W + GAP)),
                px(top + row * (CARD_H + GAP)),
                px(CARD_W), px(CARD_H),
            )
            self.cards.append((lid, rect))


    def _next_page(self):
        if self.page < PAGES - 1:
            self.audio.play("click")
            self.page += 1
            self._rebuild_cards()
    def _prev_page(self):
        if self.page > 0:
            self.audio.play("click")
            self.page -= 1
            self._rebuild_cards()
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
