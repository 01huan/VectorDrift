"""Daily challenge page: today's date, Play and a calendar of the player's days.

Reached from the level select's Daily button. Play decides the day
(daily_level.daily_today(), UTC+8) and starts its map; Restart / Retry /
Replay inside the game keep that day (session.daily_day).

The calendar shows one month, Sunday first. Each day is marked from its
record (daily_records.py): cleared (a check), cleared after paying for the
answer (an "A" badge as well), played but not cleared (a cross), not played,
or still to come (dimmed). Today has an outline.
"""

import calendar
from collections import namedtuple

import pygame

from .. import config, daily_level, daily_records, render
from ..config import px
from ..image_assets import COIN_BALANCE
from ..ui import Button, draw_coins, draw_text, icon_surface
from .base import Scene
from .xp_ui import draw_level_row

# Layout in logical pixels (1280 x 720).
TITLE_Y = 70
DATE_Y = 112
LEFT_X, LEFT_Y, LEFT_W = 150, 170, 330      # left column: streaks, Play, legend
PLAY_Y = LEFT_Y + 146
PLAY_H = 56
LEGEND_Y = LEFT_Y + 240
LEGEND_SWATCH_W, LEGEND_SWATCH_H, LEGEND_ROW_H = 40, 28, 34

# Calendar card on the right: month title, weekday row, then up to six weeks.
CAL_X, CAL_Y = 540, 170                     # the day grid's left edge; the card's top
CELL_W, CELL_H, CELL_GAP = 76, 56, 6
MONTH_Y = CAL_Y + 22                        # month title (center)
WEEKDAY_Y = CAL_Y + 60                      # weekday names (center)
GRID_Y = CAL_Y + 78                         # first week's top
MAX_WEEKS = 6
CARD_PAD = 20
GRID_W = 7 * CELL_W + 6 * CELL_GAP
GRID_H = MAX_WEEKS * CELL_H + (MAX_WEEKS - 1) * CELL_GAP

CELL_FILL = (22, 30, 54)                    # a past day not played
CLEARED_FILL = (28, 78, 58)
FAILED_FILL = (78, 34, 44)
BADGE_R = 8

FIRST_WEEKDAY = calendar.SUNDAY
WEEKDAY_SHORT = ("Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat")
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December")


def long_date(day):
    """"Friday, November 20, 2026" (English whatever the system locale)."""
    return f"{WEEKDAYS[day.weekday()]}, {MONTHS[day.month - 1]} {day.day}, {day.year}"


def month_title(year, month):
    return f"{MONTHS[month - 1]} {year}"


# state: "cleared" | "failed" (a record, not cleared) | "none" (no record) | "future"
DayMarks = namedtuple("DayMarks", "state answer today")


def day_marks(record, day, today):
    """How the calendar marks ``day`` given its record (None: never played)."""
    if day > today:
        state, answer = "future", False
    elif record is None:
        state, answer = "none", False
    else:
        state = "cleared" if record.get("cleared") is True else "failed"
        answer = record.get("answer_used") is True
    return DayMarks(state, answer, day == today)


def month_weeks(year, month):
    """The month's weeks, Sunday first: lists of 7 dates (other months' days included)."""
    return calendar.Calendar(firstweekday=FIRST_WEEKDAY).monthdatescalendar(year, month)


