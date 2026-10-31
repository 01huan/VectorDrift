"""Login / register screens backed by Supabase Auth."""

from __future__ import annotations

import pygame

from .. import config, render
from ..config import px
from ..ui import Button, draw_text, get_font
from .base import Scene


class _TextInput:
    def __init__(self, rect, placeholder="", password=False):
        self.rect = pygame.Rect(rect)
        self.placeholder = placeholder
        self.password = password
        self._text = ""
        self.cursor = 0
        self.active = False
        self._keydown_inserted = False
        self._last_keydown_char = ""

    @property
    def text(self):
        return self._text

    @text.setter
    def text(self, value):
        self._text = value
        if self.cursor > len(self._text):
            self.cursor = len(self._text)

    def _font(self):
        return get_font(16, "ui")

    def _insert(self, text):
        if not text:
            return
        self.text = self.text[:self.cursor] + text + self.text[self.cursor:]
        self.cursor += len(text)

    def _delete_before(self):
        if self.cursor > 0:
            self.text = self.text[:self.cursor - 1] + self.text[self.cursor:]
            self.cursor -= 1
        elif self.text:
            self.text = self.text[:-1]
            self.cursor = len(self.text)

    def _delete_after(self):
        if self.cursor < len(self.text):
            self.text = self.text[:self.cursor] + self.text[self.cursor + 1:]

    def _move_cursor_to_pos(self, x):
        font = self._font()
        display = "*" * len(self.text) if self.password else self.text
        # find nearest cursor index
        best = 0
        best_dist = abs((self.rect.x + px(8)) - x)
        for i in range(len(display) + 1):
            w = font.size(display[:i])[0]
            pos_x = self.rect.x + px(8) + w
            dist = abs(pos_x - x)
            if dist < best_dist:
                best_dist = dist
                best = i
        self.cursor = best

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self._keydown_inserted = False
            self._last_keydown_char = ""
            self.active = self.rect.collidepoint(event.pos)
            if self.active:
                self._move_cursor_to_pos(event.pos[0])
            return
        if not self.active:
            return
        if event.type == pygame.TEXTINPUT:
            txt = getattr(event, "text", "")
            if self._keydown_inserted and txt == self._last_keydown_char:
                self._keydown_inserted = False
                self._last_keydown_char = ""
                return
            self._insert(txt)
            self._keydown_inserted = False
            self._last_keydown_char = ""
            return
        if event.type != pygame.KEYDOWN:
            return
        self._keydown_inserted = False
        self._last_keydown_char = ""
        mod = getattr(event, "mod", 0)
        ctrl = bool(mod & pygame.KMOD_CTRL)
        if event.key == pygame.K_BACKSPACE:
            self._delete_before()
        elif event.key == pygame.K_DELETE:
            self._delete_after()
        elif event.key == pygame.K_LEFT:
            self.cursor = max(0, self.cursor - 1)
        elif event.key == pygame.K_RIGHT:
            self.cursor = min(len(self.text), self.cursor + 1)
        elif event.key == pygame.K_HOME:
            self.cursor = 0
        elif event.key == pygame.K_END:
            self.cursor = len(self.text)
        elif ctrl and event.key == pygame.K_c:
            try:
                pygame.scrap.put_text(self.text)
            except Exception:
                pass
        elif ctrl and event.key == pygame.K_v:
            try:
                txt = pygame.scrap.get_text()
            except Exception:
                txt = None
            if txt:
                self._insert(txt)
        elif ctrl and event.key == pygame.K_x:
            try:
                pygame.scrap.put_text(self.text)
            except Exception:
                pass
            self.text = ""
            self.cursor = 0
        elif ctrl and event.key == pygame.K_a:
            self.cursor = len(self.text)
        elif event.key in (
            pygame.K_KP0, pygame.K_KP1, pygame.K_KP2,
            pygame.K_KP3, pygame.K_KP4, pygame.K_KP5,
            pygame.K_KP6, pygame.K_KP7, pygame.K_KP8,
            pygame.K_KP9
        ):
            keypad_map = {
                pygame.K_KP0: "0",
                pygame.K_KP1: "1",
                pygame.K_KP2: "2",
                pygame.K_KP3: "3",
                pygame.K_KP4: "4",
                pygame.K_KP5: "5",
                pygame.K_KP6: "6",
                pygame.K_KP7: "7",
                pygame.K_KP8: "8",
                pygame.K_KP9: "9",
            }

            ch = keypad_map[event.key]
            self._insert(ch)
            self._keydown_inserted = True
            self._last_keydown_char = ch

        elif event.key == pygame.K_KP_PERIOD:
            self._insert(".")
            self._keydown_inserted = True
            self._last_keydown_char = "."

        elif event.unicode and len(event.unicode) == 1 and event.unicode.isprintable():
            self._insert(event.unicode)
            self._keydown_inserted = True
            self._last_keydown_char = event.unicode
            pass

    def draw(self, surface):
        pygame.draw.rect(surface, config.EDITOR_BG, self.rect, border_radius=px(4))
        pygame.draw.rect(surface, config.ACCENT if self.active else config.EDITOR_BORDER,
                         self.rect, width=max(1, px(1)), border_radius=px(4))
        display = "*" * len(self.text) if self.password else self.text
        if not display:
            draw_text(surface, self.placeholder, (self.rect.x + px(8), self.rect.centery),
                      16, config.TEXT_FAINT, anchor="midleft")
        else:
            draw_text(surface, display, (self.rect.x + px(8), self.rect.centery),
                      16, config.TEXT, anchor="midleft")
        if self.active:
            font = self._font()
            prefix = "*" * self.cursor if self.password else self.text[:self.cursor]
            cx = self.rect.x + px(8) + font.size(prefix)[0]
            pygame.draw.line(surface, config.EDITOR_CURSOR,
                             (cx, self.rect.y + px(6)), (cx, self.rect.bottom - px(6)), max(1, px(1)))


