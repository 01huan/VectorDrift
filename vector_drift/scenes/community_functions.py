"""Community functions: browse and import force functions uploaded by others."""

from __future__ import annotations

import pygame

from .. import config, data
from ..config import px
from ..function_library import SavedFunction, clean_name, make_function
from ..ui import Button, draw_text, fit_text
from .base import Scene
from ..account import community as _community_mod
try:
    from ..account import community_functions as _community_functions_mod
except Exception:  # noqa: BLE001
    _community_functions_mod = _community_mod
# Patchable module aliases (mirror community_levels scene conventions).
community = _community_mod
community_functions = _community_functions_mod


_ORIGINAL_FETCH = {}
for _m in (_community_mod, _community_functions_mod):
    if _m is not None and hasattr(_m, "fetch_community_functions"):
        _ORIGINAL_FETCH[id(_m)] = _m.fetch_community_functions


def _community_module():
    # Prefer a module whose fetch function was patched at runtime.
    candidates = []
    for name in ("community_functions", "_community_functions_mod", "community", "_community_mod"):
        mod = globals().get(name)
        if mod is not None and hasattr(mod, "fetch_community_functions"):
            candidates.append(mod)
    for mod in candidates:
        if _ORIGINAL_FETCH.get(id(mod)) is not mod.fetch_community_functions:
            return mod
    return candidates[0] if candidates else _community_mod


