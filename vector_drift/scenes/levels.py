"""Level select: playable levels plus locked placeholders, and a way back to the main menu."""

import pygame

from .. import config, render
from ..config import px
from ..data import LEVELS, all_levels
from ..level_presets import get_preset, is_dynamic_level
from ..ui import Button, draw_text, icon_surface
from .base import Scene

SLOTS = 9                    # cards shown; levels beyond LEVELS are locked placeholders
COLS = 3
CARD_W, CARD_H, GAP = 220, 150, 30


class LevelSelectScene(Scene):
    def __init__(self, manager):
        super().__init__(manager)
        self.background = render.make_space_background((config.WINDOW_W, config.WINDOW_H), seed=5,
                                                       star_count=260)
        self.levels = {lv.id: lv for lv in all_levels()}
        grid_w = COLS * CARD_W + (COLS - 1) * GAP
        left, top = (1280 - grid_w) // 2, 200
        self.cards = []
        for i in range(max(SLOTS, len(self.levels))):
            col, row = i % COLS, i // COLS
            rect = pygame.Rect(px(left + col * (CARD_W + GAP)), px(top + row * (CARD_H + GAP)),
                               px(CARD_W), px(CARD_H))
            self.cards.append((i + 1, rect))
        self.hover = None
        self.menu_button = Button((px(40), config.WINDOW_H - px(86), px(180), px(46)), "Main Menu",
                                  style="plain", font_size=17)

    def _start(self, level_id):
        self.audio.play("click")
        self.session.level_id = level_id
        self.session.fx_text = self.session.fy_text = ""
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

    def handle_event(self, event):
        if event.type == pygame.MOUSEMOTION:
            self.hover = next((lid for lid, r in self.cards if r.collidepoint(event.pos)), None)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for lid, rect in self.cards:
                if rect.collidepoint(event.pos):
                    if lid in self.levels:
                        self._start(lid)
                    else:
                        self.audio.play("error")
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

    def draw(self, surface):
        surface.blit(self.background, (0, 0))
        cx = config.WINDOW_W // 2
        draw_text(surface, "SELECT LEVEL", (cx, px(110)), 40, config.TEXT, kind="bold", anchor="center")
        draw_text(surface, "Choose a mission", (cx, px(152)), 16, config.TEXT_DIM, anchor="center")
        for lid, rect in self.cards:
            self._draw_card(surface, lid, rect)
        self.menu_button.draw(surface)

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
        draw_text(surface, level.name, (rect.x + px(18), rect.y + px(78)), 17, config.TEXT, kind="bold")
        if is_dynamic_level(lid):
            try:
                blurb = get_preset(lid).card_blurb
            except KeyError:
                blurb = "New maze every visit"
            draw_text(surface, blurb, (rect.x + px(18), rect.y + px(100)), 13,
                      config.ACCENT, anchor="topleft")
            status_y = rect.y + px(124)
        else:
            status_y = rect.y + px(116)
        best = self.session.records.get(lid)
        if best is None:
            draw_text(surface, "Not cleared yet", (rect.x + px(18), status_y), 13, config.TEXT_DIM, anchor="midleft")
        else:
            check = icon_surface("check", px(16), config.SUCCESS)
            surface.blit(check, check.get_rect(midleft=(rect.x + px(16), status_y)))
            draw_text(surface, f"Best {best:.2f} s", (rect.x + px(38), status_y), 13, config.SUCCESS,
                      anchor="midleft")
