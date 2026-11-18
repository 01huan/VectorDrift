"""Shop scene: spend coins on ability charges.

Every ability on one page: a 4-column grid, 4 cards on the first row and the
rest centred below. Each card, top to bottom: the ability's icon (picture or
letter avatar) beside its name and key; the description, wrapped; the price
with how many charges the player owns; the Buy button.
"""

import pygame

from .. import config, render
from ..abilities import charge_count, get_ability
from ..ability_icons import draw_ability_icon
from ..config import px
from ..image_assets import COIN_BALANCE, COIN_TRADE
from ..ui import Button, draw_coins, draw_icon_row, draw_text, get_font, wrap_text
from .base import Scene
from .. import shop as shop_module

# Layout constants (design coordinates on the 1280x720 layout).
COLS = 4
CARD_W, GAP = 262, 22
GRID_TOP = 160
CARD_PAD = 14
ICON_BOX = 44                # the icon frame left of the name
ICON_SIDE = 40               # the icon inside it
NAME_SIZE = 17
KEY_SIZE = 12
DESC_SIZE = 13
DESC_LINE_H = 17
PRICE_SIZE = 15
PRICE_ROW_H = 20
BUY_H = 34
SUBTITLE = "Abilities are one-use charges. Press the key during a flight."


def card_height(desc_lines):
    """Card height (logical px) for ``desc_lines`` lines of description."""
    return (CARD_PAD + ICON_BOX + 12 + desc_lines * DESC_LINE_H + 10
            + PRICE_ROW_H + 10 + BUY_H + CARD_PAD)


