"""Daily challenge page: today's date, Play and a calendar of the player's days.

Reached from the level select's Daily button. Play decides the day
(daily_level.daily_today(), UTC+8) and starts its map; Restart / Retry /
Replay inside the game keep that day (session.daily_day).

The calendar shows one month, Sunday first. Each day is marked from its
record (daily_records.py): cleared (a check), cleared after paying for the
answer (an "A" badge as well), played but not cleared (a cross), not played,
or still to come (dimmed). Today has an outline. The "<" / ">" arrows (or
the arrow keys) switch months, from the earliest month with a record up to
today's; the page always opens on today's month. Hovering a day with a
record shows it; no calendar day can be played (only today, through Play).
"""

import calendar
from collections import namedtuple
from datetime import date

import pygame

from .. import config, daily_level, daily_records, render
from ..config import px
from ..image_assets import COIN_BALANCE
from ..ui import Button, draw_coins, draw_text, icon_surface
from .base import Scene
from .levels import PageArrow
from .xp_ui import draw_level_row

# Layout in logical pixels (1280 x 720).
TITLE_Y = 70
DATE_Y = 112
LEFT_X, LEFT_Y, LEFT_W = 150, 170, 330      # left column: streaks, Play, legend
STREAK_BOX_H = 126
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
MONTH_ARROW_HIT = 44                        # the "<" / ">" click area beside the month title
MONTH_ARROW_INSET = 14                      # its center, in from the grid's edge
TOOLTIP_W, TOOLTIP_PAD, TOOLTIP_TITLE_H, TOOLTIP_ROW_H = 250, 10, 34, 20
TOOLTIP_GAP = 6                             # between the day and its tooltip

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


def tooltip_title(day):
    """"Thu, Nov 19"."""
    return f"{WEEKDAY_SHORT[(day.weekday() + 1) % 7]}, {MONTHS[day.month - 1][:3]} {day.day}"


def tooltip_rows(record):
    """(label, value, colour) lines of a played day's record."""
    cleared = record.get("cleared") is True
    best = record.get("best_time")
    lives = record.get("first_clear_lives_used")
    used = record.get("answer_used") is True
    return [
        ("Cleared", "Yes" if cleared else "No", config.SUCCESS if cleared else config.DANGER),
        ("Best time", f"{best:.2f} s" if best is not None else "—", config.TEXT),
        ("Lives lost (first clear)", str(lives) if lives is not None else "—", config.TEXT),
        ("Coins collected", str(record.get("coins", 0)), config.TEXT),
        ("Answer", "Used" if used else "Not used", config.WARNING if used else config.TEXT_DIM),
    ]


def streak_text(which, days):
    """"Current streak: 2 days" ("1 day" for one)."""
    return f"{which} streak: {days} {'day' if days == 1 else 'days'}"


def streak_box_rect():
    return pygame.Rect(px(LEFT_X), px(LEFT_Y), px(LEFT_W), px(STREAK_BOX_H))


def shift_month(month, step):
    """(year, month) ``step`` months after ``month`` (before, for a negative step)."""
    year, m = month
    index = year * 12 + (m - 1) + step
    return index // 12, index % 12 + 1


def month_range(records, today):
    """(first, last) months the calendar can show.

    The last is today's month; the first is the earliest month with a record,
    or today's month when that is earlier or there are no records.
    """
    last = (today.year, today.month)
    days = [date.fromisoformat(key) for key in records]     # keys are ISO days (daily_records)
    first = min([(d.year, d.month) for d in days] + [last])
    return first, last


def calendar_card_rect():
    """The calendar card: month title, weekdays and room for six weeks."""
    return pygame.Rect(px(CAL_X - CARD_PAD), px(CAL_Y - 4), px(GRID_W + 2 * CARD_PAD),
                       px(GRID_Y - CAL_Y + 4 + GRID_H + CARD_PAD))


class MonthArrow(PageArrow):
    """The level select's page arrow, smaller: switches the calendar's month."""

    glyph_size = (12, 24)
    stroke = 4


