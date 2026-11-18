"""The game screen's function picker: the player's saved functions.

The game screen has a "Lab" button that opens this small modal list of the
functions the player saved in the Function Lab.  Picking one writes its
formulas into the Fx / Fy editor, so a saved function can be used in any
normal level.

The module only reads the player's library and talks to the editor; it does
not touch the flight, the level or the physics.
"""

import pygame

from .. import config
from ..config import px
from ..ui import Button, draw_text, fit_text

CARD_W, CARD_H = 560, 360
ROW_H = 40
MAX_ROWS = 6
TITLE = "SAVED FUNCTIONS"


def library(session):
    """The player's saved functions (SavedFunction objects)."""
    from ..function_library import SavedFunction

    functions = []
    for item in getattr(session, "function_library", ()) or ():
        if isinstance(item, SavedFunction):
            functions.append(item)
        elif isinstance(item, dict):
            function = SavedFunction.from_row(item)
            if function is not None:
                functions.append(function)
    return functions


def card_rect():
    """The modal card in the middle of the screen."""
    card = pygame.Rect(0, 0, px(CARD_W), px(CARD_H))
    card.center = (config.WINDOW_W // 2, config.WINDOW_H // 2)
    return card


def open_popup(scene):
    """Show the picker."""
    scene.lab_popup = True
    scene.lab_page = 0
    scene.ai_popup = False          # only one modal at a time
    layout(scene)


def close_popup(scene):
    """Hide the picker."""
    scene.lab_popup = False
    scene.lab_rows = []


def layout(scene):
    """(function, rect) for every visible row; also places the buttons."""
    card = card_rect()
    functions = library(scene.session)
    pages = max(1, -(-len(functions) // MAX_ROWS))
    page = max(0, min(getattr(scene, "lab_page", 0), pages - 1))
    scene.lab_page = page
    scene.lab_pages = pages
    rows = []
    y = card.y + px(76)
    for function in functions[page * MAX_ROWS:(page + 1) * MAX_ROWS]:
        rect = pygame.Rect(card.x + px(16), y, card.w - px(32), px(ROW_H) - px(4))
        rows.append((function, rect))
        y += px(ROW_H)
    scene.lab_rows = rows
    scene.lab_card = card
    by = card.bottom - px(52)
    scene.lab_prev_button.rect = pygame.Rect(card.x + px(16), by, px(70), px(34))
    scene.lab_next_button.rect = pygame.Rect(card.x + px(94), by, px(70), px(34))
    scene.lab_close_button.rect = pygame.Rect(card.right - px(106), by, px(90), px(34))
    scene.lab_prev_button.enabled = page > 0
    scene.lab_next_button.enabled = page < pages - 1


def load(scene, function):
    """Write a saved function into the Fx / Fy editor.

    The function is also marked as the one the player is using, so a launch
    or a clear with it counts toward the community usage statistics when it
    came from the community — picking it from this list is what "using" it
    means.
    """
    scene.editor.set_lines([function.fx, function.fy])
    scene.session.imported_function_id = function.id
    scene._on_text_change(scene.editor)
    try:
        from ..account.integration import save_progress
        save_progress(getattr(scene.manager, "account", None), scene.session)
    except Exception:  # noqa: BLE001 - persisting the selection must not block the picker
        pass
    close_popup(scene)


def handle_event(scene, event) -> bool:
    """Handle one event; True when the picker consumed it."""
    if not getattr(scene, "lab_popup", False):
        return False
    layout(scene)
    if event.type == pygame.KEYDOWN:
        if event.key == pygame.K_ESCAPE:
            close_popup(scene)
            return True
        return True                       # modal: the keys belong to the picker
    if event.type == pygame.MOUSEMOTION:
        scene.lab_prev_button.handle_event(event)
        scene.lab_next_button.handle_event(event)
        scene.lab_close_button.handle_event(event)
        return True                       # modal: the hover belongs to the picker
    if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
        for function, rect in scene.lab_rows:
            if rect.collidepoint(event.pos):
                load(scene, function)
                return True
        if scene.lab_prev_button.handle_event(event) == "click":
            scene.lab_page -= 1
            layout(scene)
            return True
        if scene.lab_next_button.handle_event(event) == "click":
            scene.lab_page += 1
            layout(scene)
            return True
        if scene.lab_close_button.handle_event(event) == "click":
            close_popup(scene)
            return True
        # A click outside the card closes the picker; a click inside it does
        # nothing else.
        if not scene.lab_card.collidepoint(event.pos):
            close_popup(scene)
        return True
    if event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
        return True
    return False


def draw(surface, scene):
    """The modal card with the list of saved functions."""
    if not getattr(scene, "lab_popup", False):
        return
    layout(scene)
    shade = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
    shade.fill((5, 8, 18, 200))
    surface.blit(shade, (0, 0))

    card = scene.lab_card
    pygame.draw.rect(surface, config.PANEL_BG, card, border_radius=px(6))
    pygame.draw.rect(surface, config.ACCENT, card, width=max(1, px(1)), border_radius=px(6))
    draw_text(surface, TITLE, (card.centerx, card.y + px(26)), 26, config.TEXT,
              kind="bold", anchor="center")

    functions = library(scene.session)
    imported = getattr(scene.session, "imported_function_id", None)
    if not functions:
        draw_text(surface, "No saved functions yet.", (card.centerx, card.y + px(120)), 16,
                  config.TEXT_DIM, anchor="center")
        draw_text(surface, "Open the Function Lab from the level select to write one.",
                  (card.centerx, card.y + px(146)), 14, config.TEXT_FAINT, anchor="center")
    else:
        mouse = pygame.mouse.get_pos()
        for function, rect in scene.lab_rows:
            hovered = rect.collidepoint(mouse)
            pygame.draw.rect(surface, config.EDITOR_LINE_HL if hovered else config.EDITOR_BG,
                             rect, border_radius=px(4))
            color = config.ACCENT if function.id == imported else config.TEXT
            draw_text(surface, fit_text(function.name, rect.w // 2 - px(20), 16, "bold"),
                      (rect.x + px(10), rect.centery), 16, color, kind="bold",
                      anchor="midleft")
            label = f"Fx {function.fx}    Fy {function.fy}"
            draw_text(surface, fit_text(label, rect.w // 2 - px(20), 12, "mono"),
                      (rect.right - px(10), rect.centery), 12, config.TEXT_DIM,
                      kind="mono", anchor="midright")
        if scene.lab_pages > 1:
            draw_text(surface, f"Page {scene.lab_page + 1} / {scene.lab_pages}",
                      (card.centerx, card.bottom - px(52)), 13, config.TEXT_DIM,
                      anchor="center")
    scene.lab_prev_button.draw(surface)
    scene.lab_next_button.draw(surface)
    scene.lab_close_button.draw(surface)
