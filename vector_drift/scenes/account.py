"""Account overview screen."""

from __future__ import annotations

import pygame

from .. import config, render
from ..config import px
from ..image_assets import COIN_BALANCE
from ..ui import Button, draw_icon_row, draw_text
from .base import Scene
from .auth import _TextInput
from ..account.integration import session_to_profile, reset_session_to_guest


class AccountScene(Scene):
    music = "menu"

    def __init__(self, manager):
        super().__init__(manager)
        self.background = render.make_space_background((config.WINDOW_W, config.WINDOW_H), seed=11, star_count=220)
        cx = config.WINDOW_W // 2
        self.back_button = Button((px(40), px(20), px(140), px(40)), "Back", style="plain", font_size=17)
        self.logout_button = Button((cx - px(110), px(520), px(220), px(46)), "Logout", style="danger", font_size=17)
        self.refresh_button = Button((cx - px(110), px(370), px(220), px(40)), "Refresh profile", style="plain", font_size=15)
        self.delete_local_button = Button((cx - px(110), px(600), px(220), px(40)), "Delete local data", style="danger", font_size=14)
        self.clear_local_button = self.delete_local_button
        self.delete_guest_data_button = self.delete_local_button
        # 修改名稱
        self.change_name_button = Button((cx - px(110), px(460), px(220), px(40)), "change name", style="plain", font_size=15)
        self.name_input = _TextInput((cx - px(180), px(260), px(360), px(40)), "new name")
        self.save_name_button = Button((cx - px(110), px(320), px(100), px(40)), "save", style="primary", font_size=15)
        self.cancel_name_button = Button((cx + px(10), px(320), px(100), px(40)), "cancel", style="plain", font_size=15)
        self.edit_name = False
        self.name_status = ""
        self.status = ""

    def handle_event(self, event):
        if self.edit_name:
            self.name_input.handle_event(event)
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if self.save_name_button.handle_event(event) == "click":
                    self._save_name()
                    return
                if self.cancel_name_button.handle_event(event) == "click":
                    self.edit_name = False
                    self.name_input.text = ""
                    self.name_status = ""
                    return
            if event.type == pygame.KEYDOWN and event.key == pygame.K_RETURN:
                self._save_name()
                return
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self.edit_name = False
                self.name_input.text = ""
                self.name_status = ""
                return
        else:
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if self.back_button.handle_event(event) == "click":
                    from .menu import MenuScene
                    self.manager.switch(MenuScene(self.manager))
                    return
                if self.change_name_button.handle_event(event) == "click":
                    account = self.manager.account
                    if account is not None and account.is_authenticated():
                        self.edit_name = True
                        self.name_input.text = self.session.display_name or ""
                        self.name_status = ""
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
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE and not self.edit_name:
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

    def _save_name(self):
        account = self.manager.account
        if account is None or not account.is_authenticated():
            self.name_status = "Not authenticated."
            return
        new_name = self.name_input.text.strip()
        if not new_name:
            self.name_status = "Name is required."
            return
        if len(new_name) > 32:
            self.name_status = "Name too long (max 32 chars)."
            return
        self.name_status = "Saving..."

        def ok(result):
            self.edit_name = False
            self.name_input.text = ""
            self.session.display_name = result or ""
            self.name_status = f"Name updated to \"{result}\"."

        def err(exc):
            self.name_status = f"Failed: {exc}"

        account.update_display_name_async(new_name, on_success=ok, on_error=err)

    def update(self, dt):
        pass

    def draw(self, surface):
        surface.blit(self.background, (0, 0))
        cx = config.WINDOW_W // 2
        draw_text(surface, "ACCOUNT", (cx, px(90)), 40, config.TEXT, kind="bold", anchor="center")

        # 修改名稱編輯模式：用深色面板完全遮蓋背景，不與原本內容重疊。
        if self.edit_name:
            panel = pygame.Surface((px(520), px(300)))
            panel.fill((16, 22, 42))
            panel.set_alpha(235)
            panel_rect = panel.get_rect(center=(cx, config.WINDOW_H // 2))
            surface.blit(panel, panel_rect)
            pygame.draw.rect(surface, config.PANEL_EDGE, panel_rect, width=2, border_radius=px(6))

            draw_text(surface, "Change Account Name", (cx, panel_rect.y + px(30)), 24, config.TEXT,
                      kind="bold", anchor="center")
            draw_text(surface, "", (panel_rect.x + px(40), panel_rect.y + px(90)), 16,
                      config.TEXT_DIM, anchor="topleft")
            self.name_input.draw(surface)
            self.save_name_button.draw(surface)
            self.cancel_name_button.draw(surface)
            if self.name_status:
                draw_text(surface, self.name_status, (cx, panel_rect.bottom - px(50)), 14,
                          config.WARNING, anchor="center")
            self.back_button.draw(surface)
            if self.status:
                draw_text(surface, self.status, (cx, panel_rect.y + px(255)), 14,
                          config.WARNING, anchor="center")
            return

        # 一般帳號頁面
        self.back_button.draw(surface)
        s = self.session
        account = self.manager.account
        lines = [
            ("User", s.display_name or "—"),
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
        self.change_name_button.draw(surface)
