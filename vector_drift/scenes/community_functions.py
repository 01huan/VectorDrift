"""Community functions: the Functions tab of the shared Community page.

Browse the force functions other players published: search by name or
uploader, filter by tags, sort by newest / most used / most successful /
favorites / highest rated, and inspect a function (vector field, ``Fx`` /
``Fy`` formulas and a probe trajectory) before importing it into your own
Function Lab.

Reading is public; publishing, updating, deleting, favoriting and rating
require an account (row level security enforces ownership on the server as
well).  The shared browser chrome lives in
:mod:`vector_drift.scenes.community_browser`.
"""

from __future__ import annotations

import pygame

from .. import config
from ..community_function_browse import (
    MAX_TAG_LEN,
    SORT_DEFAULT_DESCENDING,
    SORT_NEWEST,
    SORT_TABLE,
    CommunityFunctionInfo,
    filter_functions,
    function_info,
    normalize_tags,
    parse_tags,
    tags_to_text,
)
from ..config import px
from ..function_library import (
    MAX_FUNCTIONS,
    make_function,
    unique_name,
)
from ..function_preview import (
    draw_preview,
    make_preview,
    parse_formulas,
)
from ..ui import Button, TextInput, draw_text, fit_text, wrap_text
from ..account import community
from .community_browser import (
    _EXTRA_W,
    _EXTRA_X,
    _FILTER_Y,
    _TOOLBAR_Y,
    _MIN_INPUT_X,
    CommunityBrowserScene,
)

_MIN_INPUT_W = 92

# The detail overlay (inspect a function before importing it).
_OVERLAY_W = 940
_OVERLAY_H = 560
_STAR_W = 30

# The import overlay (rename before importing into the lab).
_IMPORT_W = 540
_IMPORT_H = 240

_SHADE_CACHE = {}