def _month_arrow(direction):
    rect = pygame.Rect(0, 0, px(MONTH_ARROW_HIT), px(MONTH_ARROW_HIT))
    x = CAL_X + MONTH_ARROW_INSET if direction < 0 else CAL_X + GRID_W - MONTH_ARROW_INSET
    rect.center = (px(x), px(MONTH_Y))
    return MonthArrow(direction, rect)


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
        self.month = (today.year, today.month)      # the month on the calendar: always today's at first
        self.prev_arrow = _month_arrow(-1)
        self.next_arrow = _month_arrow(1)
        self._refresh_arrows()
        self._mouse_pos = (-1, -1)

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

    def hovered_day(self):
        """The day under the mouse when it has a record to show (past days and today)."""
        for day, rect in self.day_cells():
            if rect.collidepoint(self._mouse_pos):
                if day <= self.today() and daily_records.get_record(self.session, day) is not None:
                    return day
                return None
        return None

    def tooltip_rect(self):
        """Where the hovered day's record shows: under the day, or above it near the bottom."""
        day = self.hovered_day()
        if day is None:
            return None
        cell = dict(self.day_cells())[day]
        box = pygame.Rect(0, 0, px(TOOLTIP_W),
                          px(2 * TOOLTIP_PAD + TOOLTIP_TITLE_H + 5 * TOOLTIP_ROW_H - TOOLTIP_ROW_H // 2))
        box.topleft = (cell.x, cell.bottom + px(TOOLTIP_GAP))
        if box.bottom > config.WINDOW_H - px(4):
            box.bottom = cell.y - px(TOOLTIP_GAP)
        box.right = min(box.right, config.WINDOW_W - px(4))
        return box

    def _refresh_arrows(self):
        """An arrow works only while there is a month that way (the range follows midnight)."""
        first, last = month_range(self.session.daily_records, self.today())
        self.prev_arrow.enabled = self.month > first
        self.next_arrow.enabled = self.month < last
        for arrow in (self.prev_arrow, self.next_arrow):
            if not arrow.enabled:
                arrow.hover = False

    def turn_month(self, step):
        """Show the month ``step`` (-1 / +1) away, if that arrow works."""
        self._refresh_arrows()
        arrow = self.prev_arrow if step < 0 else self.next_arrow
        if not arrow.enabled:
            return False
        self.audio.play("click")
        self.month = shift_month(self.month, step)
        self._refresh_arrows()
        return True

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
            elif event.key in (pygame.K_LEFT, pygame.K_RIGHT):
                self.turn_month(-1 if event.key == pygame.K_LEFT else 1)
            return
        if event.type == pygame.MOUSEMOTION:
            self._mouse_pos = event.pos
            self._refresh_arrows()
            for arrow in (self.prev_arrow, self.next_arrow):
                arrow.update_hover(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for arrow in (self.prev_arrow, self.next_arrow):
                if arrow.rect.collidepoint(event.pos):
                    self.turn_month(arrow.direction)    # a disabled arrow does nothing
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
        self._draw_streaks(surface)
        self.play_button.draw(surface)
        self.back_button.draw(surface)
        self._draw_legend(surface)
        self._draw_calendar(surface)

    def _draw_streaks(self, surface):
        """Days cleared in a row (answer days count): up to today, and the best run."""
        records = self.session.daily_records
        box = streak_box_rect()
        pygame.draw.rect(surface, config.PANEL_BG, box, border_radius=px(6))
        pygame.draw.rect(surface, config.PANEL_EDGE, box, width=max(1, px(1)), border_radius=px(6))
        x = box.x + px(20)
        draw_text(surface, "STREAK", (x, box.y + px(18)), 12, config.TEXT_DIM, kind="bold")
        draw_text(surface, streak_text("Current", daily_records.current_streak(records, self.today())),
                  (x, box.y + px(52)), 20, config.TEXT, kind="bold")
        draw_text(surface, streak_text("Longest", daily_records.longest_streak(records)),
                  (x, box.y + px(90)), 17, config.TEXT_DIM)

    def _draw_calendar(self, surface):
        card = calendar_card_rect()
        pygame.draw.rect(surface, config.PANEL_BG, card, border_radius=px(6))
        pygame.draw.rect(surface, config.PANEL_EDGE, card, width=max(1, px(1)), border_radius=px(6))
        draw_text(surface, month_title(*self.month), (px(CAL_X + GRID_W // 2), px(MONTH_Y)), 22,
                  config.TEXT, kind="bold", anchor="center")
        for col, name in enumerate(WEEKDAY_SHORT):
            draw_text(surface, name, (px(CAL_X + col * (CELL_W + CELL_GAP) + CELL_W // 2), px(WEEKDAY_Y)),
                      13, config.TEXT_DIM, kind="bold", anchor="center")
        self._refresh_arrows()
        self.prev_arrow.draw(surface)
        self.next_arrow.draw(surface)
        for day, rect in self.day_cells():
            draw_day(surface, rect, str(day.day), self.marks(day))
        self._draw_tooltip(surface)

    def _draw_tooltip(self, surface):
        """The hovered day's record (days without one show nothing; no day can be played)."""
        box = self.tooltip_rect()
        if box is None:
            return
        day = self.hovered_day()
        cell = dict(self.day_cells())[day]
        pygame.draw.rect(surface, config.TEXT_DIM, cell, width=max(1, px(1)), border_radius=px(5))
        pygame.draw.rect(surface, config.PANEL_BG, box, border_radius=px(5))
        pygame.draw.rect(surface, config.ACCENT, box, width=max(1, px(1)), border_radius=px(5))
        x, right = box.x + px(TOOLTIP_PAD), box.right - px(TOOLTIP_PAD)
        draw_text(surface, tooltip_title(day), (x, box.y + px(TOOLTIP_PAD)), 14, config.TEXT, kind="bold")
        y = box.y + px(TOOLTIP_PAD + TOOLTIP_TITLE_H)
        for label, value, color in tooltip_rows(daily_records.get_record(self.session, day)):
            draw_text(surface, label, (x, y), 13, config.TEXT_DIM, anchor="midleft")
            draw_text(surface, value, (right, y), 13, color, kind="mono", anchor="midright")
            y += px(TOOLTIP_ROW_H)

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
