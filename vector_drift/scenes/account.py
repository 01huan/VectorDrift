"""Account overview screen."""

from __future__ import annotations

import pygame

from .. import config, render
from ..config import px
from ..ui import Button, draw_text
from .base import Scene
from ..account.integration import session_to_profile, reset_session_to_guest


class AccountScene(Scene):
    def __init__(self, manager):
        super().__init__(manager)
        self.background = render.make_space_background((config.WINDOW_W, config.WINDOW_H), seed=11, star_count=220)
        cx = config.WINDOW_W // 2
        self.back_button = Button((px(40), px(20), px(140), px(40)), "Back", style="plain", font_size=17)
        self.logout_button = Button((cx - px(110), px(520), px(220), px(46)), "Logout", style="danger", font_size=17)
        self.refresh_button = Button((cx - px(110), px(460), px(220), px(40)), "Refresh profile", style="plain", font_size=15)
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
            from vector_drift.account.integration import apply_profile_to_session
            apply_profile_to_session(self.session, profile, account.current_user.id, account.current_user.email)
            self.status = "Profile refreshed."

        def err(exc):
            self.status = f"Refresh failed: {exc}"

        account.load_profile_async(on_success=ok, on_error=err)

    def _logout(self):
        account = self.manager.account
        if account is None:
            reset_session_to_guest(self.session)
            from .menu import MenuScene
            self.manager.switch(MenuScene(self.manager))
            return
        self.status = "Logging out..."

        def ok():
            reset_session_to_guest(self.session)
            from .menu import MenuScene
            self.manager.switch(MenuScene(self.manager))

        def err(exc):
            reset_session_to_guest(self.session)
            self.status = f"Logout finished with warning: {exc}"
            from .menu import MenuScene
            self.manager.switch(MenuScene(self.manager))

        account.sign_out_async(on_success=ok, on_error=err)

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
            ("Money", str(int(s.money))),
            ("Records", str(len(s.records))),
            ("Owned ships", ", ".join(sorted(s.owned_ships))),
            ("Sync", s.sync_status),
        ]
        y = px(160)
        for label, value in lines:
            draw_text(surface, label, (cx - px(160), y), 16, config.TEXT_DIM, anchor="midleft")
            draw_text(surface, value, (cx + px(160), y), 16, config.TEXT, anchor="midright")
            y += px(32)
        if self.status:
            draw_text(surface, self.status, (cx, px(430)), 15, config.WARNING, anchor="center")
        self.refresh_button.draw(surface)
        self.logout_button.draw(surface)
