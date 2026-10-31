"""Opening crawl: the story text scrolls up and away into the stars.

Plays the first time Start is pressed (Session.story_seen), then goes on to
level select. Any key or click skips it.
"""

import pygame

from .. import config, render
from ..config import px
from ..story import INTRO_SEEN, get_story
from ..ui import draw_text, get_font, wrap_text
from .base import Scene

CRAWL_COLOR = (238, 200, 92)
TITLE_SIZE, SUBTITLE_SIZE, TEXT_SIZE = 64, 34, 30
TEXT_W = 760                    # logical width of the text column
LINE_GAP = 12
PARA_GAP = 40
HORIZON = 0.18                  # horizon height as a fraction of the screen
DEPTH = 0.9                     # how fast the text recedes (1 = rows keep their height at the bottom)
SPEED = 55                      # logical px of text per second at the bottom row
VANISH = 0.25                   # rows fade out as they shrink from 0.5 to this size
FADE_IN_S = 1.2


def _justified(line, font, width, color):
    """One text row stretched to ``width`` by spreading the word gaps."""
    words = line.split()
    imgs = [font.render(w, True, color) for w in words]
    surf = pygame.Surface((width, font.get_height()), pygame.SRCALPHA)
    if len(imgs) == 1:
        surf.blit(imgs[0], (0, 0))
        return surf
    gap = (width - sum(i.get_width() for i in imgs)) / (len(imgs) - 1)
    x = 0.0
    for img in imgs:
        surf.blit(img, (round(x), 0))
        x += img.get_width() + gap
    return surf


def render_crawl(intro):
    """The whole crawl as one tall transparent surface (real pixels)."""
    width = px(TEXT_W)
    pieces = []                                     # (surface, gap after, centered)
    title = get_font(TITLE_SIZE, "bold").render(intro.title, True, CRAWL_COLOR)
    subtitle = get_font(SUBTITLE_SIZE, "bold").render(intro.subtitle.upper(), True, CRAWL_COLOR)
    pieces += [(title, px(LINE_GAP), True), (subtitle, px(PARA_GAP * 2), True)]
    font = get_font(TEXT_SIZE, "bold")
    for paragraph in intro.paragraphs:
        rows = wrap_text(paragraph, TEXT_SIZE, width, kind="bold")
        for i, row in enumerate(rows):
            last = i == len(rows) - 1
            img = font.render(row, True, CRAWL_COLOR) if last else _justified(row, font, width, CRAWL_COLOR)
            pieces.append((img, px(PARA_GAP) if last else px(LINE_GAP), False))

    height = sum(img.get_height() + gap for img, gap, _ in pieces)
    crawl = pygame.Surface((width, height), pygame.SRCALPHA)
    y = 0
    for img, gap, centered in pieces:
        crawl.blit(img, ((width - img.get_width()) // 2 if centered else 0, y))
        y += img.get_height() + gap
    return crawl


class IntroScene(Scene):
    music = "opening"

    def __init__(self, manager):
        super().__init__(manager)
        size = (config.WINDOW_W, config.WINDOW_H)
        self.background = render.make_space_background(size, seed=11, star_count=320)
        self.crawl = render_crawl(get_story().intro)
        self.horizon = round(config.WINDOW_H * HORIZON)
        self.depth = config.WINDOW_H - self.horizon        # rows from horizon to bottom
        # Scroll = crawl row at the bottom of the screen; starts just below it.
        self.scroll = -px(40)
        self.t = 0.0
        self.finished = False

    def handle_event(self, event):
        if event.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN):
            self._finish()

    def _finish(self):
        if self.finished:
            return
        self.finished = True
        self.session.story_seen.add(INTRO_SEEN)
        from vector_drift.account.integration import save_progress
        save_progress(self.manager.account, self.session)
        from .levels import LevelSelectScene
        self.manager.switch(LevelSelectScene(self.manager))

    def update(self, dt):
        self.t += dt
        self.scroll += px(SPEED) * dt
        # Done once the last row has faded out in the distance.
        if self._source_row(self.depth * VANISH) > self.crawl.get_height():
            self._finish()

    def _source_row(self, d):
        """Crawl row seen ``d`` screen rows below the horizon (perspective)."""
        D = self.depth
        return self.scroll - (D / d - 1) * D * DEPTH

    def draw(self, surface):
        surface.blit(self.background, (0, 0))
        crawl, cw, ch = self.crawl, self.crawl.get_width(), self.crawl.get_height()
        cx = config.WINDOW_W // 2
        fade_in = min(1.0, self.t / FADE_IN_S)
        step = max(1, px(1))
        for d in range(step, self.depth + 1, step):
            v = int(self._source_row(d))
            if v < 0 or v >= ch:
                continue
            scale = d / self.depth
            alpha = min(1.0, (scale - VANISH) / VANISH) * fade_in
            if alpha <= 0:
                continue
            w = max(1, round(cw * scale))
            # Plain scale of a copied row: smoothscale on a 1-pixel-tall
            # subsurface crashes pygame-ce (access violation) on real displays.
            row = pygame.transform.scale(crawl.subsurface((0, v, cw, 1)).copy(), (w, step))
            if alpha < 1.0:
                row.set_alpha(round(255 * alpha))
            surface.blit(row, (cx - w // 2, self.horizon + d - step))
        draw_text(surface, "Press any key to skip", (config.WINDOW_W - px(20), config.WINDOW_H - px(18)),
                  13, config.TEXT_FAINT, anchor="midright")
