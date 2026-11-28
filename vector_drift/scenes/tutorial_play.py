"""The game screen in tutorial mode (Basics and the element demos build on it).

It is the ordinary GameScene - same physics, field arrows, editor, timer,
pickup effects - on a map from tutorial.toml, with everything that would
outlast the tutorial turned off: no coins, clear reward, best time, replay,
save or achievement; endless lives with the lives row hidden; no Hint, AI Solver, Lab,
ability or level buttons. The session's formulas, ship and level are
put back on leaving, so no level's progress changes.
"""


import re

import pygame

from .. import config
from ..config import px
from ..tutorial import TUTORIAL_SHIP_ID
from ..ui_fonts import draw_text, get_font, _needs_cjk_font
from ..sprites.common import blink_value
from .game import GameScene
from .game_layout import ARRIVED

# Session fields a tutorial scene borrows and gives back.
BORROWED = ("fx_text", "fy_text", "editor_history", "ship_id", "level_id", "random_seed")
POINTER = (255, 214, 102)           # the arrow that points things out


def borrow_session(session):
    """What the tutorial changes in the session, to give back on leaving."""
    return {key: getattr(session, key, None) for key in BORROWED}


def give_back_session(session, saved):
    for key, value in (saved or {}).items():
        setattr(session, key, value)


class TutorialGameScene(GameScene):
    show_lives = False
    show_assists = False
    show_level_row = False
    show_abilities = False              # abilities do nothing here
    counts_for_progress = False         # achievements ignore this screen

    def __init__(self, manager, level, fx="", fy="", restore=None):
        session = manager.session
        self.restore = restore if restore is not None else borrow_session(session)
        self._tutorial_level = level
        session.ship_id = TUTORIAL_SHIP_ID
        session.fx_text, session.fy_text = fx, fy
        session.editor_history = None
        super().__init__(manager)

    # --- the map comes from tutorial.toml ---------------------------------------
    def _load_level(self):
        return self._tutorial_level

    def _level_ship_id(self):
        return TUTORIAL_SHIP_ID

    # --- nothing outlasts the tutorial ------------------------------------------
    def _spend_life(self):
        pass                            # endless lives

    def _miss_banner(self, reason, where):
        return (reason, where[:1].upper() + where[1:], config.BANNER_DURATION)

    def _persist(self):
        pass

    def _store_replay(self, outcome):
        pass

    def _record_clear(self):
        pass

    def _pay_clear_reward(self):
        pass

    def _record_community_stat(self, kind):
        pass

    def _record_function_usage(self, success):
        pass

    def _use_ability_key(self, key):
        return False

    def _hidden_buttons(self):
        return (self.level_button, self.lab_button, self.ai_button)

    def _refresh_buttons(self):
        super()._refresh_buttons()
        for button in (self.level_button, self.lab_button):
            button.enabled = False

    def _update_flight(self, dt):
        if self.state == ARRIVED:       # no Win screen: the scene decides what follows
            self.arrive_timer = max(0.0, self.arrive_timer - dt)
            return
        super()._update_flight(dt)

    # --- leaving ------------------------------------------------------------------
    def leave(self, target=None):
        """Give the session back and go to ``target`` (default: level select)."""
        self.audio.stop_loop("thruster_loop")
        give_back_session(self.session, self.restore)
        if target is None:
            from .levels import LevelSelectScene
            target = LevelSelectScene(self.manager)
        self.manager.switch(target)

    def handle_event(self, event):
        if event.type == pygame.MOUSEMOTION:
            self._mouse_pos = event.pos
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.audio.play("click")
            self.leave()
            return
        if event.type == pygame.MOUSEBUTTONDOWN and any(
                b.rect.collidepoint(event.pos) for b in self._hidden_buttons()):
            return
        super().handle_event(event)

    # --- drawing ------------------------------------------------------------------
    def draw(self, surface):
        surface.fill(config.BG)
        self._draw_plot(surface)
        self._draw_panel(surface)
        self._draw_fly_texts(surface)
        self.draw_overlay(surface)

    def draw_overlay(self, surface):
        """The tutorial's own captions and buttons (subclasses)."""

    def world_to_screen(self, point):
        return self.camera.to_screen(point[0], point[1])


# --- small drawing helpers -------------------------------------------------------------
def _segments(word, bold):
    """Split one word at its ** marks: ([(text, bold), ...], bold after it)."""
    parts = word.split("**")
    segs = []
    for k, part in enumerate(parts):
        if k:
            bold = not bold
        if part:
            segs.append((part, bold))
    return segs, bold


def _width(segs, size, cjk=False):
    return sum(get_font(size, "bold" if b else "ui", cjk=cjk).size(t)[0] for t, b in segs)


def rich_lines(text, size, width):
    """Wrap ``text`` (paragraphs split by newlines, **bold** marked) into lines
    of words, each word a list of (text, bold) pieces, no wider than ``width``.

    Translate the whole paragraph before splitting it: translating each word
    separately never matches a sentence in the catalog.  CJK text has no
    spaces, so it is wrapped per character with ``**`` kept as a bold marker.
    """
    from ..i18n import translate
    text = translate(text)
    cjk = _needs_cjk_font(text)
    space = 0 if cjk else get_font(size).size(" ")[0]
    lines = []
    for paragraph in text.splitlines():
        words = re.findall(r"\*\*|.", paragraph) if cjk else paragraph.split(" ")
        line, line_w, bold = [], 0, False
        for raw in words:
            segs, bold = _segments(raw, bold)
            if not segs:
                continue
            w = _width(segs, size, cjk)
            if line and line_w + space + w > width:
                lines.append(line)
                line, line_w = [], 0
            line_w += (space if line else 0) + w
            line.append(segs)
        lines.append(line)
    return lines


def draw_rich(surface, text, pos, width, size=16, color=config.TEXT, bold_color=config.ACCENT):
    """Draw wrapped rich text from its top-left; returns the height used."""
    from ..i18n import translate
    text = translate(text)
    cjk = _needs_cjk_font(text)
    x0, y = pos
    space = 0 if cjk else get_font(size).size(" ")[0]
    step = px(size + 7)
    for line in rich_lines(text, size, width):
        x = x0
        for segs in line:
            for piece, bold in segs:
                kind = "bold" if bold else "ui"
                draw_text(surface, piece, (x, y), size, bold_color if bold else color, kind=kind)
                x += get_font(size, kind, cjk=cjk).size(piece)[0]
            x += space
        y += step
    return y - pos[1]


def rich_height(text, width, size=16):
    return len(rich_lines(text, size, width)) * px(size + 7)


def draw_pointer(surface, tip, t, length=46):
    """A bobbing arrow from above, its point at ``tip``."""
    bob = px(6) * blink_value(t, 5.0)
    x, y = tip[0], tip[1] - px(14) - bob
    head = px(12)
    pygame.draw.line(surface, POINTER, (x, y - px(length)), (x, y - head // 2), max(3, px(4)))
    pygame.draw.polygon(surface, POINTER, [(x, y), (x - head, y - head), (x + head, y - head)])


def draw_attention_ring(surface, rect, t, pad=6, width=2):
    """A pulsing outline in the pointer colour around a control."""
    grow = px(pad) + round(px(2) * blink_value(t, 4.0))
    ring = rect.inflate(grow * 2, grow * 2)
    pygame.draw.rect(surface, POINTER, ring, max(2, px(width)), border_radius=px(6))