class ShopScene(Scene):
    music = "menu"

    def __init__(self, manager):
        super().__init__(manager)
        self.background = render.make_space_background((config.WINDOW_W, config.WINDOW_H), seed=7,
                                                       star_count=220)
        # Bottom-left, like Main Menu on level select, clear of the coin balance.
        self.back_button = Button((px(40), config.WINDOW_H - px(86), px(180), px(46)), "Back",
                                 style="plain", font_size=17)
        # Aliases for callers/tests that expect other names.
        self.levels_button = self.back_button
        self.menu_button = self.back_button
        self.cards = []
        self.buy_buttons = []
        self.desc_lines = {}
        self.items = shop_module.all_items()
        self._rebuild_cards()

    def _rebuild_cards(self):
        self.cards = []
        self.buy_buttons = []
        text_w = px(CARD_W - 2 * CARD_PAD)
        self.desc_lines = {item.id: wrap_text(item.description, DESC_SIZE, text_w)
                           for item in self.items}
        lines = max((len(v) for v in self.desc_lines.values()), default=1)
        self.card_h = card_height(max(1, lines))
        for idx, item in enumerate(self.items):
            row, col = divmod(idx, COLS)
            in_row = min(COLS, len(self.items) - row * COLS)
            row_w = in_row * CARD_W + (in_row - 1) * GAP
            left = (config.BASE_W - row_w) // 2
            rect = pygame.Rect(px(left + col * (CARD_W + GAP)),
                               px(GRID_TOP + row * (self.card_h + GAP)),
                               px(CARD_W), px(self.card_h))
            buy_rect = pygame.Rect(rect.x + px(CARD_PAD), rect.bottom - px(CARD_PAD + BUY_H),
                                   rect.w - px(2 * CARD_PAD), px(BUY_H))
            btn = Button(buy_rect, "Buy", style="primary", font_size=16)
            self.cards.append((item, rect))
            self.buy_buttons.append((item, btn))
        self._refresh_buttons()

    @property
    def page_count(self):
        return 1

    def _refresh_buttons(self):
        for item, btn in self.buy_buttons:
            if item.owned(self.session):
                btn.label = "Owned"
                btn.enabled = False
            else:
                btn.label = "Buy"
                btn.enabled = True

    def _to_levels(self):
        self.audio.play("click")
        from .levels import LevelSelectScene
        self.manager.switch(LevelSelectScene(self.manager))

    def handle_event(self, event):
        if event.type == pygame.MOUSEMOTION:
            self.back_button.handle_event(event)
            for _item, btn in self.buy_buttons:
                btn.handle_event(event)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.back_button.handle_event(event) == "click":
                self._to_levels()
                return
            for item, btn in self.buy_buttons:
                if btn.handle_event(event) == "click":
                    if btn.enabled:
                        ok = shop_module.purchase_item(item, self.session)
                        if ok:
                            self.audio.play("purchase")
                            from vector_drift.account.integration import save_progress

                            save_progress(self.manager.account, self.session)

                        else:
                            self.audio.play("error")
                        self._refresh_buttons()
                    else:
                        self.audio.play("error")
                    return
        elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self._to_levels()

    def update(self, dt):
        pass

    def owned_count(self, item):
        """Charges of ``item`` the player holds (0 for non-ability items)."""
        if get_ability(item.id) is None:
            return 1 if item.owned(self.session) else 0
        return charge_count(self.session, item.id)

    def _draw_card(self, surface, item, rect):
        pygame.draw.rect(surface, config.PANEL_BG, rect, border_radius=px(6))
        pygame.draw.rect(surface, config.PANEL_EDGE, rect, width=max(1, px(1)),
                         border_radius=px(6))
        # Icon frame, then the name and the key label beside it.
        box = pygame.Rect(rect.x + px(CARD_PAD), rect.y + px(CARD_PAD), px(ICON_BOX), px(ICON_BOX))
        pygame.draw.rect(surface, config.BG, box, border_radius=px(5))
        pygame.draw.rect(surface, config.PANEL_EDGE, box, width=max(1, px(1)), border_radius=px(5))
        draw_ability_icon(surface, item.id, box.center, px(ICON_SIDE))
        text_x = box.right + px(12)
        draw_text(surface, item.name, (text_x, box.y + px(1)), NAME_SIZE, config.TEXT, kind="bold")
        ability = get_ability(item.id)
        if ability is not None and ability.key:
            key_w = get_font(KEY_SIZE, "bold").size(ability.key)[0]
            frame = pygame.Rect(text_x, box.bottom - px(19), max(px(19), key_w + px(12)), px(19))
            pygame.draw.rect(surface, config.BG, frame, border_radius=px(3))
            pygame.draw.rect(surface, config.TEXT_DIM, frame, width=max(1, px(1)),
                             border_radius=px(3))
            draw_text(surface, ability.key, frame.center, KEY_SIZE, config.TEXT, kind="bold",
                      anchor="center")
        # Description, wrapped: never cut.
        y = box.bottom + px(12)
        for line in self.desc_lines.get(item.id, []):
            draw_text(surface, line, (rect.x + px(CARD_PAD), y), DESC_SIZE, config.TEXT_DIM)
            y += px(DESC_LINE_H)
        # Price on the left, charges owned on the right.
        price_y = rect.bottom - px(CARD_PAD + BUY_H + 10 + PRICE_ROW_H // 2)
        short = not item.owned(self.session) and item.price > int(self.session.money)
        draw_icon_row(surface, [("Price", config.TEXT_DIM), COIN_TRADE,
                                (item.price, config.DANGER if short else config.TEXT)],
                      (rect.x + px(CARD_PAD), price_y), PRICE_SIZE, anchor="midleft")
        count = self.owned_count(item)
        draw_text(surface, f"Owned ×{count}", (rect.right - px(CARD_PAD), price_y), PRICE_SIZE,
                  config.TEXT if count else config.TEXT_DIM, kind="bold", anchor="midright")

    def draw(self, surface):
        surface.blit(self.background, (0, 0))
        draw_coins(surface, int(self.session.money), (px(12), px(12)), 16, config.TEXT,
                   icon=COIN_BALANCE)
        cx = config.WINDOW_W // 2
        draw_text(surface, "SHOP", (cx, px(90)), 40, config.TEXT, kind="bold", anchor="center")
        draw_text(surface, SUBTITLE, (cx, px(132)), 16, config.TEXT_DIM, anchor="center")
        for item, rect in self.cards:
            self._draw_card(surface, item, rect)
        for _item, btn in self.buy_buttons:
            btn.draw(surface)
        self.back_button.draw(surface)
