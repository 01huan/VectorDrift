"""Intro story: the panels of intro_story.toml, one at a time.

A panel shows its picture fitted to the screen (or, until the picture
exists, its scene description as dim placeholder text) with the line in a
subtitle box. Panels fade out and in; the line fades in once the picture
is up. Click / Space / Right: next (while a panel is still fading in, the
first press only shows it in full). Left: back. Esc or Skip ends the story
at once, and Next on the last panel ends it too.
"""

import pygame

from .. import config
from ..config import px
from ..image_assets import load_image, source_size
from ..intro_story import story_panels
from ..ui import Button, draw_text, wrap_text
from .base import Scene

FADE_S = 0.3                # a panel fades out / in this long
LINE_FADE_S = 0.4           # then its line fades in this long
STORY_BG = (6, 9, 20)       # behind a picture, and the placeholder panel
PLACEHOLDER_SIZE = 16       # scene description font size (logical px)
PLACEHOLDER_W = 760         # ... wrapped to this width
LINE_SIZE = 20
SPEAKER_SIZE = 15
SUBTITLE_BOX = (80, 128, 110)   # logical px: side margin, height, bottom gap (above Skip)
SUBTITLE_FILL = (8, 12, 26, 205)
CONTROLS_TEXT = "Click / Space / → next    ← back    Esc skip"


def scene_after_story(manager):
    """Where the intro story ends (played through or skipped): the one place to change it.

    For now always level select; a tutorial mode would go here.
    """
    from .levels import LevelSelectScene
    return LevelSelectScene(manager)


class StoryScene(Scene):
    music = None            # set to "opening" when that track exists, else the music stays

    def __init__(self, manager):
        super().__init__(manager)
        if "opening" in (getattr(self.audio, "music_paths", None) or {}):
            self.music = "opening"
        self.panels = story_panels()
        self.index = 0
        self.t = 0.0                # time since this panel started fading in
        self.revealed = False       # Next pressed while fading in: shown in full
        self.leaving_to = None      # index being faded over to (fading out), else None
        self.out_t = 0.0
        self.skip_button = Button((config.WINDOW_W - px(140), config.WINDOW_H - px(62),
                                   px(110), px(40)), "Skip", style="plain", font_size=16)

    # --- state ---------------------------------------------------------------
    @property
    def panel(self):
        return self.panels[self.index]

    @property
    def counter_text(self):
        return f"{self.index + 1} / {len(self.panels)}"

    @property
    def fully_shown(self):
        return self.leaving_to is None and (self.revealed or self.t >= FADE_S + LINE_FADE_S)

    @property
    def dark_alpha(self):
        """How dark the fade over the panel is: 255 black, 0 clear."""
        if self.leaving_to is not None:
            return round(255 * min(1.0, self.out_t / FADE_S))
        if self.revealed:
            return 0
        return round(255 * max(0.0, 1.0 - self.t / FADE_S))

    @property
    def line_alpha(self):
        """The line fades in after the picture (255 at once once revealed)."""
        if self.revealed:
            return 255
        return round(255 * min(1.0, max(0.0, (self.t - FADE_S) / LINE_FADE_S)))

    # --- moving between panels ----------------------------------------------
    def next(self):
        if self.leaving_to is not None:
            return                              # already on the way to a panel
        if not self.fully_shown:
            self.revealed = True                # first press: show it all
            return
        if self.index + 1 >= len(self.panels):
            self.finish()
            return
        self._leave_to(self.index + 1)

    def back(self):
        if self.leaving_to is not None or self.index == 0:
            return
        self._leave_to(self.index - 1)

    def _leave_to(self, index):
        self.leaving_to = index
        self.out_t = 0.0

    def finish(self):
        """End the story (last panel, Skip or Esc)."""
        self.manager.switch(scene_after_story(self.manager))

    # --- scene ------------------------------------------------------------------
    def handle_event(self, event):
        if self.skip_button.handle_event(event) == "click":
            self.audio.play("click")
            self.finish()
            return
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.finish()
            elif event.key in (pygame.K_SPACE, pygame.K_RIGHT):
                self.next()
            elif event.key == pygame.K_LEFT:
                self.back()
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.next()

    def update(self, dt):
        if self.leaving_to is not None:
            self.out_t += dt
            if self.out_t >= FADE_S:
                self.index, self.leaving_to = self.leaving_to, None
                self.t, self.revealed = 0.0, False
            return
        self.t += dt

    def draw(self, surface):
        surface.fill(STORY_BG)
        if not self._draw_picture(surface):
            self._draw_placeholder(surface)
        if self.line_alpha:
            self._draw_subtitle(surface)
        dark = self.dark_alpha                  # one veil fades the picture and the line
        if dark:
            veil = pygame.Surface(surface.get_size())
            veil.fill((0, 0, 0))
            veil.set_alpha(dark)
            surface.blit(veil, (0, 0))
        draw_text(surface, self.counter_text, (config.WINDOW_W - px(30), px(24)), 16,
                  config.TEXT_DIM, kind="bold", anchor="topright")
        draw_text(surface, CONTROLS_TEXT, (config.WINDOW_W // 2, config.WINDOW_H - px(42)), 13,
                  config.TEXT_FAINT, anchor="center")
        self.skip_button.draw(surface)

    def _draw_picture(self, surface):
        """The panel's picture fitted to the screen, keeping its shape; False if there is none."""
        size = source_size(self.panel.image)
        if size is None or not size[0] or not size[1]:
            return False
        sw, sh = surface.get_size()
        scale = min(sw / size[0], sh / size[1])
        fit = (max(1, round(size[0] * scale)), max(1, round(size[1] * scale)))
        img = load_image(self.panel.image, size_px=fit)
        if img is None:
            return False
        surface.blit(img, img.get_rect(center=(sw // 2, sh // 2)))
        return True

    def _draw_placeholder(self, surface):
        """No picture yet: the scene description, small and dim, in the middle."""
        lines = wrap_text(self.panel.scene, PLACEHOLDER_SIZE, px(PLACEHOLDER_W))
        step = px(PLACEHOLDER_SIZE + 8)
        y = config.WINDOW_H * 0.4 - step * (len(lines) - 1) / 2
        for i, line in enumerate(lines):
            draw_text(surface, line, (config.WINDOW_W // 2, round(y + i * step)), PLACEHOLDER_SIZE,
                      config.TEXT_FAINT, anchor="center")

    def _draw_subtitle(self, surface):
        """The line in a see-through box at the bottom; the narrator has no name and dimmer text."""
        margin, height, gap = SUBTITLE_BOX
        box = pygame.Rect(px(margin), config.WINDOW_H - px(gap) - px(height),
                          config.WINDOW_W - 2 * px(margin), px(height))
        layer = pygame.Surface(box.size, pygame.SRCALPHA)
        pygame.draw.rect(layer, SUBTITLE_FILL, layer.get_rect(), border_radius=px(6))
        x, y = px(24), px(18)
        speaker = self.panel.speaker
        if speaker:
            draw_text(layer, speaker, (x, y), SPEAKER_SIZE, config.ACCENT, kind="bold")
            y += px(SPEAKER_SIZE + 10)
            color = config.TEXT
        else:
            y += px(SPEAKER_SIZE + 10) // 2
            color = config.TEXT_DIM             # narrator: no name, dimmer
        for line in wrap_text(self.panel.line, LINE_SIZE, box.width - 2 * x):
            draw_text(layer, line, (x, y), LINE_SIZE, color)
            y += px(LINE_SIZE + 8)
        layer.set_alpha(self.line_alpha)
        surface.blit(layer, box.topleft)
