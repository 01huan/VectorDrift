"""Vector Drift - entry point.  Run:  python main.py"""

import os

import pygame

from vector_drift import config
from vector_drift.audio import SoundBank
from vector_drift.desktop import disable_ime
from vector_drift.scenes.base import SceneManager
from vector_drift.scenes.menu import MenuScene

MOUSE_EVENTS = (pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP)


def open_display():
    """Return (display, canvas, offset). The game draws on `canvas`, a
    WINDOW_W x WINDOW_H area centered on the display."""
    if config.FULLSCREEN:
        # A borderless window covering the desktop, not SDL's exclusive
        # fullscreen: the exclusive window gets special focus handling that
        # kept the Win+Shift+S snipping overlay from capturing the game.
        os.environ.setdefault("SDL_VIDEO_WINDOW_POS", "0,0")
        dw, dh = pygame.display.get_desktop_sizes()[0]                  # desktop resolution
        display = pygame.display.set_mode((dw, dh), pygame.NOFRAME)
        w, h = min(config.WINDOW_W, dw), min(config.WINDOW_H, dh)
        offset = ((dw - w) // 2, (dh - h) // 2)
        display.fill(config.BG)
        return display, display.subsurface((*offset, w, h)), offset
    display = pygame.display.set_mode((config.WINDOW_W, config.WINDOW_H))
    return display, display, (0, 0)


def margin_rects(display, canvas, offset):
    """The display areas outside the canvas (letterbox strips)."""
    dw, dh = display.get_size()
    cw, ch = canvas.get_size()
    ox, oy = offset
    rects = [(0, 0, dw, oy), (0, oy + ch, dw, dh - oy - ch), (0, oy, ox, ch), (ox + cw, oy, dw - ox - cw, ch)]
    return [r for r in rects if r[2] > 0 and r[3] > 0]


def to_canvas(event, offset):
    """Shift mouse positions from display to canvas coordinates."""
    if offset == (0, 0) or event.type not in MOUSE_EVENTS:
        return event
    data = dict(event.dict)
    data["pos"] = (event.pos[0] - offset[0], event.pos[1] - offset[1])
    return pygame.event.Event(event.type, data)


def main():
    pygame.mixer.pre_init(44100, -16, 2, 512)
    pygame.init()
    if pygame.mixer.get_init() is None:
        try:
            pygame.mixer.init()
        except pygame.error:
            pass

    display, screen, offset = open_display()
    margins = margin_rects(display, screen, offset)
    pygame.display.set_caption(config.TITLE)
    pygame.key.set_repeat(400, 35)
    disable_ime()
    clock = pygame.time.Clock()

    audio = SoundBank()
    audio.start_music()
    manager = SceneManager(audio)
    manager.screen = screen
    manager.switch(MenuScene(manager))

    while manager.running:
        dt = clock.tick(config.FPS) / 1000.0
        for event in pygame.event.get():
            if event.type == pygame.WINDOWFOCUSGAINED:
                disable_ime()          # keep the IME detached after alt-tab
            manager.handle_event(to_canvas(event, offset))
            if not manager.running:
                break
        manager.update(dt)
        manager.draw(screen)
        for rect in margins:
            display.fill(config.BG, rect)
        pygame.display.flip()

    pygame.quit()


if __name__ == "__main__":
    main()
