"""Shared base for the Community browser scenes (Levels and Functions).

Everything the community tabs have in common lives here:

* the top chrome (title, the **Levels / Functions** tab bar, the refresh and
  back buttons);
* the search bar (name, uploader), the sort bar and the filter row;
* the card grid, pagination (buttons and mouse wheel) and the page counter;
* the loading, empty and error states;
* the per-user state that survives a tab switch (search, sort, page) — it is
  kept on the session, never in the profile.

Each content type subclasses this and provides:

* ``kind`` / ``content_label`` — which tab it is;
* ``_build_extra_widgets`` / ``_draw_extra_filters`` / ``_extra_state`` —
  the content-specific controls (the pickup filter for levels, the tag
  filter for functions);
* ``_fetch_rows`` / ``_on_loaded`` — where the rows come from;
* ``_info_for_row`` / ``_filter_infos`` — the search / sort rules;
* ``_draw_card`` — the card contents;
* ``_primary_action`` — what clicking a card does.

The result: a third content type can be added by subclassing this file
without re-implementing the community experience.
"""

from __future__ import annotations

from dataclasses import replace

import pygame

from .. import config
from ..config import px
from ..level_pages import can_next, can_prev, clamp_page, levels_on_page, page_count, wheel_step
from ..ui import Button, TextInput, draw_text, fit_text
from .base import Scene

# Toolbar layout (logical pixels).
_NAME_CAPTION_X = 36
_NAME_INPUT_X = 74
_NAME_INPUT_W = 176
_UPLOADER_CAPTION_X = 258
_UPLOADER_INPUT_X = 282
_UPLOADER_INPUT_W = 150
_SORT_BUTTON_X = 442
_SORT_BUTTON_W = 186
_DIR_BUTTON_X = 636
_DIR_BUTTON_W = 34
_EXTRA_X = 678
_EXTRA_W = 168
_MIN_INPUT_X = 86
_MIN_INPUT_W = 92
_MIN_INPUT_GAP = 8
_RESET_BUTTON_X = 854
_RESET_BUTTON_W = 84
_FILTER_SUMMARY_X = 430

_TITLE_Y = 10
_TABS_Y = 42
_TOOLBAR_Y = 80
_FILTER_Y = 116
_CARDS_Y = 150
_CARD_W = 240
_CARD_H = 152
_CARD_GAP_X = 20
_CARD_GAP_Y = 14
_CARDS_X = 60
_COLUMNS = 4

_TAB_H = 32
_TAB_W = 170
_TAB_GAP = 24