class LoginScene(Scene):
    music = "menu"

    def __init__(self, manager):
        super().__init__(manager)
        self.background = render.make_space_background((config.WINDOW_W, config.WINDOW_H), seed=9, star_count=220)
        cx = config.WINDOW_W // 2
        self.email_input = _TextInput((cx - px(180), px(220), px(360), px(40)), "Email")
        self.password_input = _TextInput((cx - px(180), px(280), px(360), px(40)), "Password", password=True)
        self.email_input.active = True
        self.login_button = Button((cx - px(180), px(340), px(170), px(44)), "Login", style="primary", font_size=17)
        self.register_button = Button((cx + px(10), px(340), px(170), px(44)), "Register", style="plain", font_size=17)
        self.forgot_button = Button((cx - px(180), px(400), px(170), px(36)), "Forgot password", style="plain", font_size=14)
        self.back_button = Button((cx + px(10), px(400), px(170), px(36)), "Back", style="plain", font_size=14)
        self.delete_local_button = Button((cx - px(180), px(460), px(360), px(36)), "Delete local data", style="danger", font_size=14)
        self.clear_local_button = self.delete_local_button
        self.delete_guest_data_button = self.delete_local_button
        self.status = ""
        self._busy = False

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
        self._set_status("Local data deleted.")

    def _set_status(self, msg):
        self.status = msg

    def handle_event(self, event):
        self.email_input.handle_event(event)
        self.password_input.handle_event(event)
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.login_button.handle_event(event) == "click":
                self._try_login()
                return
            if self.register_button.handle_event(event) == "click":
                from .auth import RegisterScene
                self.manager.switch(RegisterScene(self.manager))
                return
            if self.forgot_button.handle_event(event) == "click":
                self._forgot_password()
                return
            if self.back_button.handle_event(event) == "click":
                from .menu import MenuScene
                self.manager.switch(MenuScene(self.manager))
                return
            if self.delete_local_button.handle_event(event) == "click":
                self._delete_local()
                return
        elif event.type == pygame.KEYDOWN and event.key == pygame.K_RETURN:
            self._try_login()

    def _try_login(self):
        if self._busy:
            return
        email = self.email_input.text.strip()
        password = self.password_input.text
        if not email or not password:
            self._set_status("Email and password are required.")
            return
        account = self.manager.account
        if account is None or not account.is_configured():
            self._set_status("Supabase is not configured.")
            return
        if account.is_busy:
            self._set_status("Please wait, finishing previous request...")
            return
        self._busy = True
        self.login_button.enabled = False
        self.email_input.active = False
        self.password_input.active = False
        self._set_status("Signing in...")

        def ok(_user):
            self._busy = False
            self.login_button.enabled = True
            profile = account.profile
            if profile is not None and account.current_user is not None:
                from vector_drift.account.integration import apply_profile_to_session
                apply_profile_to_session(self.session, profile, account.current_user.id, account.current_user.email)
            from .menu import MenuScene
            self.manager.switch(MenuScene(self.manager))

        def err(exc):
            self._busy = False
            self.login_button.enabled = True
            self._set_status(f"Login failed: {exc}")

        account.sign_in_async(email, password, on_success=ok, on_error=err)
    def _forgot_password(self):
        email = self.email_input.text.strip()
        if not email:
            self._set_status("Enter your email first.")
            return
        account = self.manager.account
        if account is None or not account.is_configured():
            self._set_status("Supabase is not configured.")
            return
        self._set_status("Sending reset email...")

        def ok():
            self._set_status("Password reset email sent.")

        def err(exc):
            self._set_status(f"Reset failed: {exc}")

        account.request_password_reset_async(email, on_success=ok, on_error=err)

    def update(self, dt):
        pass

    def draw(self, surface):
        surface.blit(self.background, (0, 0))
        cx = config.WINDOW_W // 2
        draw_text(surface, "LOGIN", (cx, px(120)), 40, config.TEXT, kind="bold", anchor="center")
        draw_text(surface, "Email", (cx - px(180), px(196)), 14, config.TEXT_DIM, anchor="midleft")
        draw_text(surface, "Password", (cx - px(180), px(256)), 14, config.TEXT_DIM, anchor="midleft")
        self.email_input.draw(surface)
        self.password_input.draw(surface)
        self.login_button.draw(surface)
        self.register_button.draw(surface)
        self.forgot_button.draw(surface)
        self.back_button.draw(surface)
        self.delete_local_button.draw(surface)
        if self.status:
            msg = self.status
            if self._busy:
                dots = "." * (int(pygame.time.get_ticks() / 400) % 4)
                msg = self.status.rstrip(".") + dots
            draw_text(surface, msg, (cx, px(460)), 15, config.WARNING, anchor="center")
        if self.manager.account is not None and self.manager.account.is_busy:
            draw_text(surface, "Please wait, contacting server...", (cx, px(485)), 13, config.TEXT_FAINT, anchor="center")


