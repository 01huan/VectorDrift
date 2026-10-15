"""Desktop-window helpers: input method and mouse cursor."""

import sys

import pygame

_current_cursor = None


def disable_ime():
    """Detach the system input method (e.g. Bopomofo) from the game window.

    Formulas only need ASCII, and with a CJK IME active the key presses would be
    swallowed into an IME composition instead of reaching the editor.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes
        from ctypes import wintypes
        hwnd = pygame.display.get_wm_info().get("window")
        if not hwnd:
            return
        imm = ctypes.windll.imm32
        imm.ImmAssociateContext.argtypes = [wintypes.HWND, wintypes.HANDLE]
        imm.ImmAssociateContext.restype = wintypes.HANDLE
        imm.ImmAssociateContext(hwnd, None)
    except (AttributeError, OSError, pygame.error):
        pass


def set_cursor(kind):
    """Switch the mouse cursor: 'arrow' or 'text' (I-beam). Cheap to call repeatedly."""
    global _current_cursor
    if kind == _current_cursor:
        return
    _current_cursor = kind
    cursor = pygame.SYSTEM_CURSOR_IBEAM if kind == "text" else pygame.SYSTEM_CURSOR_ARROW
    try:
        pygame.mouse.set_cursor(cursor)
    except pygame.error:          # e.g. headless video driver
        pass
