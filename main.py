"""Vector Drift - entry point.  Run:  python main.py"""

import os


def set_mode(pygame, size, flags=0):
    """pygame.display.set_mode with a readable error message."""
    try:
        return pygame.display.set_mode(size, flags)
    except pygame.error as exc:
        raise RuntimeError(
            f"Vector Drift cannot open a {size[0]}x{size[1]} window: {exc}") from exc


def open_display():
    import pygame
    from vector_drift import config
    """Return (display, canvas, offset). The game draws on `canvas`, a
    WINDOW_W x WINDOW_H area centered on the display."""
    if config.FULLSCREEN:
        # A borderless window covering the desktop, not SDL's exclusive
        # fullscreen: the exclusive window gets special focus handling that
        # kept the Win+Shift+S snipping overlay from capturing the game.
        os.environ.setdefault("SDL_VIDEO_WINDOW_POS", "0,0")
        # config.SCREEN_SIZE is the only source of truth: the window and the
        # canvas are built from the same numbers, so the canvas can never be
        # bigger than the window (which would cut the game off).
        dw, dh = config.SCREEN_SIZE
        if not dw or not dh:
            # No desktop size (no video driver): fall back to a plain window.
            display = set_mode(pygame, (config.WINDOW_W, config.WINDOW_H))
            return display, display, (0, 0)
        display = set_mode(pygame, (dw, dh), pygame.NOFRAME)
        w, h = min(config.WINDOW_W, dw), min(config.WINDOW_H, dh)
        offset = ((dw - w) // 2, (dh - h) // 2)
        display.fill(config.BG)
        return display, display.subsurface((*offset, w, h)), offset
    display = set_mode(pygame, (config.WINDOW_W, config.WINDOW_H))
    return display, display, (0, 0)


def margin_rects(display, canvas, offset):
    """The display areas outside the canvas (letterbox strips)."""
    dw, dh = display.get_size()
    cw, ch = canvas.get_size()
    ox, oy = offset
    rects = [(0, 0, dw, oy), (0, oy + ch, dw, dh - oy - ch), (0, oy, ox, ch), (ox + cw, oy, dw - ox - cw, ch)]
    return [r for r in rects if r[2] > 0 and r[3] > 0]


def to_canvas(event, offset):
    import pygame
    MOUSE_EVENTS = (pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP)
    """Shift mouse positions from display to canvas coordinates."""
    if offset == (0, 0) or event.type not in MOUSE_EVENTS:
        return event
    data = dict(event.dict)
    data["pos"] = (event.pos[0] - offset[0], event.pos[1] - offset[1])
    return pygame.event.Event(event.type, data)


def main():
    import pygame
    from vector_drift import config
    from vector_drift.audio import SoundBank
    from vector_drift.desktop import disable_ime
    from vector_drift.scenes.base import SceneManager
    from vector_drift.scenes.menu import MenuScene
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

    from vector_drift.account import AccountManager
    account_manager = AccountManager()
    manager = SceneManager(audio, account_manager=account_manager)
    manager.screen = screen

    try:
        from vector_drift.account.integration import load_guest_profile_into_session
        load_guest_profile_into_session(manager.session)
    except Exception:
        pass

    if account_manager.is_configured():
        def _on_restored(_user):
            profile = account_manager.profile
            if profile is not None and account_manager.current_user is not None:
                from vector_drift.account.integration import (
                    apply_best_profile,
                    save_guest_profile,
                    save_progress,
                )
                # 先將目前未登入賺的進度寫入本地，避免登入後被雲端舊資料覆蓋。
                save_guest_profile(manager.session)
                chosen = apply_best_profile(
                    manager.session, profile,
                    account_manager.current_user.id,
                    account_manager.current_user.email,
                )
                # 本地較新且雲端已有資料時，把本地推回雲端，讓兩端收斂。
                if chosen is not None and chosen is not profile and profile is not None:
                    save_progress(account_manager, manager.session)

        account_manager.restore_session_async(on_success=_on_restored, on_error=lambda _e: None)

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