class CommunityFunctionsScene(Scene):
    music = "menu"

    def __init__(self, manager):
        super().__init__(manager)
        self.back_button = Button((px(40), config.WINDOW_H - px(86), px(180), px(46)), "Levels",
                                   style="plain", font_size=17)
        self.refresh_button = Button((config.WINDOW_W - px(200), px(20), px(160), px(40)), "Refresh",
                                     style="plain", font_size=17)
        self.functions = []
        self.levels = self.functions
        self._filtered = self.functions
        self.cards = []
        self.delete_rects = []
        self.deleting = None
        self.busy = False
        self.status = ""
        self.page = 0
        self._load()

    # ---------------------------------------------------------------- events
    def handle_event(self, event):
        if self.back_button.handle_event(event) == "click":
            self.audio.play("click")
            from .function_lab import FunctionLabScene
            self.manager.switch(FunctionLabScene(self.manager))
            return
        if self.refresh_button.handle_event(event) == "click":
            self.audio.play("click")
            self._load()
            return
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and not self.busy:
            for (fn, rect), del_rect in zip(self.cards, self.delete_rects):
                if del_rect.collidepoint(event.pos):
                    self._delete(fn)
                    return
            for fn, rect in self.cards:
                if rect.collidepoint(event.pos):
                    self.audio.play("click")
                    self._import(fn)
                    return

    # ---------------------------------------------------------------- loading
    def _load(self):
        self.busy = True
        self.status = "Loading community functions..."
        self.cards = []
        self.delete_rects = []
        self.functions = []
        mod = _community_module()
        mod.fetch_community_functions(on_success=self._on_loaded, on_error=self._on_error)

    def _on_loaded(self, rows):
        self.functions = rows or []
        self.levels = self.functions
        self.status = f"Found {len(self.functions)} community function(s)."
        self.busy = False
        self._rebuild()

    def _on_error(self, exc):
        self.status = f"Failed to load community functions: {exc}"
        self.busy = False

    def _is_owner(self, fn):
        account = self.manager.account
        if account is None or not account.is_authenticated() or account.current_user is None:
            return False
        return str(fn.get("user_id")) == str(account.current_user.id)

    def _row_name(self, fn):
        return (fn.get("function_name") or fn.get("name") or fn.get("level_name")
                or "Untitled")

    def _delete(self, fn):
        if not self._is_owner(fn):
            self.status = "You can only delete your own uploads."
            return
        account = self.manager.account
        fid = str(fn.get("id"))
        self.deleting = fid
        self.status = "Deleting..."
        mod = _community_module()

        def on_ok(_result=None):
            self.deleting = None
            self.status = "Deleted."
            self._load()

        def on_err(exc):
            self.deleting = None
            self.status = f"Delete failed: {exc}"

        mod.delete_community_function(fid, account, on_success=on_ok, on_error=on_err)

    def _import(self, fn):
        name = clean_name(self._row_name(fn))
        fx = str(fn.get("fx", "") or "")
        fy = str(fn.get("fy", "") or "")
        library = list(getattr(self.session, "function_library", ()) or [])
        # Avoid duplicates.
        exists = False
        for item in library:
            item_fx = getattr(item, "fx", None)
            if item_fx is None and isinstance(item, dict):
                item_fx = item.get("fx")
            item_fy = getattr(item, "fy", None)
            if item_fy is None and isinstance(item, dict):
                item_fy = item.get("fy")
            item_name = getattr(item, "name", None)
            if item_name is None and isinstance(item, dict):
                item_name = item.get("name")
            if item_name == name and item_fx == fx and item_fy == fy:
                exists = True
                break
        if not exists:
            function = make_function(name, fx, fy)
            library.append(function)
            self.session.function_library = library
        self.status = f"Imported “{name}” into your Function Lab."
        # Also persist.
        try:
            from ..account.integration import save_progress
            save_progress(self.manager.account, self.session)
        except Exception:
            pass

    # Alias used by some callers.
    _open = _import
    _import_function = _import

    def _rebuild(self):
        # Keep the two names in sync: some callers use ``levels``.
        if getattr(self, "levels", None) is not None and self.levels is not self.functions:
            self.functions = self.levels
        if getattr(self, "functions", None) is None:
            self.functions = []
        self.levels = self.functions
        self._filtered = self.functions
        self.cards = []
        self.delete_rects = []
        x, y = px(60), px(100)
        for i, fn in enumerate(self.functions):
            rect = pygame.Rect(x + (i % 4) * px(260), y + (i // 4) * px(180), px(240), px(160))
            self.cards.append((fn, rect))
            self.delete_rects.append(pygame.Rect(rect.right - px(22), rect.y + px(6), px(16), px(16)))

    def draw(self, surface):
        surface.fill(config.BG)
        self.back_button.draw(surface)
        self.refresh_button.draw(surface)
        if self._dirty if hasattr(self, "_dirty") else False:
            pass
        draw_text(surface, "Community Functions", (config.WINDOW_W // 2, px(30)), 28,
                   config.TEXT, kind="bold", anchor="center")
        for (fn, rect), del_rect in zip(self.cards, self.delete_rects):
            pygame.draw.rect(surface, config.PANEL_BG, rect, border_radius=px(6))
            pygame.draw.rect(surface, config.PANEL_EDGE, rect, width=max(1, px(1)), border_radius=px(6))
            name = fit_text(self._row_name(fn), rect.w - px(20), 15, kind="bold")
            draw_text(surface, name, (rect.x + px(10), rect.y + px(8)), 15, config.TEXT, kind="bold")
            uploader = fit_text(str(fn.get("uploader_name") or fn.get("uploader_email") or "—"), rect.w - px(20), 12)
            draw_text(surface, uploader, (rect.x + px(10), rect.y + px(28)), 12, config.TEXT_DIM)
            fx = fit_text(str(fn.get("fx", "")), rect.w - px(20), 12, kind="mono")
            fy = fit_text(str(fn.get("fy", "")), rect.w - px(20), 12, kind="mono")
            draw_text(surface, f"Fx: {fx}", (rect.x + px(10), rect.y + px(52)), 12, config.TEXT_DIM, kind="mono")
            draw_text(surface, f"Fy: {fy}", (rect.x + px(10), rect.y + px(70)), 12, config.TEXT_DIM, kind="mono")
            if del_rect is not None and self._is_owner(fn):
                hover = del_rect.collidepoint(pygame.mouse.get_pos())
                bg = config.DANGER if hover else (140, 60, 70)
                pygame.draw.rect(surface, bg, del_rect, border_radius=px(3))
                draw_text(surface, "×", del_rect.center, 16, (255, 255, 255), kind="bold", anchor="center")
        if self.busy:
            draw_text(surface, self.status or "Loading...", (config.WINDOW_W // 2, config.WINDOW_H - px(60)),
                       15, config.WARNING, anchor="center")
        elif self.status:
            draw_text(surface, self.status, (config.WINDOW_W // 2, config.WINDOW_H - px(60)),
                       15, config.SUCCESS, anchor="center")


# Aliases
CommunityFunctionScene = CommunityFunctionsScene
CommunityFunctions = CommunityFunctionsScene
PublicFunctionsScene = CommunityFunctionsScene
CommunityFunctionBrowserScene = CommunityFunctionsScene