class CommunityBrowserScene(Scene):
    """The shared community browser; see the module docstring."""

    music = "menu"

    kind = ""                   # "levels" | "functions"
    content_label = "content"   # "levels" | "functions" (used in messages)
    back_label = "Back"

    def __init__(self, manager, back_to=None):
        super().__init__(manager)
        self.back_to = back_to
        self.back_button = Button((px(40), config.WINDOW_H - px(86), px(180), px(46)),
                                  self.back_label, style="plain", font_size=17)
        self.refresh_button = Button((config.WINDOW_W - px(200), px(20), px(160), px(40)),
                                     "Refresh", style="plain", font_size=17)
        self.tab_levels = Button(self._tab_rect(0), "Levels", style="plain", font_size=16)
        self.tab_functions = Button(self._tab_rect(1), "Functions", style="plain", font_size=16)
        self.cards = []
        self.delete_rects = []           # parallel to self.cards
        self.manage_rects = []           # edit button per card (owned only)
        self.favorite_rects = []         # favorite button per card (functions)
        self.deleting = None
        self.busy = False
        self.status = ""
        self.levels = []

        # --- search / sort / filter -------------------------------------
        self.sort_key = self._default_sort_key()
        self.descending = self._default_direction(self.sort_key)
        self.name_input = TextInput(
            (px(_NAME_INPUT_X), px(_TOOLBAR_Y), px(_NAME_INPUT_W), px(30)),
            f"{self.content_label[:-1]} name", font_size=14, on_change=self._on_filter_changed)
        self.uploader_input = TextInput(
            (px(_UPLOADER_INPUT_X), px(_TOOLBAR_Y), px(_UPLOADER_INPUT_W), px(30)),
            "uploader", font_size=14, on_change=self._on_filter_changed)
        self._build_extra_widgets()
        self.sort_button = Button((px(_SORT_BUTTON_X), px(_TOOLBAR_Y), px(_SORT_BUTTON_W), px(30)),
                                  "Sort", style="plain", font_size=14)
        self.sort_dir_button = Button((px(_DIR_BUTTON_X), px(_TOOLBAR_Y), px(_DIR_BUTTON_W), px(30)),
                                      "↓", style="plain", font_size=15)
        self.reset_button = Button((px(_RESET_BUTTON_X), px(_TOOLBAR_Y), px(_RESET_BUTTON_W), px(30)),
                                   "Reset", style="plain", font_size=14)
        # Paging: only the cards that fit on the screen are drawn, the rest
        # is reached with these buttons or with the mouse wheel.
        self.prev_page_button = Button((config.WINDOW_W - px(212), config.WINDOW_H - px(86), px(96), px(46)),
                                       "Prev", style="plain", font_size=16)
        self.next_page_button = Button((config.WINDOW_W - px(106), config.WINDOW_H - px(86), px(96), px(46)),
                                       "Next", style="plain", font_size=16)

        self._info_cache = {}        # row id -> info (cleared on refresh)
        self._preview_cache = {}     # row id -> preview payload (or None)
        self._filtered = []          # the entries the current search shows
        self._page_entries = []      # the ones on the page that is shown
        self._dirty = True           # the card list has to be rebuilt
        self.page = 0                # the page of the search result that is shown
        self._last_wheel = None      # time of the last wheel event (one gesture, one page)
        self._restore_state()
        self._load()

    # ------------------------------------------------------------------ tabs

    @staticmethod
    def _tab_rect(index: int) -> pygame.Rect:
        total = 2 * _TAB_W + _TAB_GAP
        x = (config.WINDOW_W - px(total)) // 2 + index * px(_TAB_W + _TAB_GAP)
        return pygame.Rect(x, px(_TABS_Y), px(_TAB_W), px(_TAB_H))

    def _tab_button(self, kind: str) -> Button:
        return self.tab_levels if kind == "levels" else self.tab_functions

    def _switch_category(self, kind: str) -> None:
        """Jump to the other tab; both tabs are the same Community page."""
        if kind == self.kind:
            return
        self._store_state()
        from .community_levels import CommunityLevelsScene
        from .community_functions import CommunityFunctionsScene
        cls = CommunityLevelsScene if kind == "levels" else CommunityFunctionsScene
        self.audio.play("click")
        self.manager.switch(cls(self.manager, back_to=self.back_to))

    # ------------------------------------------------------ session state

    def _state_store(self) -> dict:
        store = getattr(self.session, "community_state", None)
        if store is None:
            store = {}
            self.session.community_state = store
        return store

    def _extra_state(self) -> dict:
        """Content-specific scalars to survive a tab switch (hook)."""
        return {}

    def _restore_extra_state(self, state: dict) -> None:
        """Apply the content-specific scalars after construction (hook)."""

    def _snapshot_state(self) -> dict:
        state = {
            "name_query": self.name_input.text,
            "uploader_query": self.uploader_input.text,
            "sort_key": self.sort_key,
            "descending": self.descending,
            "page": self.page,
        }
        state.update(self._extra_state())
        return state

    def _restore_state(self) -> None:
        state = (self._state_store().get(self.kind) or {}) if self.session is not None else {}
        if not state:
            return
        try:
            self.name_input.set_text(state.get("name_query", ""))
            self.uploader_input.set_text(state.get("uploader_query", ""))
            self.sort_key = state.get("sort_key", self.sort_key)
            self.descending = bool(state.get("descending", self.descending))
            self.page = max(0, int(state.get("page", 0)))
            self._restore_extra_state(state)
        except Exception:  # noqa: BLE001 - a corrupt saved state never breaks the page
            pass

    def _store_state(self) -> None:
        if self.session is None:
            return
        self._state_store()[self.kind] = self._snapshot_state()

    # ------------------------------------------------------------------ events

    def handle_event(self, event):
        # The tab bar comes first: switching categories never leaves the
        # community page.
        if self.tab_levels.handle_event(event) == "click":
            self._switch_category("levels")
            return
        if self.tab_functions.handle_event(event) == "click":
            self._switch_category("functions")
            return
        # The toolbar buttons come first: clicking one keeps the focus in the
        # search box, so the player can keep typing right afterwards.
        if self.sort_button.handle_event(event) == "click":
            self.audio.play("click")
            self._cycle_sort()
            return
        if self.sort_dir_button.handle_event(event) == "click":
            self.audio.play("click")
            self.descending = not self.descending
            self._on_filter_changed()
            return
        if self._handle_extra_event(event):
            return
        if self.reset_button.handle_event(event) == "click":
            self.audio.play("click")
            self._reset_filters()
            return
        if self.prev_page_button.handle_event(event) == "click":
            self.audio.play("click")
            self._change_page(-1)
            return
        if self.next_page_button.handle_event(event) == "click":
            self.audio.play("click")
            self._change_page(1)
            return
        if self.back_button.handle_event(event) == "click":
            self.audio.play("click")
            self._go_back()
            return
        if self.refresh_button.handle_event(event) == "click":
            self.audio.play("click")
            self._load()
            return
        # The text fields own the keyboard while one of them is focused.
        if self._handle_input_event(event):
            return
        if event.type == pygame.MOUSEWHEEL:
            self._handle_wheel(event)
            return
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and not self.busy:
            # Delete / manage own uploads first (small buttons in the
            # top-right corner of a card).
            for index, (row, rect) in enumerate(self.cards):
                del_rect = self.delete_rects[index] if index < len(self.delete_rects) else None
                if del_rect is not None and del_rect.collidepoint(event.pos):
                    self._delete(row)
                    return
                edit_rect = self.manage_rects[index] if hasattr(self, "manage_rects") and index < len(self.manage_rects) else None
                if edit_rect is not None and edit_rect.collidepoint(event.pos):
                    self._edit(row)
                    return
                fav_rect = self.favorite_rects[index] if hasattr(self, "favorite_rects") and index < len(self.favorite_rects) else None
                if fav_rect is not None and fav_rect.collidepoint(event.pos):
                    self._toggle_favorite(row)
                    return
            # Otherwise open the content.
            for row, rect in self.cards:
                if rect.collidepoint(event.pos):
                    self.audio.play("click")
                    self._primary_action(row)
                    return

    def _default_back_target(self):
        """Hook: the scene class Back leads to (resolved lazily so tests can
        patch the module attribute)."""
        from .levels import LevelSelectScene

        return LevelSelectScene

    def _go_back(self):
        target = self.back_to or self._default_back_target()
        self.manager.switch(target(self.manager))

    def _handle_input_event(self, event) -> bool:
        """Let the text fields handle the event; True when the text changed."""
        changed = False
        for widget in self._input_widgets():
            if widget.handle_event(event):
                changed = True
        if changed:
            self._on_filter_changed()
        return changed

    def _input_widgets(self):
        return (self.name_input, self.uploader_input, *self._extra_inputs())

    def _extra_inputs(self):
        """Content-specific text fields (hook)."""
        return ()

    def _handle_extra_event(self, event) -> bool:
        """Content-specific buttons (hook): True when consumed."""
        return False

    # ------------------------------------------------------------------ paging

    def page_count(self) -> int:
        """How many pages the current search result has."""
        return page_count(len(self._filtered), self._per_page)

    @property
    def _per_page(self) -> int:
        """How many cards fit on one page."""
        return self._visible_count()

    def _change_page(self, step: int) -> None:
        """One page back (-1) or on (+1); nothing toward a disabled side."""
        pages = self.page_count()
        allowed = can_prev(self.page) if step < 0 else can_next(self.page, pages)
        if not allowed:
            return
        self.page += -1 if step < 0 else 1
        self._store_state()
        self._dirty = True

    def _handle_wheel(self, event) -> None:
        """The mouse wheel turns the page (one gesture turns one page)."""
        now = pygame.time.get_ticks() / 1000.0
        step, self._last_wheel = wheel_step(getattr(event, "y", 0), now, self._last_wheel)
        if step:
            self._change_page(step)

    # ----------------------------------------------------------------- loading

    def _loading_text(self) -> str:
        return f"Loading community {self.content_label}..."

    def _found_text(self, count: int) -> str:
        return f"Found {count} community {self.content_label[:-1] if self.content_label.endswith('s') else self.content_label}(s)."

    def _empty_text(self) -> str:
        return f"No community {self.content_label} yet — be the first to share one!"

    def _load(self):
        self.busy = True
        self.status = self._loading_text()
        self.cards = []
        self.delete_rects = []
        self.levels = []
        self._filtered = []
        self._info_cache.clear()
        self._preview_cache.clear()
        self._dirty = True
        self._fetch_rows(on_success=self._on_loaded, on_error=self._on_error)

    def _fetch_rows(self, on_success, on_error):
        """Hook: fetch the public rows (hook)."""
        raise NotImplementedError

    def _on_loaded(self, rows):
        self.levels = rows or []
        self.status = self._found_text(len(self.levels))
        self.busy = False
        self._dirty = True

    def _on_error(self, exc):
        self.status = f"Failed to load community {self.content_label}: {exc}"
        self.busy = False

    def _is_owner(self, row) -> bool:
        account = self.manager.account
        if account is None or not account.is_authenticated() or account.current_user is None:
            return False
        if not isinstance(row, dict):
            return False
        return str(row.get("user_id")) == str(account.current_user.id)

    def _delete(self, row):
        if not self._is_owner(row):
            self.status = "You can only delete your own uploads."
            return
        account = self.manager.account
        row_id = str(row.get("id"))
        self.deleting = row_id
        self.status = "Deleting..."

        def on_ok(_result=None):
            self.deleting = None
            self.status = "Deleted."
            self._store_state()
            self._load()

        def on_err(exc):
            self.deleting = None
            self.status = f"Delete failed: {exc}"

        self._delete_row(row_id, account, on_success=on_ok, on_error=on_err)

    def _delete_row(self, row_id, account, on_success, on_error):
        """Hook: delete the row in the content's table (hook)."""
        raise NotImplementedError

    def _edit(self, row):
        """Hook: edit one of the user's own rows (hook)."""
        self.status = "Editing is not available here."

    def _toggle_favorite(self, row):
        """Hook: favorite/unfavorite one row (hook; functions only)."""

    # ---------------------------------------------------------------- filtering

    def _on_filter_changed(self, *_args):
        """A search box, a filter or a sort button changed: rebuild the list."""
        self._dirty = True
        # New results are a new list: showing the old page number could land
        # in the middle (or at the end) of them.
        self.page = 0
        self._store_state()

    def _cycle_sort(self):
        """Next sort order (the direction follows the new order)."""
        try:
            index = self._sort_keys().index(self.sort_key)
        except ValueError:
            index = 0
        self.sort_key = self._sort_keys()[(index + 1) % len(self._sort_keys())]
        self.descending = self._default_direction(self.sort_key)
        self._on_filter_changed()

    def _reset_filters(self):
        """Clear every search box and go back to the default order."""
        for widget in self._input_widgets():
            widget.clear()
        self._reset_extra_filters()
        self.sort_key = self._default_sort_key()
        self.descending = self._default_direction(self.sort_key)
        self._on_filter_changed()

    def _reset_extra_filters(self) -> None:
        """Hook: clear the content-specific inputs."""

    def _min_count(self, widget) -> int:
        try:
            return max(0, int(widget.text or 0))
        except (TypeError, ValueError):
            return 0

    def _sort_keys(self):
        return self._sort_table().keys

    def _sort_table(self):
        raise NotImplementedError

    def _default_sort_key(self):
        return self._sort_keys()[0]

    @staticmethod
    def _default_direction(sort_key: str) -> bool:
        return True

    def _sort_label(self):
        return self._sort_table().label(self.sort_key, self.descending)

    def _entries(self):
        """``(row, info)`` for every row, parsing each row only once."""
        entries = []
        for index, row in enumerate(self.levels):
            if not isinstance(row, dict):
                continue
            key = str(row.get("id") or "")
            if not key:
                # A row without an id is broken data; it still gets a key of
                # its own so it can be listed and opened.
                key = f"row-{index}"
            info = self._info_cache.get(key)
            if info is None:
                info = replace(self._info_for_row(row), row_id=key)
                self._info_cache[key] = info
            entries.append((row, info))
        return entries

    def _info_for_row(self, row):
        raise NotImplementedError

    def _filtered_entries(self):
        """The ``(row, info)`` pairs the current search shows."""
        entries = self._entries()
        rows_by_id = {info.row_id: row for row, info in entries}
        matched = self._filter_infos([info for _row, info in entries])
        return [(rows_by_id.get(info.row_id), info) for info in matched]

    def _filter_infos(self, infos):
        raise NotImplementedError

    # ------------------------------------------------------------------- cards

    def _rebuild(self):
        """(Re)build the visible cards from the current search result."""
        self._filtered = self._filtered_entries()
        self.page = clamp_page(self.page, self.page_count())
        visible = levels_on_page(self._filtered, self.page, self._per_page)
        self.cards = []
        self.delete_rects = []
        self.manage_rects = []
        self.favorite_rects = []
        page_entries = []
        x, y = px(_CARDS_X), px(_CARDS_Y)
        step_x = px(_CARD_W + _CARD_GAP_X)
        step_y = px(_CARD_H + _CARD_GAP_Y)
        for index, (row, _info) in enumerate(visible):
            if row is None:
                continue
            rect = pygame.Rect(x + (index % _COLUMNS) * step_x, y + (index // _COLUMNS) * step_y,
                               px(_CARD_W), px(_CARD_H))
            self.cards.append((row, rect))
            self.delete_rects.append(self._delete_rect(rect))
            self.manage_rects.append(self._manage_rect(rect))
            self.favorite_rects.append(self._favorite_rect(rect, row))
            page_entries.append((row, _info))
        self._page_entries = page_entries
        self.prev_page_button.enabled = can_prev(self.page)
        self.next_page_button.enabled = can_next(self.page, self.page_count())

    @staticmethod
    def _card_button_rect(rect: pygame.Rect, offset_from_right: int) -> pygame.Rect:
        return pygame.Rect(rect.right - px(offset_from_right), rect.y + px(6), px(20), px(18))

    def _delete_rect(self, rect: pygame.Rect) -> pygame.Rect:
        return self._card_button_rect(rect, 26)

    def _manage_rect(self, rect: pygame.Rect):
        return None

    def _favorite_rect(self, rect: pygame.Rect, row=None):
        return None

    def _visible_count(self) -> int:
        """How many cards fit on the screen (the rest is not drawn)."""
        space = config.WINDOW_H - px(_CARDS_Y) - px(24)
        fit = int((space + px(_CARD_GAP_Y)) // (px(_CARD_H) + px(_CARD_GAP_Y)))
        return max(1, fit) * _COLUMNS

    def _primary_action(self, row):
        """Hook: what clicking a card does (hook)."""

    # ------------------------------------------------------------------------

    def _build_extra_widgets(self) -> None:
        """Hook: create the content-specific widgets (the pickup button for
        levels, the tag field for functions)."""

    def _extra_toolbar_x(self) -> int:
        return _EXTRA_X

    def _draw_toolbar(self, surface):
        """The search bar: two searches, the sort order and the filters."""
        label_color = config.TEXT_DIM
        draw_text(surface, "Name", (px(_NAME_CAPTION_X), px(_TOOLBAR_Y + 15)), 13,
                  label_color, anchor="midleft")
        self.name_input.draw(surface)
        draw_text(surface, "By", (px(_UPLOADER_CAPTION_X), px(_TOOLBAR_Y + 15)), 13,
                  label_color, anchor="midleft")
        self.uploader_input.draw(surface)
        self.sort_button.label = f"Sort: {self._sort_table().labels.get(self.sort_key, self.sort_key)}"
        self.sort_button.draw(surface)
        self.sort_dir_button.label = "↓" if self.descending else "↑"
        self.sort_dir_button.draw(surface)
        self.reset_button.draw(surface)
        self._draw_extra_toolbar(surface)

        draw_text(surface, self._filter_caption(), (px(_NAME_CAPTION_X), px(_FILTER_Y + 14)), 13,
                  label_color, anchor="midleft")
        self._draw_extra_filters(surface)

        total = len(self.levels)
        shown = len(self._filtered)
        pages = self.page_count()
        if total:
            summary = f"{shown} of {total} {self.content_label} · page {self.page + 1}/{pages}"
        else:
            summary = f"no {self.content_label}"
        if self.name_input.text or self.uploader_input.text:
            summary += " · closest match first"
        draw_text(surface, summary, (px(_FILTER_SUMMARY_X), px(_FILTER_Y + 14)), 13,
                  config.TEXT, anchor="midleft")

    def _filter_caption(self) -> str:
        return "At least"

    def _draw_extra_toolbar(self, surface) -> None:
        """Hook: draw the extra control on the toolbar row."""

    def _draw_extra_filters(self, surface) -> None:
        """Hook: draw the extra control(s) on the filter row."""

    def _extra_summary(self) -> str:
        return ""

    # ------------------------------------------------------------------------

    def _draw_tabs(self, surface):
        for kind in ("levels", "functions"):
            button = self._tab_button(kind)
            button.style = "primary" if kind == self.kind else "plain"
            button.draw(surface)

    def _draw_empty_state(self, surface):
        if self.busy or self.levels:
            return
        if self.name_input.text or self.uploader_input.text:
            text = "Nothing matches — try a different search."
        else:
            text = self._empty_text()
        draw_text(surface, text, (config.WINDOW_W // 2, px(_CARDS_Y + 150)), 16,
                  config.TEXT_DIM, anchor="center")

    def _draw_card(self, surface, row, info, rect, del_rect=None, manage_rect=None, fav_rect=None):
        """Hook: draw one card's contents."""
        raise NotImplementedError

    def _draw_card_frame(self, surface, rect):
        pygame.draw.rect(surface, config.PANEL_BG, rect, border_radius=px(6))
        pygame.draw.rect(surface, config.PANEL_EDGE, rect, width=max(1, px(1)), border_radius=px(6))

    def _draw_owner_buttons(self, surface, row, del_rect, manage_rect):
        """The delete / edit buttons shared by both kinds."""
        if manage_rect is not None and self._is_owner(row):
            hover = manage_rect.collidepoint(pygame.mouse.get_pos())
            bg = config.BUTTON_PRIMARY_HOVER if hover else config.BUTTON_PRIMARY
            pygame.draw.rect(surface, bg, manage_rect, border_radius=px(3))
            from ..ui_icons import icon_surface
            icon = icon_surface("pencil", min(manage_rect.w, manage_rect.h) - px(2), (255, 255, 255))
            surface.blit(icon, icon.get_rect(center=manage_rect.center))
        if del_rect is not None and self._is_owner(row):
            hover = del_rect.collidepoint(pygame.mouse.get_pos())
            bg = config.DANGER if hover else (140, 60, 70)
            pygame.draw.rect(surface, bg, del_rect, border_radius=px(3))
            draw_text(surface, "×", del_rect.center, 16, (255, 255, 255),
                      kind="bold", anchor="center")

    def draw(self, surface):
        surface.fill(config.BG)
        self.back_button.draw(surface)
        self.refresh_button.draw(surface)
        # Rebuild before the paging buttons are drawn: their enabled state
        # belongs to the result that is about to be shown.
        if self._dirty:
            self._rebuild()
            self._dirty = False
        self.prev_page_button.draw(surface)
        self.next_page_button.draw(surface)
        draw_text(surface, "Community", (px(36), px(22)), 26, config.TEXT,
                  kind="bold", anchor="midleft")
        draw_text(surface, self._tab_caption(), (px(36), px(22 + 26)), 13,
                  config.TEXT_FAINT, anchor="midleft")
        self._draw_tabs(surface)
        self._draw_toolbar(surface)
        self._draw_empty_state(surface)
        for index, (row, rect) in enumerate(self.cards):
            info = self._page_entries[index][1] if index < len(self._page_entries) else None
            if info is None:
                continue
            del_rect = self.delete_rects[index] if index < len(self.delete_rects) else None
            manage_rect = self.manage_rects[index] if index < len(self.manage_rects) else None
            fav_rect = self.favorite_rects[index] if index < len(self.favorite_rects) else None
            self._draw_card(surface, row, info, rect, del_rect, manage_rect, fav_rect)
        if self.busy:
            draw_text(surface, self.status or "Loading...", (config.WINDOW_W // 2, config.WINDOW_H - px(60)),
                      15, config.WARNING, anchor="center")
        elif self.status:
            draw_text(surface, self.status, (config.WINDOW_W // 2, config.WINDOW_H - px(60)),
                      15, config.SUCCESS, anchor="center")

    def _tab_caption(self) -> str:
        return "one place, every player's creations"