def calendar_card_rect():
    """The calendar card: month title, weekdays and room for six weeks."""
    return pygame.Rect(px(CAL_X - CARD_PAD), px(CAL_Y - 4), px(GRID_W + 2 * CARD_PAD),
                       px(GRID_Y - CAL_Y + 4 + GRID_H + CARD_PAD))


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
        today = self.today()
        self.month = (today.year, today.month)      # the month on the calendar

    @staticmethod
    def today():
        """Asked again on every call: the page follows midnight (UTC+8) while open."""
        return daily_level.daily_today()

    def day_cells(self):
        """[(date, real-px rect)] of the shown month's days, in order."""
        year, month = self.month
        cells = []
        for row, week in enumerate(month_weeks(year, month)):
            for col, day in enumerate(week):
                if day.month == month:
                    cells.append((day, pygame.Rect(px(CAL_X + col * (CELL_W + CELL_GAP)),
                                                   px(GRID_Y + row * (CELL_H + CELL_GAP)),
                                                   px(CELL_W), px(CELL_H))))
        return cells

    def marks(self, day):
        return day_marks(daily_records.get_record(self.session, day), day, self.today())

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
        self._draw_legend(surface)
        self._draw_calendar(surface)

    def _draw_calendar(self, surface):
        card = calendar_card_rect()
        pygame.draw.rect(surface, config.PANEL_BG, card, border_radius=px(6))
        pygame.draw.rect(surface, config.PANEL_EDGE, card, width=max(1, px(1)), border_radius=px(6))
        draw_text(surface, month_title(*self.month), (px(CAL_X + GRID_W // 2), px(MONTH_Y)), 22,
                  config.TEXT, kind="bold", anchor="center")
        for col, name in enumerate(WEEKDAY_SHORT):
            draw_text(surface, name, (px(CAL_X + col * (CELL_W + CELL_GAP) + CELL_W // 2), px(WEEKDAY_Y)),
                      13, config.TEXT_DIM, kind="bold", anchor="center")
        for day, rect in self.day_cells():
            draw_day(surface, rect, str(day.day), self.marks(day))

    def _draw_legend(self, surface):
        x, y = px(LEFT_X), px(LEGEND_Y)
        draw_text(surface, "LEGEND", (x, y), 12, config.TEXT_DIM, kind="bold")
        y += px(24)
        samples = (("Cleared", DayMarks("cleared", False, False)),
                   ("Cleared, answer used", DayMarks("cleared", True, False)),
                   ("Played, not cleared", DayMarks("failed", False, False)),
                   ("Not played", DayMarks("none", False, False)),
                   ("Today", DayMarks("none", False, True)),
                   ("Not yet", DayMarks("future", False, False)))
        for label, marks in samples:
            rect = pygame.Rect(x, y, px(LEGEND_SWATCH_W), px(LEGEND_SWATCH_H))
            draw_day(surface, rect, "27" if marks.state == "future" else "", marks, small=True)
            draw_text(surface, label, (rect.right + px(12), rect.centery), 14, config.TEXT,
                      anchor="midleft")
            y += px(LEGEND_ROW_H)


def draw_day(surface, rect, number, marks, small=False):
    """One calendar day, or a legend swatch (``small``: smaller marks, centred number)."""
    radius = px(4 if small else 5)
    if marks.state == "future":
        if small:
            draw_text(surface, number, rect.center, 13, config.TEXT_FAINT, anchor="center")
        else:
            draw_text(surface, number, (rect.x + px(8), rect.y + px(6)), 14, config.TEXT_FAINT)
        return
    fill = {"cleared": CLEARED_FILL, "failed": FAILED_FILL}.get(marks.state, CELL_FILL)
    pygame.draw.rect(surface, fill, rect, border_radius=radius)
    if number:
        draw_text(surface, number, (rect.x + px(8), rect.y + px(6)), 14, config.TEXT)
    size = px(14 if small else 20)
    center = (rect.x + px(12), rect.centery) if small else (rect.centerx, rect.centery + px(8))
    if marks.state == "cleared":
        icon = icon_surface("check", size, config.SUCCESS)
        surface.blit(icon, icon.get_rect(center=center))
    elif marks.state == "failed":
        half, width = size // 3, max(2, px(3))
        cx, cy = center
        pygame.draw.line(surface, config.DANGER, (cx - half, cy - half), (cx + half, cy + half), width)
        pygame.draw.line(surface, config.DANGER, (cx - half, cy + half), (cx + half, cy - half), width)
    if marks.answer:
        badge = (rect.right - px(10), rect.y + px(10))
        pygame.draw.circle(surface, config.WARNING, badge, px(BADGE_R))
        draw_text(surface, "A", badge, 11, config.BG, kind="bold", anchor="center")
    if marks.today:
        pygame.draw.rect(surface, config.ACCENT, rect, width=max(2, px(2)), border_radius=radius)
