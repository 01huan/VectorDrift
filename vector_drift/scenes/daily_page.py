"""Daily challenge page: today's date and Play, reached from the level select's Daily button.

Play decides the day (daily_level.daily_today(), UTC+8) and starts its map;
Restart / Retry / Replay inside the game keep that day (session.daily_day).
"""

import pygame

from .. import config, daily_level, render
from ..config import px
from ..image_assets import COIN_BALANCE
from ..ui import Button, draw_coins, draw_text
from .base import Scene
from .xp_ui import draw_level_row

# Layout in logical pixels (1280 x 720).
TITLE_Y = 70
DATE_Y = 112
LEFT_X, LEFT_Y, LEFT_W = 150, 170, 330      # left column: streaks, Play
PLAY_Y = LEFT_Y + 146
PLAY_H = 56

WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December")


def long_date(day):
    """"Friday, November 20, 2026" (English whatever the system locale)."""
    return f"{WEEKDAYS[day.weekday()]}, {MONTHS[day.month - 1]} {day.day}, {day.year}"


class DailyScene(Scene):
    music = "menu"

    def __init__(self, manager):
        super().__init__(manager)
        self.background = render.make_space_background((config.WINDOW_W, config.WINDOW_H), seed=5,
                                                       star_count=260)
        self.play_button = Button((px(LEFT_X), px(PLAY_Y), px(LEFT_W), px(PLAY_H)), "Play",
                                  style="primary", font_size=20)
        self.back_button = Button((px(40), config.WINDOW_H - px(86), px(180), px(46)), "Back",
                                  style="plain", font_size=17)

    @staticmethod
    def today():
        """Asked again on every call: the page follows midnight (UTC+8) while open."""
        return daily_level.daily_today()

    # ------------------------------------------------------------------ actions
    def _play(self):
        """Today's map: the day is decided now, on Play."""
        self.audio.play("click")
        self.session.daily_day = self.today()
        from .levels import start_level
        start_level(self.manager, config.DAILY_LEVEL_ID)

    def _back(self):
        self.audio.play("click")
        from .levels import LevelSelectScene
        self.manager.switch(LevelSelectScene(self.manager))

    def handle_event(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self._back()
            elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self._play()
            return
        if self.play_button.handle_event(event) == "click":
            self._play()
            return
        if self.back_button.handle_event(event) == "click":
            self._back()

    # ------------------------------------------------------------------ draw
    def draw(self, surface):
        surface.blit(self.background, (0, 0))
        balance = draw_coins(surface, int(self.session.money), (px(12), px(12)), 16, config.TEXT,
                             icon=COIN_BALANCE)
        draw_level_row(surface, self.session.xp_total, (px(12), balance.bottom + px(8)))
        cx = config.WINDOW_W // 2
        draw_text(surface, "DAILY CHALLENGE", (cx, px(TITLE_Y)), 40, config.TEXT, kind="bold",
                  anchor="center")
        draw_text(surface, long_date(self.today()), (cx, px(DATE_Y)), 16, config.TEXT_DIM,
                  anchor="center")
        self.play_button.draw(surface)
        self.back_button.draw(surface)
