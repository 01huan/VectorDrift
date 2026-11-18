"""Intro story: the panels of intro_story.toml, one at a time.

A panel shows its picture fitted to the screen (or, without the picture,
its scene description as dim placeholder text) with the line in a subtitle
box. Panels fade out and in. Once the picture is up, the ship's lines
(speaker SHIP) are typed out at TYPE_CPS characters a second, with the
name and the box shown at once; the narrator's lines (no speaker) fade in.
A typed line is wrapped as the whole line first, so a word never jumps to
the next line while it is being typed; "…" is one character.

A picture slowly zooms in (Ken Burns): from 1.00x to ZOOM_END over ZOOM_S
seconds with an ease-out, about ZOOM_ANCHOR (a point of the screen; the
pictures keep their subject in the upper two thirds), then holds. The zoom
follows only how long the panel has been up, so showing a panel in full
does not jump it; it goes on while the panel fades out, and the next panel
starts again at 1.00x. Each panel loads its picture once, at the fitted
size times ZOOM_END, and every frame cuts the visible part out of it and
scales that to the screen (pygame.transform.scale: smoothscale is too slow
at 4K). The placeholder text does not zoom.

Click / Space / Right: next (while a panel is still fading in or its line
is still being typed, the first press only shows it in full). Left: back.
Esc or Skip ends the story at once, and Next on the last panel ends it
too. However it ends, it goes on to the tutorial screen
(scene_after_story): after the first Start and after the Tutorial button
on level select alike.
"""

import pygame

from .. import config
from ..config import px
from ..image_assets import load_image, source_size
from ..intro_story import story_panels
from ..ui import Button, draw_text, wrap_text
from .base import Scene

ZOOM_END = 1.06            # a picture zooms in to this ...
ZOOM_S = 8.0                # ... over this many seconds (ease-out), then holds
ZOOM_ANCHOR = (0.5, 0.4)    # the screen point (fractions of width, height) that stays put
FADE_S = 0.3                # a panel fades out / in this long
LINE_FADE_S = 0.4           # then the narrator's line fades in this long
TYPE_CPS = 35               # the ship's lines are typed out this many characters a second
TYPED_SPEAKER = "SHIP"      # whose lines are typed out
STORY_BG = (6, 9, 20)       # behind a picture, and the placeholder panel
PLACEHOLDER_SIZE = 16       # scene description font size (logical px)
PLACEHOLDER_W = 760         # ... wrapped to this width
LINE_SIZE = 20
SPEAKER_SIZE = 15
SUBTITLE_BOX = (80, 128, 110)   # logical px: side margin, height, bottom gap (above Skip)
SUBTITLE_FILL = (8, 12, 26, 205)
CONTROLS_TEXT = "Click / Space / → next    ← back    Esc skip"


def start_first_intro(manager):
    """First Start: mark the intro seen and save it now, then play it.

    Saved before the first panel, so quitting mid-story does not bring the
    player back to it next time.
    """
    from ..account.integration import save_progress
    manager.session.seen_intro = True
    save_progress(manager.account, manager.session)
    manager.switch(StoryScene(manager))


