"""Account overview screen."""

from __future__ import annotations

import pygame

from .. import config, render
from ..config import px
from ..image_assets import COIN_BALANCE
from ..ui import Button, draw_icon_row, draw_text
from .base import Scene
from ..account.integration import session_to_profile, reset_session_to_guest


class AccountScene(Scene):
    music = "menu"

    def __init__(self, manager):
        super().__init__(manager)
        self.background = render.make_space_background((config.WINDOW_W, config.WINDOW_H), seed=11, star_count=220)
        cx = config.WINDOW_W // 2
        self.back_button = Button((px(40), px(20), px(140), px(40)), "Back", style="plain", font_size=17)
        self.logout_button = Button((cx - px(110), px(520), px(220), px(46)), "Logout", style="danger", font_size=17)
        self.refresh_button = Button((cx - px(110), px(460), px(220), px(40)), "Refresh profile", style="plain", font_size=15)
        self.delete_local_button = Button((cx - px(110), px(390), px(220), px(40)), "Delete local data", style="danger", font_size=14)
        self.clear_local_button = self.delete_local_button
        self.delete_guest_data_button = self.delete_local_button
        self.status = ""

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.back_button.handle_event(event) == "click":
                from .menu import MenuScene
                self.manager.switch(MenuScene(self.manager))
                return
            if self.refresh_button.handle_event(event) == "click":
                self._refresh()
                return
            if self.delete_local_button.handle_event(event) == "click":
                self._delete_local()
                return
            if self.logout_button.handle_event(event) == "click":
                self._logout()
                return
        elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            from .menu import MenuScene
            self.manager.switch(MenuScene(self.manager))

    def _refresh(self):
        account = self.manager.account
        if account is None or not account.is_authenticated():
            self.status = "Not authenticated."
            return
        self.status = "Refreshing..."

        def ok(profile):
            from vector_drift.account.integration import (
                apply_best_profile,
                save_guest_profile,
                save_progress,
            )
            # 先將目前未登入賺的進度寫入本地，避免被雲端舊資料覆蓋。
            save_guest_profile(self.session)
            chosen = apply_best_profile(
                self.session, profile, account.current_user.id, account.current_user.email
            )
            # 本地較新且雲端已有資料時，把本地推回雲端，讓兩端收斂。
            if chosen is not None and chosen is not profile and profile is not None:
                save_progress(account, self.session)
            self.status = "Profile refreshed."

        def err(exc):
            self.status = f"Refresh failed: {exc}"

        account.load_profile_async(on_success=ok, on_error=err)

    def _logout(self):
        account = self.manager.account
        self.status = "Logging out..."

        def _to_guest():
            # 切換為 Guest 狀態，但保留同一份遊戲進度：不重置 session、
            # 不載入舊的 guest_profile.json，只改變帳號認證相關欄位。
            session = self.session
            session.user_id = None
            session.email = None
            session.display_name = None
            session.auth_status = "guest"
            session.profile_loaded = False
            session.sync_status = "idle"
            session.last_sync_error = None
            from .menu import MenuScene
            self.manager.switch(MenuScene(self.manager))

        def ok():
            _to_guest()

        def err(exc):
            _to_guest()
            self.status = f"Logout finished with warning: {exc}"

        # 1. 先將目前登入帳號的遊戲進度保存到本地 guest_profile.json
        try:
            from vector_drift.account.integration import save_guest_profile
            save_guest_profile(self.session)
        except Exception:
            pass

        # 2. 若沒有帳號（未登入），直接切換為 Guest，保留現有進度
        if account is None:
            ok()
            return

        # 3. 清除 Supabase 登入 Session（refresh token 等認證資訊會被清除）
        account.sign_out_async(on_success=ok, on_error=err)

    def _delete_local(self):
        account = self.manager.account
        if account is not None:
            try:
                account.delete_local_data(self.session)
            except Exception:
                from vector_drift.account.integration import clear_guest_profile, reset_session_to_guest
                clear_guest_profile(self.session)
        else:
            from vector_drift.account.integration import clear_guest_profile, reset_session_to_guest
            clear_guest_profile(self.session)
        self.status = "Local data deleted."

    def update(self, dt):
        pass

    def draw(self, surface):
        surface.blit(self.background, (0, 0))
        self.back_button.draw(surface)
        cx = config.WINDOW_W // 2
        draw_text(surface, "ACCOUNT", (cx, px(90)), 40, config.TEXT, kind="bold", anchor="center")
        s = self.session
        account = self.manager.account
        lines = [
            ("User", s.email or "Guest"),
            ("Status", s.auth_status),
            ("Display name", s.display_name or "-"),
            (COIN_BALANCE, str(int(s.money))),
            ("Records", str(len(s.records))),
            ("Owned ships", ", ".join(sorted(s.owned_ships))),
            ("Sync", s.sync_status),
        ]
        y = px(160)
        for label, value in lines:
            if label == COIN_BALANCE:           # the coin picture stands for the word
                draw_icon_row(surface, [COIN_BALANCE], (cx - px(160), y), 16, anchor="midleft")
            else:
                draw_text(surface, label, (cx - px(160), y), 16, config.TEXT_DIM, anchor="midleft")
            draw_text(surface, value, (cx + px(160), y), 16, config.TEXT, anchor="midright")
            y += px(32)
        if self.status:
            draw_text(surface, self.status, (cx, px(430)), 15, config.WARNING, anchor="center")
        self.delete_local_button.draw(surface)
        self.refresh_button.draw(surface)
        self.logout_button.draw(surface)
