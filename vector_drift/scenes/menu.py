"""Main menu: Start / Quit over an animated starfield."""

import math

import pygame

from .. import config, render, sprites
from ..config import px
from ..coords import Viewport
from ..data import SHIPS
from ..physics import ForceField
from ..ui import Button, draw_text
from .base import Scene


class MenuScene(Scene):
    music = "menu"

    def __init__(self, manager):
        super().__init__(manager)
        size = (config.WINDOW_W, config.WINDOW_H)
        self.background = render.make_space_background(size, seed=3, star_count=300)
        self._make_swirl()
        cx = config.WINDOW_W // 2
        self.start_button = Button((cx - px(110), px(400), px(220), px(54)), "Start", font_size=22)
        self.quit_button = Button((cx - px(110), px(470), px(220), px(54)), "Quit", style="plain", font_size=22)
        self.account_button = Button((config.WINDOW_W - px(180), px(20), px(160), px(40)), "Account", style="plain", font_size=15)
        self.login_menu_button = Button((cx - px(110), px(540), px(220), px(46)), "Login", style="primary", font_size=18)
        self.t = 0.0

    def _make_swirl(self):
        """Faint decorative rotational field behind the title."""
        vp = Viewport((0, 0, config.WINDOW_W, config.WINDOW_H), scale=64 * config.UI_SCALE)
        layer, _ = render.make_field_layer(vp, ForceField(b=-0.6, d=0.6, a=-0.08, e=-0.08))
        layer.set_alpha(90)
        self.swirl = layer

    def handle_event(self, event):
        if event.type == pygame.MOUSEMOTION:
            self.account_button.handle_event(event)
            self.login_menu_button.handle_event(event)
        if self.start_button.handle_event(event) == "click" or (
                event.type == pygame.KEYDOWN and event.key == pygame.K_RETURN):
            self.audio.play("click")
            from ..story import INTRO_SEEN
            if INTRO_SEEN not in self.session.story_seen:
                from .intro import IntroScene
                self.manager.switch(IntroScene(self.manager))
            else:
                from .levels import LevelSelectScene
                self.manager.switch(LevelSelectScene(self.manager))
        elif self.quit_button.handle_event(event) == "click":
            self.audio.play("click")
            self.manager.quit()
        elif self.login_menu_button.handle_event(event) == "click":
            self.audio.play("click")
            account = self.manager.account
            if account is not None and account.is_authenticated():
                from .account import AccountScene
                self.manager.switch(AccountScene(self.manager))
            else:
                from .auth import LoginScene
                self.manager.switch(LoginScene(self.manager))
        elif self.account_button.handle_event(event) == "click":
            self.audio.play("click")
            account = self.manager.account
            if account is not None and account.is_authenticated():
                from .account import AccountScene
                self.manager.switch(AccountScene(self.manager))
            else:
                from .auth import LoginScene
                self.manager.switch(LoginScene(self.manager))
        elif event.type == pygame.KEYDOWN and event.key == pygame.K_l:
            self.audio.play("click")
            account = self.manager.account
            if account is not None and account.is_authenticated():
                from .account import AccountScene
                self.manager.switch(AccountScene(self.manager))
            else:
                from .auth import LoginScene
                self.manager.switch(LoginScene(self.manager))

    def update(self, dt):
        self.t += dt

    def draw(self, surface):
        surface.blit(self.background, (0, 0))
        surface.blit(self.swirl, (0, 0))
        sprites.draw_target(surface, (px(150), config.WINDOW_H - px(90)), px(120), self.t)

        # A ship drifting along an ellipse, nose along its velocity.
        a, b, w = px(430), px(230), 0.35
        cx, cy = config.WINDOW_W / 2, config.WINDOW_H / 2 + px(10)
        th = self.t * w
        pos = (cx + a * math.cos(th), cy - b * math.sin(th))
        heading = math.atan2(b * math.cos(th), -a * math.sin(th))
        sprites.draw_ship(surface, pos, heading, px(64), SHIPS["ship01"])

        draw_text(surface, "VECTOR DRIFT", (config.WINDOW_W // 2 + px(4), px(195)), 76, config.OUTLINE,
                  kind="bold", anchor="center")
        draw_text(surface, "VECTOR DRIFT", (config.WINDOW_W // 2, px(190)), 76, config.TEXT,
                  kind="bold", anchor="center")
        draw_text(surface, "Design a force field. Let physics fly the ship.",
                  (config.WINDOW_W // 2, px(262)), 22, config.ACCENT, anchor="center")
        self.start_button.draw(surface)
        self.quit_button.draw(surface)
        account = self.manager.account
        if account is not None and account.is_authenticated():
            self.login_menu_button.label = "Account"
        else:
            self.login_menu_button.label = "Login"
        if account is not None:
            self.login_menu_button.enabled = not account.is_busy
        self.login_menu_button.draw(surface)
        if account is not None and account.is_authenticated():
            self.account_button.label = "Account"
        else:
            self.account_button.label = "Login"
        if account is not None:
            self.account_button.enabled = not account.is_busy
        self.account_button.draw(surface)
        if account is not None and account.is_authenticated() and account.current_user is not None:
            draw_text(surface, account.current_user.email or "", (config.WINDOW_W - px(10), px(68)), 13,
                      config.TEXT_DIM, anchor="midright")
        draw_text(surface, "Enter: launch   L: login/account   Ctrl+M: mute",
                  (config.WINDOW_W // 2, config.WINDOW_H - px(26)), 14, config.TEXT_FAINT, anchor="center")