def scene_after_story(manager):
    """Where the story ends (played through, skipped or Esc): the one place to change it.

    The tutorial screen; it ends at level select.
    """
    from .tutorial_basics import BasicsScene
    return BasicsScene(manager)


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
        self._zoom_picture = None   # (key, screen size, the panel's picture at its largest size)
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
    def typed(self):
        """This panel's line is typed out (the ship speaks), not faded in."""
        return self.panel.speaker == TYPED_SPEAKER

    @property
    def typed_chars(self):
        """How many characters of the line are showing (all of it for the narrator)."""
        n = len(self.panel.line)
        if self.revealed or not self.typed:
            return n
        return min(n, max(0, int((self.t - FADE_S) * TYPE_CPS + 1e-6)))

    @property
    def fully_shown(self):
        if self.leaving_to is not None:
            return False
        if self.revealed:
            return True
        if self.typed:
            return self.typed_chars >= len(self.panel.line)
        return self.t >= FADE_S + LINE_FADE_S

    @property
    def zoom(self):
        """How far the picture has zoomed in: 1.0 when the panel starts, ZOOM_END after ZOOM_S."""
        p = min(1.0, max(0.0, self.t / ZOOM_S))
        return 1.0 + (ZOOM_END - 1.0) * (1.0 - (1.0 - p) ** 3)     # ease-out (cubic)

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
        """The subtitle box after the picture: at once for a typed line, faded in for
        the narrator (255 at once once revealed)."""
        if self.revealed:
            return 255
        if self.typed:
            return 255 if self.t >= FADE_S else 0
        return round(255 * min(1.0, max(0.0, (self.t - FADE_S) / LINE_FADE_S)))

    # --- moving between panels ----------------------------------------------
    def next(self):
        if self.leaving_to is not None:
            return                              # already on the way to a panel
        if not self.fully_shown:
            self.revealed = True                # first press: show it all
            return
        if self.index + 1 >= len(self.panels):
            from ..achievements import unlock
            unlock(self.manager, "is_anyone_out_there")     # played through, not skipped
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
        self.t += dt                            # keeps counting while fading out (the zoom goes on)
        if self.leaving_to is not None:
            self.out_t += dt
            if self.out_t >= FADE_S:
                self.index, self.leaving_to = self.leaving_to, None
                self.t, self.revealed = 0.0, False

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
        """The panel's picture fitted to the screen, keeping its shape, zoomed in by
        ``zoom`` about ZOOM_ANCHOR; False if there is none."""
        size = source_size(self.panel.image)
        if size is None or not size[0] or not size[1]:
            return False
        sw, sh = surface.get_size()
        scale = min(sw / size[0], sh / size[1])
        fit = (max(1, round(size[0] * scale)), max(1, round(size[1] * scale)))
        big = self._largest_picture(surface, fit)
        if big is None:
            return False
        box = pygame.Rect((0, 0), fit)
        box.center = (sw // 2, sh // 2)
        # The anchor as a point of the fitted picture (fractions), kept in place.
        fx = min(1.0, max(0.0, (sw * ZOOM_ANCHOR[0] - box.x) / fit[0]))
        fy = min(1.0, max(0.0, (sh * ZOOM_ANCHOR[1] - box.y) / fit[1]))
        bw, bh = big.get_size()
        zoom = self.zoom
        cw, ch = min(bw, max(1, round(bw / zoom))), min(bh, max(1, round(bh / zoom)))
        part = big.subsurface((round(fx * (bw - cw)), round(fy * (bh - ch)), cw, ch))
        try:
            pygame.transform.scale(part, fit, surface.subsurface(box))   # no new 4K surface
        except (ValueError, pygame.error):      # a target the scale cannot write into
            surface.blit(pygame.transform.scale(part, fit), box)
        return True

    def _largest_picture(self, surface, fit):
        """The panel's picture at its largest (fitted size times ZOOM_END), opaque in the
        screen's format. Asked from load_image once per panel and screen size."""
        key = self.panel.image
        want = (key, surface.get_size())
        if self._zoom_picture is None or self._zoom_picture[:2] != want:
            big_size = (max(1, round(fit[0] * ZOOM_END)), max(1, round(fit[1] * ZOOM_END)))
            img = load_image(key, size_px=big_size)
            if img is None:
                return None
            flat = pygame.Surface(img.get_size(), 0, surface)
            flat.fill(STORY_BG)
            flat.blit(img, (0, 0))
            self._zoom_picture = (*want, flat)
        return self._zoom_picture[2]

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
        left = self.typed_chars                 # wrapped as the whole line, then cut
        for line in wrap_text(self.panel.line, LINE_SIZE, box.width - 2 * x):
            shown = line[:max(0, left)]
            left -= len(line) + 1               # + the space the wrap took
            if shown:
                draw_text(layer, shown, (x, y), LINE_SIZE, color)
            y += px(LINE_SIZE + 8)
        layer.set_alpha(self.line_alpha)
        surface.blit(layer, box.topleft)