def _overlay_panel(width, height) -> pygame.Rect:
    panel = pygame.Rect(0, 0, px(width), px(height))
    panel.center = (config.WINDOW_W // 2, config.WINDOW_H // 2)
    return panel


class CommunityFunctionsScene(CommunityBrowserScene):
    kind = "functions"
    content_label = "functions"
    back_label = "Back"

    def __init__(self, manager, back_to=None):
        # Overlay state: set before the parent builds (and loads) the page.
        self._detail_row = None        # the row being inspected (live dict)
        self._detail_info = None       # its parsed info (refreshed on demand)
        self._edit_mode = False
        self._edit_fields = {}
        self._overlay_message = ""
        self._overlay_message_color = config.TEXT
        self._import_mode = False
        self._import_input = None
        self._overlay_buttons = {}
        self._star_rects = []
        self._my_favorites = set()
        self._my_ratings = {}
        self._previews = {}            # (fx, fy, w, h) -> preview payload
        super().__init__(manager, back_to=back_to)

    def _default_back_target(self):
        from .function_lab import FunctionLabScene

        return FunctionLabScene

    # ------------------------------------------------------------------ hooks

    def _default_sort_key(self):
        return SORT_NEWEST

    @staticmethod
    def _default_direction(sort_key: str) -> bool:
        return SORT_DEFAULT_DESCENDING.get(sort_key, False)

    def _sort_table(self):
        return SORT_TABLE

    def _build_extra_widgets(self):
        self.tag_input = TextInput(
            (px(_EXTRA_X), px(_TOOLBAR_Y), px(_EXTRA_W), px(30)),
            "tag", font_size=14, max_length=MAX_TAG_LEN, on_change=self._on_filter_changed)
        self.min_uses_input = TextInput(
            (px(_MIN_INPUT_X), px(_FILTER_Y), px(_MIN_INPUT_W), px(28)),
            "uses", font_size=13, numeric=True, on_change=self._on_filter_changed)

    def _extra_inputs(self):
        return (self.tag_input, self.min_uses_input)

    def _extra_state(self):
        return {"tag_query": self.tag_input.text, "min_uses": self.min_uses_input.text}

    def _restore_extra_state(self, state):
        self.tag_input.set_text(state.get("tag_query", ""))
        self.min_uses_input.set_text(state.get("min_uses", ""))

    def _reset_extra_filters(self):
        pass  # the extra inputs are cleared by the base reset already

    def _filter_caption(self):
        return "At least"

    def _draw_extra_filters(self, surface):
        self.min_uses_input.draw(surface)

    # ---------------------------------------------------------------- data hooks

    def _fetch_rows(self, on_success, on_error):
        community.fetch_community_functions(on_success=on_success, on_error=on_error)

    def _delete_row(self, row_id, account, on_success, on_error):
        community.delete_community_function(row_id, account, on_success=on_success, on_error=on_error)

    def _info_for_row(self, row):
        return function_info(row)

    def _filter_infos(self, infos):
        return filter_functions(
            infos,
            name_query=self.name_input.text,
            uploader_query=self.uploader_input.text,
            tag_query=self.tag_input.text,
            min_uses=self._min_count(self.min_uses_input),
            sort_key=self.sort_key,
            descending=self.descending,
        )

    def _favorite_rect(self, rect, row=None):
        owner = self._is_owner(row) if row is not None else False
        return self._card_button_rect(rect, 78 if owner else 26)

    def _manage_rect(self, rect):
        return self._card_button_rect(rect, 52)

    def _primary_action(self, row):
        """Clicking a card opens the detail (inspect) overlay."""
        self._open_detail(row)

    # ------------------------------------------------------------ engagement

    def _fetch_engagement(self):
        account = self.manager.account

        def on_ok(payload):
            if isinstance(payload, dict):
                self._my_favorites = set(payload.get("favorites") or [])
                ratings = payload.get("ratings") or {}
                self._my_ratings = {str(k): int(v) for k, v in ratings.items()
                                    if str(k) and isinstance(v, int)}
                self._dirty = True

        try:
            community.fetch_function_engagement(account, on_success=on_ok, on_error=lambda exc: None)
        except Exception:  # noqa: BLE001 - a missing engagement service never breaks browsing
            pass

    def _on_loaded(self, rows):
        super()._on_loaded(rows)
        self._fetch_engagement()

    def _toggle_favorite(self, row):
        account = self.manager.account
        row_id = str(row.get("id"))
        if not row_id:
            return
        if (
            account is None
            or not account.is_authenticated()
            or account.current_user is None
        ):
            self.status = "Please log in to favorite functions."
            return
        wanted = row_id not in self._my_favorites

        def on_ok(_result=None):
            if wanted:
                self._my_favorites.add(row_id)
                row["favorite_count"] = int(row.get("favorite_count") or 0) + 1
            else:
                self._my_favorites.discard(row_id)
                row["favorite_count"] = max(0, int(row.get("favorite_count") or 0) - 1)
            self._info_cache.pop(row_id, None)
            self._previews.clear()
            self._dirty = True
            if self._detail_row is row:
                self._build_detail_buttons()

        def on_err(exc):
            self.status = f"Could not update your favorite: {exc}"

        community.set_function_favorite(row_id, wanted, account, on_success=on_ok, on_error=on_err)

    def _rate(self, row, stars: int):
        account = self.manager.account
        row_id = str(row.get("id"))
        if not row_id:
            return
        if (
            account is None
            or not account.is_authenticated()
            or account.current_user is None
        ):
            self.status = "Please log in to rate functions."
            return
        old = self._my_ratings.get(row_id)

        def on_ok(_result=None):
            self._my_ratings[row_id] = stars
            rating_count = int(row.get("rating_count") or 0)
            rating_total = int(row.get("rating_total") or 0)
            if old is None:
                rating_count += 1
                rating_total += stars
            else:
                rating_total = max(0, rating_total - old + stars)
            row["rating_count"] = rating_count
            row["rating_total"] = rating_total
            self._info_cache.pop(row_id, None)
            self._detail_info = None
            self._dirty = True

        def on_err(exc):
            self.status = f"Could not save your rating: {exc}"

        community.set_function_rating(row_id, stars, account, on_success=on_ok, on_error=on_err)

    # ------------------------------------------------------------------ cards

    def _edit(self, row):
        """Open the detail overlay with the edit form enabled."""
        if not self._is_owner(row):
            self.status = "You can only edit your own uploads."
            return
        self._open_detail(row, edit_mode=True)

    def _draw_field_preview(self, surface, row, rect):
        """Draw the vector field (and probe) of one row inside ``rect``."""
        pygame.draw.rect(surface, (26, 34, 60), rect, border_radius=px(3))
        pygame.draw.rect(surface, config.PANEL_EDGE, rect, width=max(1, px(1)), border_radius=px(3))
        fx = str(row.get("fx") or "")
        fy = str(row.get("fy") or "")
        key = (fx, fy, rect.w, rect.h)
        preview = self._previews.get(key)
        if preview is None:
            preview = make_preview(fx, fy, pygame.Rect(rect))
            self._previews[key] = preview
        if preview["field"] is None:
            draw_text(surface, "preview unavailable", rect.center, 11,
                      config.TEXT_FAINT, anchor="center")
            return
        clip_backup = surface.get_clip()
        surface.set_clip(rect)
        try:
            draw_preview(surface, preview, rect)
        finally:
            surface.set_clip(clip_backup)

    def _draw_card(self, surface, fn: dict, info: CommunityFunctionInfo, rect: pygame.Rect,
                   del_rect=None, manage_rect=None, fav_rect=None):
        """One function card: name, uploader, preview, stats, engagement."""
        self._draw_card_frame(surface, rect)
        row_id = str(fn.get("id"))
        owner = self._is_owner(fn)
        name_w = rect.w - px(150) if owner else rect.w - px(60)
        name = fit_text(info.name or "Untitled", max(60, name_w), 14, kind="bold")
        draw_text(surface, name, (rect.x + px(10), rect.y + px(7)), 14, config.TEXT, kind="bold")
        uploader = fit_text(info.uploader or "—", rect.w - px(20), 11)
        draw_text(surface, uploader, (rect.x + px(10), rect.y + px(25)), 11, config.TEXT_DIM)

        preview = pygame.Rect(rect.x + px(10), rect.y + px(42), rect.w - px(20), px(56))
        self._draw_field_preview(surface, fn, preview)

        caption = info.description or info.fx or ""
        draw_text(surface, fit_text(caption, rect.w - px(20), 10),
                  (rect.x + px(10), rect.y + px(101)), 10, config.TEXT_DIM)
        avg = info.average_rating
        usage = f"uses {info.usage_count} · users {info.unique_user_count}"
        draw_text(surface, fit_text(usage, rect.w - px(20) - px(64), 11),
                  (rect.x + px(10), rect.y + px(114)), 11, config.TEXT_DIM)
        rating_text = f"{avg:.1f} ({info.rating_count})" if info.rating_count else "—"
        from ..ui_icons import icon_surface
        star_icon = icon_surface("star", px(12),
                                 (255, 205, 80) if info.rating_count else config.TEXT_FAINT)
        text_w = int(get_text_width(rating_text, 11))
        surface.blit(star_icon, star_icon.get_rect(topleft=(rect.right - px(10) - text_w - px(14), rect.y + px(113))))
        draw_text(surface, rating_text, (rect.right - px(10), rect.y + px(114)), 11,
                  (255, 205, 80) if info.rating_count else config.TEXT_FAINT, anchor="topright")
        tags = ", ".join(info.tags) if info.tags else ""
        date = info.detail_date()
        left = fit_text(tags or "no tags", rect.w - px(20) - px(58), 10)
        draw_text(surface, left, (rect.x + px(10), rect.y + px(128)), 10,
                  config.TEXT_FAINT if tags else config.TEXT_DIM)
        right = f"♥ {info.favorite_count}" + (f" · {date}" if date else "")
        draw_text(surface, fit_text(right, px(96), 10),
                  (rect.right - px(10), rect.y + px(128)), 10, config.TEXT_FAINT, anchor="topright")

        # Engagement / management buttons.
        fav_hover = fav_rect is not None and fav_rect.collidepoint(pygame.mouse.get_pos())
        if fav_rect is not None:
            fav_on = row_id in self._my_favorites
            bg = (150, 60, 80) if fav_on else ((140, 60, 70) if not fav_hover else config.DANGER)
            if fav_on and fav_hover:
                bg = config.DANGER
            pygame.draw.rect(surface, bg, fav_rect, border_radius=px(3))
            draw_text(surface, "♥", fav_rect.center, 13, (255, 255, 255),
                      kind="bold", anchor="center")
        self._draw_owner_buttons(surface, fn, del_rect, manage_rect)

    # ------------------------------------------------------------------ events

    def handle_event(self, event):
        # An open overlay (inspect / edit / import) owns every event.
        if self._import_mode:
            self._handle_import_event(event)
            return
        if self._detail_row is not None:
            self._handle_detail_event(event)
            return
        return super().handle_event(event)

    # --------------------------------------------------------- detail overlay

    def _open_detail(self, row, edit_mode: bool = False):
        if not isinstance(row, dict):
            return
        self._detail_row = row
        self._detail_info = None
        self._edit_mode = bool(edit_mode and self._is_owner(row))
        self._overlay_message = ""
        if self._edit_mode:
            self._build_edit_fields(row)
        self._build_detail_buttons()

    def _close_detail(self):
        self._detail_row = None
        self._detail_info = None
        self._edit_mode = False
        self._edit_fields = {}
        self._overlay_buttons = {}
        self._overlay_message = ""

    def _detail_info_obj(self):
        if self._detail_info is None and self._detail_row is not None:
            self._detail_info = function_info(self._detail_row)
        return self._detail_info

    def _build_edit_fields(self, row):
        panel = _overlay_panel(_OVERLAY_W, _OVERLAY_H)
        x = panel.x + px(24)
        w = panel.w - px(48)
        y = panel.y + px(84)
        self._edit_fields = {}
        for key, max_length, placeholder in (
            ("name", 40, "name"),
            ("description", 280, "description"),
            ("tags", 10 * MAX_TAG_LEN, "tags (comma separated)"),
            ("fx", 400, "Fx"),
            ("fy", 400, "Fy"),
        ):
            field = TextInput((x, y + px(16), w, px(30)), placeholder,
                              font_size=13, max_length=max_length)
            self._edit_fields[key] = field
            y += px(66)
        self._edit_fields["name"].set_text(str(row.get("function_name") or ""))
        self._edit_fields["description"].set_text(str(row.get("description") or ""))
        self._edit_fields["tags"].set_text(tags_to_text(row.get("tags")))
        self._edit_fields["fx"].set_text(str(row.get("fx") or ""))
        self._edit_fields["fy"].set_text(str(row.get("fy") or ""))

    def _build_detail_buttons(self):
        panel = _overlay_panel(_OVERLAY_W, _OVERLAY_H)
        by = panel.bottom - px(56)
        row_id = str((self._detail_row or {}).get("id"))
        fav = row_id in self._my_favorites
        self._overlay_buttons = {
            "import": Button(pygame.Rect(panel.x + px(24), by, px(250), px(38)),
                             "Import to Function Lab", style="primary", font_size=15),
            "favorite": Button(pygame.Rect(panel.x + px(282), by, px(210), px(38)),
                               "♥ Favorited" if fav else "♥ Favorite", style="plain", font_size=15),
            "edit": Button(pygame.Rect(panel.x + px(500), by, px(130), px(38)),
                           "Edit", style="plain", font_size=15),
            "delete": Button(pygame.Rect(panel.x + px(638), by, px(120), px(38)),
                             "Delete", style="danger", font_size=15),
            "close": Button(pygame.Rect(panel.right - px(124), by, px(100), px(38)),
                            "Close", style="plain", font_size=15),
            "save": Button(pygame.Rect(panel.x + px(24), by, px(180), px(38)),
                           "Save changes", style="primary", font_size=15),
            "cancel": Button(pygame.Rect(panel.x + px(212), by, px(120), px(38)),
                             "Cancel", style="plain", font_size=15),
        }

    def _star_rects_layout(self, origin):
        rects = []
        for index in range(5):
            rects.append(pygame.Rect(origin[0] + index * px(_STAR_W), origin[1],
                                     px(_STAR_W - 4), px(_STAR_W - 4)))
        return rects

    def _handle_detail_event(self, event) -> bool:
        panel = _overlay_panel(_OVERLAY_W, _OVERLAY_H)
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.audio.play("click")
            self._close_detail()
            return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if not panel.collidepoint(event.pos):
                self._close_detail()
                return True
        row = self._detail_row
        if row is None:
            self._close_detail()
            return True
        owner = self._is_owner(row)

        if self._edit_mode:
            handled = False
            for field in self._edit_fields.values():
                if field.handle_event(event):
                    handled = True
            if handled:
                return True
            if self._overlay_buttons["save"].handle_event(event) == "click":
                self.audio.play("click")
                self._save_edit()
                return True
            if self._overlay_buttons["cancel"].handle_event(event) == "click":
                self.audio.play("click")
                self._edit_mode = False
                self._build_detail_buttons()
                return True
            return True   # swallow everything else while editing

        for star_index, rect in enumerate(self._star_rects):
            if (event.type == pygame.MOUSEBUTTONDOWN and event.button == 1
                    and rect.collidepoint(event.pos)):
                self._rate(row, star_index + 1)
                return True
        buttons = self._overlay_buttons
        if buttons["favorite"].handle_event(event) == "click":
            self.audio.play("click")
            self._toggle_favorite(row)
            return True
        if buttons["import"].handle_event(event) == "click":
            self.audio.play("click")
            self._open_import(row)
            return True
        if owner and buttons["edit"].handle_event(event) == "click":
            self.audio.play("click")
            self._edit_mode = True
            self._build_edit_fields(row)
            return True
        if owner and buttons["delete"].handle_event(event) == "click":
            self.audio.play("click")
            self._close_detail()
            self._delete(row)
            return True
        if buttons["close"].handle_event(event) == "click":
            self.audio.play("click")
            self._close_detail()
            return True
        for name, button in buttons.items():
            if name in ("edit", "delete"):
                continue   # disabled for non-owners: treated as absent
            button.handle_event(event)
        return True

    def _edit_error(self, text):
        self._overlay_message = text
        self._overlay_message_color = config.WARNING

    def _save_edit(self):
        row = self._detail_row
        if row is None:
            return
        account = self.manager.account
        name = self._edit_fields["name"].text.strip()
        description = self._edit_fields["description"].text
        tags_text = self._edit_fields["tags"].text
        fx = self._edit_fields["fx"].text
        fy = self._edit_fields["fy"].text
        if not name:
            self._edit_error("The function needs a name.")
            return
        _field, errors = parse_formulas(fx, fy)
        for error in errors:
            if error:
                message, _pos = error
                self._edit_error(f"Formula error: {message}")
                return
        tags = parse_tags(tags_text)

        def on_ok(_result=None):
            row["function_name"] = name
            row["description"] = " ".join(str(description).split())[:280]
            row["tags"] = list(tags)
            row["fx"] = fx
            row["fy"] = fy
            row_id = str(row.get("id"))
            self._info_cache.pop(row_id, None)
            self._previews.clear()
            self._detail_info = None
            self._edit_mode = False
            self._overlay_message = ""
            self.status = "Updated."
            self._dirty = True

        def on_err(exc):
            self._edit_error(f"Update failed: {exc}")

        community.update_community_function(
            str(row.get("id")), account,
            function_name=name, fx=fx, fy=fy, description=description, tags=tags,
            on_success=on_ok, on_error=on_err,
        )

    # --------------------------------------------------------- import overlay

    def _open_import(self, row):
        self._import_mode = True
        self._overlay_message = ""
        library = list(getattr(self.session, "function_library", ()) or [])
        prefill = unique_name(row.get("function_name") or "Untitled", library)
        if self._import_input is None:
            self._import_input = TextInput((0, 0, px(10), px(34)), "function name",
                                           font_size=15, max_length=40)
        panel = _overlay_panel(_IMPORT_W, _IMPORT_H)
        self._import_input.rect = pygame.Rect(panel.x + px(28), panel.y + px(106),
                                              panel.w - px(56), px(34))
        self._import_input.set_text(prefill)
        self._import_input.active = True
        self._import_buttons = {
            "import": Button(pygame.Rect(panel.x + px(28), panel.bottom - px(64), px(150), px(38)),
                             "Import", style="primary", font_size=16),
            "cancel": Button(pygame.Rect(panel.x + px(56 + 150), panel.bottom - px(64), px(110), px(38)),
                             "Cancel", style="plain", font_size=16),
        }

    def _close_import(self):
        self._import_mode = False
        self._overlay_message = ""

    def _handle_import_event(self, event) -> bool:
        panel = _overlay_panel(_IMPORT_W, _IMPORT_H)
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.audio.play("click")
            self._close_import()
            return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if not panel.collidepoint(event.pos):
                self._close_import()
                return True
        if self._import_input is not None and self._import_input.handle_event(event):
            return True
        if self._import_buttons["import"].handle_event(event) == "click":
            self.audio.play("click")
            self._confirm_import()
            return True
        if self._import_buttons["cancel"].handle_event(event) == "click":
            self.audio.play("click")
            self._close_import()
            return True
        return True

    def _confirm_import(self):
        row = self._detail_row
        if row is None:
            self._close_import()
            return
        name = self._import_input.text if self._import_input is not None else ""
        fx = str(row.get("fx") or "")
        fy = str(row.get("fy") or "")
        field, errors = parse_formulas(fx, fy)
        if field is None:
            for error in errors:
                if error:
                    message, _pos = error
                    self._overlay_message = f"Cannot import: {message}"
                    self._overlay_message_color = config.WARNING
                    return
            self._overlay_message = "Cannot import: the formulas are not valid."
            self._overlay_message_color = config.WARNING
            return
        library = list(getattr(self.session, "function_library", ()) or [])
        if len(library) >= MAX_FUNCTIONS:
            self._overlay_message = f"The library holds at most {MAX_FUNCTIONS} functions."
            self._overlay_message_color = config.WARNING
            return
        final_name = unique_name(name, library)
        function = make_function(
            final_name, fx, fy,
            description=row.get("description") or "",
            tags=row.get("tags") or (),
            source="community",
            community_id=str(row.get("id") or ""),
        )
        self.session.function_library = library + [function]
        try:
            from ..account.integration import save_progress
            save_progress(self.manager.account, self.session)
        except Exception:  # noqa: BLE001 - persistence must not block the import
            pass
        self.status = f"Imported “{function.name}” into your Function Lab."
        self._close_import()
        self._close_detail()

    # -------------------------------------------------------------------- draw

    def draw(self, surface):
        # The normal community page first…
        super().draw(surface)
        # …then the overlay, if one is open.
        if self._import_mode:
            self._draw_import_overlay(surface)
        elif self._detail_row is not None:
            self._draw_detail_overlay(surface)

    def _shade(self, surface):
        key = tuple(surface.get_size())
        shade = _SHADE_CACHE.get(key)
        if shade is None:
            shade = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
            shade.fill((5, 8, 18, 200))
            _SHADE_CACHE[key] = shade
        surface.blit(shade, (0, 0))

    def _draw_detail_overlay(self, surface):
        panel = _overlay_panel(_OVERLAY_W, _OVERLAY_H)
        row = self._detail_row
        info = self._detail_info_obj()
        owner = self._is_owner(row)
        self._shade(surface)
        pygame.draw.rect(surface, config.PANEL_BG, panel, border_radius=px(8))
        pygame.draw.rect(surface, config.PANEL_EDGE, panel, width=max(1, px(1)), border_radius=px(8))

        name = fit_text(info.name or "Untitled", panel.w - px(150), 20, kind="bold")
        draw_text(surface, name, (panel.x + px(24), panel.y + px(18)), 20, config.TEXT,
                  kind="bold")
        who = info.uploader or "—"
        date = info.detail_date()
        subtitle = f"uploaded by {who}"
        if date:
            subtitle += f" · {date}"
        if owner:
            subtitle += " · yours"
        draw_text(surface, fit_text(subtitle, panel.w - px(80), 12),
                  (panel.x + px(24), panel.y + px(46)), 12, config.TEXT_DIM)

        if not self._edit_mode:
            # --- left column: the field preview -------------------------------
            preview_rect = pygame.Rect(panel.x + px(24), panel.y + px(76), px(400), px(212))
            self._draw_field_preview(surface, row, preview_rect)
            caption = "vector field · probe trajectory (Fx, Fy)"
            draw_text(surface, caption, (preview_rect.centerx, preview_rect.bottom + px(10)), 11,
                      config.TEXT_FAINT, anchor="center")

        # --- right column --------------------------------------------------
        col_x = panel.x + px(448)
        col_w = panel.right - px(24) - col_x

        if self._edit_mode:
            labels = (("name", "NAME"), ("description", "DESCRIPTION"),
                      ("tags", "TAGS (comma separated)"), ("fx", "FX"), ("fy", "FY"))
            for key, label in labels:
                field = self._edit_fields[key]
                draw_text(surface, label, (field.rect.x, field.rect.y - px(2)), 10,
                          config.TEXT_FAINT, kind="bold", anchor="bottomleft")
                field.draw(surface)
            if self._overlay_message:
                draw_text(surface, fit_text(self._overlay_message, panel.w - px(48), 12),
                          (panel.x + px(24), panel.y + px(426)), 12, self._overlay_message_color)
        else:
            desc = info.description or "No description."
            desc_lines = wrap_text(desc, 12, col_w)[:3]
            y = panel.y + px(76)
            draw_text(surface, "DESCRIPTION", (col_x, y), 10, config.TEXT_FAINT, kind="bold")
            for index, line in enumerate(desc_lines):
                draw_text(surface, line, (col_x, y + px(16 + 17 * index)), 12, config.TEXT_DIM)
            y += px(76)
            draw_text(surface, "TAGS", (col_x, y), 10, config.TEXT_FAINT, kind="bold")
            self._draw_tag_chips(surface, info.tags, col_x, y + px(16), col_w)
            y += px(64)
            draw_text(surface, "Fx", (col_x, y), 11, config.TEXT_FAINT, kind="bold", anchor="midleft")
            draw_text(surface, fit_text(info.fx or "-", col_w - px(30), 12, "mono"),
                      (col_x + px(26), y), 12, config.TEXT, kind="mono", anchor="midleft")
            y += px(22)
            draw_text(surface, "Fy", (col_x, y), 11, config.TEXT_FAINT, kind="bold", anchor="midleft")
            draw_text(surface, fit_text(info.fy or "-", col_w - px(30), 12, "mono"),
                      (col_x + px(26), y), 12, config.TEXT, kind="mono", anchor="midleft")
            y += px(30)
            uses = (f"Uses {info.usage_count} · successful {info.successful_usage_count} "
                    f"({info.success_rate * 100:.0f}%)")
            draw_text(surface, fit_text(uses, col_w, 13), (col_x, y), 13, config.TEXT)
            y += px(22)
            draw_text(surface, f"Unique players {info.unique_user_count}", (col_x, y), 13, config.TEXT)
            y += px(30)
            avg = info.average_rating
            count = info.rating_count
            draw_text(surface, "RATING", (col_x, y), 10, config.TEXT_FAINT, kind="bold")
            self._star_rects = self._star_rects_layout((col_x, y + px(14)))
            my_rating = self._my_ratings.get(str(row.get("id")))
            from ..ui_icons import icon_surface
            for index, star in enumerate(self._star_rects):
                filled = my_rating is not None and index < my_rating
                avg_fill = my_rating is None and index < int(round(avg))
                if filled:
                    color = (255, 205, 80)
                elif avg_fill:
                    color = (190, 160, 70)
                else:
                    color = (70, 80, 110)
                icon = icon_surface("star", star.w, color)
                surface.blit(icon, icon.get_rect(center=star.center))
            caption = f"{avg:.1f} · {count} rating{'s' if count != 1 else ''}" if count else "no ratings yet"
            draw_text(surface, caption, (col_x + px(5 * _STAR_W), y + px(14 + (_STAR_W - 4) // 2)),
                      12, config.WARNING if count else config.TEXT_DIM, anchor="midleft")
            if self._overlay_message:
                draw_text(surface, fit_text(self._overlay_message, col_w, 12),
                          (col_x, panel.bottom - px(84)), 12, self._overlay_message_color)

        # --- bottom button row ----------------------------------------------
        buttons = self._overlay_buttons
        if self._edit_mode:
            buttons["save"].draw(surface)
            buttons["cancel"].draw(surface)
        else:
            buttons["import"].draw(surface)
            buttons["favorite"].draw(surface)
            if owner:
                buttons["edit"].draw(surface)
                buttons["delete"].draw(surface)
            else:
                draw_text(surface, "Only the uploader can edit or delete this function.",
                          (buttons["edit"].rect.x, buttons["edit"].rect.centery), 12,
                          config.TEXT_FAINT, anchor="midleft")
            buttons["close"].draw(surface)

    def _draw_tag_chips(self, surface, tags, x, y, max_width):
        tags = normalize_tags(tags)
        if not tags:
            draw_text(surface, "no tags", (x, y), 11, config.TEXT_FAINT)
            return
        cursor_x = x
        for index, tag in enumerate(tags[:6]):
            width_px = px(14) + int(get_text_width(tag, 11))
            if cursor_x + width_px > x + max_width:
                draw_text(surface, f"+{len(tags) - index}", (cursor_x, y + px(5)),
                          11, config.TEXT_FAINT)
                return
            rect = pygame.Rect(cursor_x, y, width_px, px(22))
            pygame.draw.rect(surface, (36, 46, 76), rect, border_radius=px(11))
            pygame.draw.rect(surface, config.PANEL_EDGE, rect, width=1, border_radius=px(11))
            draw_text(surface, fit_text(tag, width_px - px(12), 11), rect.center, 11,
                      config.TEXT_DIM, anchor="center")
            cursor_x += width_px + px(8)

    def _draw_import_overlay(self, surface):
        panel = _overlay_panel(_IMPORT_W, _IMPORT_H)
        self._shade(surface)
        pygame.draw.rect(surface, config.PANEL_BG, panel, border_radius=px(8))
        pygame.draw.rect(surface, config.PANEL_EDGE, panel, width=max(1, px(1)), border_radius=px(8))
        draw_text(surface, "Import to your Function Lab", (panel.centerx, panel.y + px(24)),
                  17, config.TEXT, kind="bold", anchor="center")
        draw_text(surface, "A new function is created in your library;",
                  (panel.centerx, panel.y + px(48)), 12, config.TEXT_DIM, anchor="center")
        draw_text(surface, "the community copy stays where it is.",
                  (panel.centerx, panel.y + px(66)), 12, config.TEXT_DIM, anchor="center")
        draw_text(surface, "NAME", (panel.x + px(28), panel.y + px(88)), 10,
                  config.TEXT_FAINT, kind="bold")
        if self._import_input is not None:
            self._import_input.draw(surface)
        if self._overlay_message:
            draw_text(surface, fit_text(self._overlay_message, panel.w - px(56), 12),
                      (panel.x + px(28), panel.y + px(150)), 12, self._overlay_message_color)
        self._import_buttons["import"].draw(surface)
        self._import_buttons["cancel"].draw(surface)


def get_text_width(text, size):
    from ..ui_fonts import get_font

    font = get_font(size)
    return font.size(str(text))[0]


# Aliases (the scene is reachable under a few names in tests and scripts).
CommunityFunctionScene = CommunityFunctionsScene
CommunityFunctions = CommunityFunctionsScene
PublicFunctionsScene = CommunityFunctionsScene
CommunityFunctionBrowserScene = CommunityFunctionsScene