class RegisterScene(Scene):
    music = "menu"

    def __init__(self, manager):
        super().__init__(manager)
        self.background = render.make_space_background((config.WINDOW_W, config.WINDOW_H), seed=10, star_count=220)
        cx = config.WINDOW_W // 2
        self.email_input = _TextInput((cx - px(180), px(220), px(360), px(40)), "Email")
        self.password_input = _TextInput((cx - px(180), px(280), px(360), px(40)), "Password (min 6 chars)", password=True)
        self.confirm_input = _TextInput((cx - px(180), px(340), px(360), px(40)), "Confirm password", password=True)
        self.email_input.active = True
        self.register_button = Button((cx - px(180), px(400), px(170), px(44)), "Create account", style="primary", font_size=15)
        self.back_button = Button((cx + px(10), px(400), px(170), px(44)), "Back", style="plain", font_size=17)
        self.status = ""
        self._busy = False

    def handle_event(self, event):
        self.email_input.handle_event(event)
        self.password_input.handle_event(event)
        self.confirm_input.handle_event(event)
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.register_button.handle_event(event) == "click":
                self._try_register()
                return
            if self.back_button.handle_event(event) == "click":
                from .auth import LoginScene
                self.manager.switch(LoginScene(self.manager))
                return
        elif event.type == pygame.KEYDOWN and event.key == pygame.K_RETURN:
            self._try_register()

    def _try_register(self):
        if self._busy:
            return
        email = self.email_input.text.strip()
        password = self.password_input.text
        confirm = self.confirm_input.text
        if not email or not password:
            self._set_status("Email and password are required.")
            return
        if password != confirm:
            self._set_status("Passwords do not match.")
            return
        if len(password) < 6:
            self._set_status("Password must be at least 6 characters.")
            return
        account = self.manager.account
        if account is None or not account.is_configured():
            self._set_status("Supabase is not configured.")
            return
        if account.is_busy:
            self._set_status("Please wait, finishing previous request...")
            return
        self._busy = True
        self.register_button.enabled = False
        self._set_status("Creating account...")

        def ok(_user):
            self._busy = False
            self.register_button.enabled = True
            if account.status == "pending_verification":
                self._set_status("Account created. Please verify your email, then log in.")
            else:
                profile = account.profile
                if profile is not None and account.current_user is not None:
                    from vector_drift.account.integration import apply_profile_to_session
                    apply_profile_to_session(self.session, profile, account.current_user.id, account.current_user.email)
                from .menu import MenuScene
                self.manager.switch(MenuScene(self.manager))

        def err(exc):
            self._busy = False
            self.register_button.enabled = True
            self._set_status(f"Register failed: {exc}")

        account.sign_up_async(email, password, on_success=ok, on_error=err)

    def _set_status(self, msg):
        self.status = msg

    def update(self, dt):
        pass

    def draw(self, surface):
        surface.blit(self.background, (0, 0))
        cx = config.WINDOW_W // 2
        draw_text(surface, "REGISTER", (cx, px(120)), 40, config.TEXT, kind="bold", anchor="center")
        draw_text(surface, "Email", (cx - px(180), px(196)), 14, config.TEXT_DIM, anchor="midleft")
        draw_text(surface, "Password", (cx - px(180), px(256)), 14, config.TEXT_DIM, anchor="midleft")
        draw_text(surface, "Confirm", (cx - px(180), px(316)), 14, config.TEXT_DIM, anchor="midleft")
        self.email_input.draw(surface)
        self.password_input.draw(surface)
        self.confirm_input.draw(surface)
        self.register_button.draw(surface)
        self.back_button.draw(surface)
        if self.status:
            draw_text(surface, self.status, (cx, px(470)), 15, config.WARNING, anchor="center")
