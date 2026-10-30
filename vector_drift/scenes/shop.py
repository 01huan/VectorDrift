"""Shop scene: spend money on purchasable items (ships, ...)."""

import pygame

from .. import config, render
from ..config import px
from ..ui import Button, draw_text
from .base import Scene
from .. import shop as shop_module


class ShopScene(Scene):
    def __init__(self, manager):
        super().__init__(manager)
        self.background = render.make_space_background((config.WINDOW_W, config.WINDOW_H), seed=7,
                                                       star_count=220)
        self.back_button = Button((px(40), px(20), px(140), px(40)), "Back",
                                 style="plain", font_size=17)
        # Aliases for callers/tests that expect other names.
        self.levels_button = self.back_button
        self.menu_button = self.back_button
        self._build()

    def _build(self):
        self.cards = []
        self.buy_buttons = []
        items = shop_module.all_items()
        cols = 3
        card_w, card_h = 260, 180
        gap = 24
        grid_w = cols * card_w + (cols - 1) * gap
        left = (config.WINDOW_W - grid_w) // 2
        top = px(150)
        for idx, item in enumerate(items):
            col = idx % cols
            row = idx // cols
            rect = pygame.Rect(px(left + col * (card_w + gap)),
                               px(top + row * (card_h + gap)),
                               px(card_w), px(card_h))
            buy_rect = pygame.Rect(rect.x + px(16), rect.bottom - px(44),
                                   rect.w - px(32), px(34))
            btn = Button(buy_rect, "Buy", style="primary", font_size=16)
            if item.owned(self.session):
                btn.label = "Owned"
                btn.enabled = False
            self.cards.append((item, rect))
            self.buy_buttons.append((item, btn))

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
                            self.audio.play("click")
                            account = self.manager.account
                            if account is not None and account.is_authenticated() and account.current_user is not None:
                                try:
                                    from vector_drift.account.integration import session_to_profile
                                    profile = session_to_profile(self.session, account.current_user.id)
                                    self.session.sync_status = "syncing"

                                    def _on_saved():
                                        self.session.sync_status = "idle"

                                    def _on_save_error(exc):
                                        self.session.sync_status = "error"
                                        self.session.last_sync_error = str(exc)

                                    account.save_profile_async(profile, on_success=_on_saved, on_error=_on_save_error)
                                except Exception:
                                    pass
                            else:
                                try:
                                    from vector_drift.account.integration import save_guest_profile
                                    save_guest_profile(self.session)
                                except Exception:
                                    pass

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

    def draw(self, surface):
        surface.blit(self.background, (0, 0))
        draw_text(surface, f"Money: {int(self.session.money)}", (px(12), px(12)), 16,
                  config.TEXT, kind="bold")
        cx = config.WINDOW_W // 2
        draw_text(surface, "SHOP", (cx, px(90)), 40, config.TEXT, kind="bold", anchor="center")
        draw_text(surface, "Spend money to unlock items", (cx, px(132)), 16,
                  config.TEXT_DIM, anchor="center")
        for item, rect in self.cards:
            pygame.draw.rect(surface, config.PANEL_BG, rect, border_radius=px(6))
            pygame.draw.rect(surface, config.PANEL_EDGE, rect, width=max(1, px(1)),
                             border_radius=px(6))
            draw_text(surface, item.name, (rect.x + px(16), rect.y + px(16)), 18,
                      config.TEXT, kind="bold")
            draw_text(surface, item.description, (rect.x + px(16), rect.y + px(44)), 13,
                      config.TEXT_DIM)
            draw_text(surface, f"Price: {item.price}", (rect.x + px(16), rect.y + px(74)), 15,
                      config.ACCENT, kind="bold")
        for _item, btn in self.buy_buttons:
            btn.draw(surface)
        self.back_button.draw(surface)


# Alias names for compatibility.
StoreScene = ShopScene
