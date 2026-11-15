"""Community levels: browse, search, sort and play custom levels uploaded
by other players.

Reads from the public ``community_levels`` Supabase table (anybody may read),
so no login is required to browse.  Opening a card downloads the level JSON,
registers it locally and starts the level.

The page has a search bar:

* two fuzzy text searches -- one for the level name, one for the uploader;
  the closer a level matches, the earlier it is listed;
* sort orders for the time limit, the number of obstacles, the number of
  pickups (total, or of one chosen pickup kind), the number of plays, the
  number of clears and the number of players who cleared the level;
* minimum filters for the same three statistics.

The rules live in :mod:`vector_drift.community_browse`; this module only
draws them.
"""

from __future__ import annotations

from dataclasses import replace

import pygame

from .. import config, data
from ..config import px
from ..community_browse import (
    DEFAULT_PICKUP_KIND,
    PICKUP_KINDS,
    PICKUP_LABELS,
    SORT_DEFAULT_DESCENDING,
    SORT_KEYS,
    SORT_LABELS,
    SORT_NEWEST,
    CommunityLevelInfo,
    filter_levels,
    level_info,
)
from ..data import LevelSpec
from ..image_assets import load_image
from ..level_pages import can_next, can_prev, clamp_page, levels_on_page, page_count, wheel_step
from ..ui import Button, TextInput, draw_text, fit_text
from ..account import community
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
_PICKUP_BUTTON_X = 678
_PICKUP_BUTTON_W = 168
_RESET_BUTTON_X = 854
_RESET_BUTTON_W = 84
_MIN_CAPTION_X = 36
_MIN_INPUT_X = 86
_MIN_INPUT_W = 92
_MIN_INPUT_GAP = 8

_TOOLBAR_Y = 54
_FILTER_Y = 90
_CARDS_Y = 126
_CARD_W = 240
_CARD_H = 152
_CARD_GAP_X = 20
_CARD_GAP_Y = 14
_CARDS_X = 60
_COLUMNS = 4


class CommunityLevelsScene(Scene):
    music = "menu"

    def __init__(self, manager):
        super().__init__(manager)
        self.back_button = Button((px(40), config.WINDOW_H - px(86), px(180), px(46)), "Levels",
                                  style="plain", font_size=17)
        self.refresh_button = Button((config.WINDOW_W - px(200), px(20), px(160), px(40)), "Refresh",
                                     style="plain", font_size=17)
        self.cards = []
        self.levels = []
        self.delete_rects = []        # parallel to self.cards: delete button per row
        self.deleting = None          # level id currently being deleted
        self.busy = False
        self.status = ""

        # --- search / sort / filter -------------------------------------
        self.sort_key = SORT_NEWEST
        self.descending = True
        self.pickup_kind = DEFAULT_PICKUP_KIND
        self.name_input = TextInput(
            (px(_NAME_INPUT_X), px(_TOOLBAR_Y), px(_NAME_INPUT_W), px(30)),
            "level name", font_size=14, on_change=self._on_filter_changed)
        self.uploader_input = TextInput(
            (px(_UPLOADER_INPUT_X), px(_TOOLBAR_Y), px(_UPLOADER_INPUT_W), px(30)),
            "uploader", font_size=14, on_change=self._on_filter_changed)
        self.min_plays_input = TextInput(
            (px(_MIN_INPUT_X), px(_FILTER_Y), px(_MIN_INPUT_W), px(28)),
            "plays", font_size=13, numeric=True, on_change=self._on_filter_changed)
        self.min_clears_input = TextInput(
            (px(_MIN_INPUT_X + _MIN_INPUT_W + _MIN_INPUT_GAP), px(_FILTER_Y), px(_MIN_INPUT_W), px(28)),
            "clears", font_size=13, numeric=True, on_change=self._on_filter_changed)
        self.min_clearers_input = TextInput(
            (px(_MIN_INPUT_X + 2 * (_MIN_INPUT_W + _MIN_INPUT_GAP)), px(_FILTER_Y), px(_MIN_INPUT_W), px(28)),
            "players", font_size=13, numeric=True, on_change=self._on_filter_changed)
        self.sort_button = Button((px(_SORT_BUTTON_X), px(_TOOLBAR_Y), px(_SORT_BUTTON_W), px(30)),
                                  "Sort: Newest", style="plain", font_size=14)
        self.sort_dir_button = Button((px(_DIR_BUTTON_X), px(_TOOLBAR_Y), px(_DIR_BUTTON_W), px(30)),
                                      "↓", style="plain", font_size=15)
        self.pickup_button = Button((px(_PICKUP_BUTTON_X), px(_TOOLBAR_Y), px(_PICKUP_BUTTON_W), px(30)),
                                    "Pickup: Money", style="plain", font_size=14)
        self.reset_button = Button((px(_RESET_BUTTON_X), px(_TOOLBAR_Y), px(_RESET_BUTTON_W), px(30)),
                                   "Reset", style="plain", font_size=14)
        # Paging: only the cards that fit on the screen are drawn, the rest
        # is reached with these buttons or with the mouse wheel.
        self.prev_page_button = Button((config.WINDOW_W - px(212), config.WINDOW_H - px(86), px(96), px(46)),
                                       "Prev", style="plain", font_size=16)
        self.next_page_button = Button((config.WINDOW_W - px(106), config.WINDOW_H - px(86), px(96), px(46)),
                                       "Next", style="plain", font_size=16)

        self._info_cache = {}        # row id -> CommunityLevelInfo (cleared on refresh)
        self._preview_cache = {}     # row id -> validated LevelSpec (or None)
        self._filtered = []          # the levels the current search shows
        self._page_entries = []      # the ones on the page that is shown
        self._dirty = True           # the card list has to be rebuilt
        self.page = 0                # the page of the search result that is shown
        self._last_wheel = None      # time of the last wheel event (one gesture, one page)
        self._load()

    # ------------------------------------------------------------------ events

    def handle_event(self, event):
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
        if self.pickup_button.handle_event(event) == "click":
            self.audio.play("click")
            self._cycle_pickup_kind()
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
            from .level_editor_menu import LevelEditorMenuScene
            self.manager.switch(LevelEditorMenuScene(self.manager))
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
            # Delete own upload first (small button in the top-right corner).
            for (lvl, rect), del_rect in zip(self.cards, self.delete_rects):
                if del_rect.collidepoint(event.pos):
                    self._delete(lvl)
                    return
            # Otherwise open the level.
            for lvl, rect in self.cards:
                if rect.collidepoint(event.pos):
                    self.audio.play("click")
                    self._open(lvl)
                    return

    def _handle_input_event(self, event) -> bool:
        """Let the text fields handle the event; True when the text changed."""
        changed = False
        for widget in (self.name_input, self.uploader_input, self.min_plays_input,
                       self.min_clears_input, self.min_clearers_input):
            if widget.handle_event(event):
                changed = True
        if changed:
            self._on_filter_changed()
        return changed

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
        self._dirty = True

    def _handle_wheel(self, event) -> None:
        """The mouse wheel turns the page (one gesture turns one page)."""
        now = pygame.time.get_ticks() / 1000.0
        step, self._last_wheel = wheel_step(getattr(event, "y", 0), now, self._last_wheel)
        if step:
            self._change_page(step)

    # ----------------------------------------------------------------- loading

    def _load(self):
        self.busy = True
        self.status = "Loading community levels..."
        self.cards = []
        self.delete_rects = []
        self.levels = []
        self._filtered = []
        self._info_cache.clear()
        self._preview_cache.clear()
        self._dirty = True
        community.fetch_community_levels(on_success=self._on_loaded, on_error=self._on_error)

    def _on_loaded(self, rows):
        self.levels = rows or []
        self.status = f"Found {len(self.levels)} community level(s)."
        self.busy = False
        self._dirty = True

    def _on_error(self, exc):
        self.status = f"Failed to load community levels: {exc}"
        self.busy = False

    def _is_owner(self, lvl: dict) -> bool:
        account = self.manager.account
        if account is None or not account.is_authenticated() or account.current_user is None:
            return False
        return str(lvl.get("user_id")) == str(account.current_user.id)

    def _delete(self, lvl: dict):
        if not self._is_owner(lvl):
            self.status = "You can only delete your own uploads."
            return
        account = self.manager.account
        level_id = str(lvl.get("id"))
        self.deleting = level_id
        self.status = "Deleting..."

        def on_ok(_result=None):
            self.deleting = None
            self.status = "Deleted."
            self._load()

        def on_err(exc):
            self.deleting = None
            self.status = f"Delete failed: {exc}"

        community.delete_community_level(level_id, account, on_success=on_ok, on_error=on_err)

    # ---------------------------------------------------------------- filtering

    def _on_filter_changed(self, *_args):
        """A search box, a filter or a sort button changed: rebuild the list."""
        self._dirty = True

    def _cycle_sort(self):
        """Next sort order (the direction follows the new order)."""
        try:
            index = SORT_KEYS.index(self.sort_key)
        except ValueError:
            index = 0
        self.sort_key = SORT_KEYS[(index + 1) % len(SORT_KEYS)]
        self.descending = self._default_direction(self.sort_key)
        self._on_filter_changed()

    def _cycle_pickup_kind(self):
        """Next pickup kind for the "how many of this pickup" sort."""
        try:
            index = PICKUP_KINDS.index(self.pickup_kind)
        except ValueError:
            index = 0
        self.pickup_kind = PICKUP_KINDS[(index + 1) % len(PICKUP_KINDS)]
        self._on_filter_changed()

    @staticmethod
    def _default_direction(sort_key: str) -> bool:
        return SORT_DEFAULT_DESCENDING.get(sort_key, False)

    def _reset_filters(self):
        """Clear every search box and go back to the default order."""
        for widget in (self.name_input, self.uploader_input, self.min_plays_input,
                       self.min_clears_input, self.min_clearers_input):
            widget.clear()
        self.sort_key = SORT_NEWEST
        self.descending = True
        self.pickup_kind = DEFAULT_PICKUP_KIND
        self._on_filter_changed()

    def _min_count(self, widget) -> int:
        try:
            return max(0, int(widget.text or 0))
        except (TypeError, ValueError):
            return 0

    def _entries(self):
        """``(row, info)`` for every level, parsing each row only once."""
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
                info = replace(level_info(row), row_id=key)
                self._info_cache[key] = info
            entries.append((row, info))
        return entries

    def _filtered_entries(self):
        """The ``(row, info)`` pairs the current search shows."""
        entries = self._entries()
        rows_by_id = {info.row_id: row for row, info in entries}
        matched = filter_levels(
            [info for _row, info in entries],
            name_query=self.name_input.text,
            uploader_query=self.uploader_input.text,
            min_plays=self._min_count(self.min_plays_input),
            min_clears=self._min_count(self.min_clears_input),
            min_clearers=self._min_count(self.min_clearers_input),
            sort_key=self.sort_key,
            descending=self.descending,
            pickup_kind=self.pickup_kind,
        )
        return [(rows_by_id.get(info.row_id), info) for info in matched]

    # ------------------------------------------------------------------- cards

    def _rebuild(self):
        """(Re)build the visible cards from the current search result."""
        self._filtered = self._filtered_entries()
        self.page = clamp_page(self.page, self.page_count())
        visible = levels_on_page(self._filtered, self.page, self._per_page)
        self._page_entries = visible
        self.cards = []
        self.delete_rects = []
        x, y = px(_CARDS_X), px(_CARDS_Y)
        step_x = px(_CARD_W + _CARD_GAP_X)
        step_y = px(_CARD_H + _CARD_GAP_Y)
        for index, (row, _info) in enumerate(visible):
            if row is None:
                continue
            rect = pygame.Rect(x + (index % _COLUMNS) * step_x, y + (index // _COLUMNS) * step_y,
                               px(_CARD_W), px(_CARD_H))
            self.cards.append((row, rect))
            self.delete_rects.append(
                pygame.Rect(rect.right - px(22), rect.y + px(6), px(16), px(16))
            )
        self.prev_page_button.enabled = can_prev(self.page)
        self.next_page_button.enabled = can_next(self.page, self.page_count())

    def _visible_count(self) -> int:
        """How many cards fit on the screen (the rest is not drawn)."""
        space = config.WINDOW_H - px(_CARDS_Y) - px(24)
        fit = int((space + px(_CARD_GAP_Y)) // (px(_CARD_H) + px(_CARD_GAP_Y)))
        return max(1, fit) * _COLUMNS

    def _deserialize(self, d: dict, level_id: int) -> LevelSpec:
        """Validate public ``level_data`` into a spec with a local id.

        The uploader-supplied ``id`` is ignored: ``level_id`` is generated
        locally from the remote row UUID (see ``data.community_level_id``), so
        a crafted integer can never become a global level id.
        """
        return data.level_spec_from_public(d, level_id)

    def _open(self, lvl: dict):
        level_id = data.community_level_id(lvl.get("id"))
        try:
            spec = self._deserialize(lvl.get("level_data") or {}, level_id)
        except (ValueError, TypeError, OverflowError) as exc:
            self.status = f"Invalid level data: {exc}"
            return
        data.register_custom_level(spec)
        self.session.custom_levels = [lv for lv in self.session.custom_levels if lv.id != spec.id]
        self.session.custom_levels.append(spec)
        self.session.custom_level_ids.add(spec.id)
        self.session.level_id = spec.id
        self.session.fx_text = self.session.fy_text = ""
        self.session.random_seed = None
        self.session.level_source = "community"
        from .game import GameScene
        self.manager.switch(GameScene(self.manager))

    # ------------------------------------------------------------------ preview

    def _preview_spec(self, lvl: dict):
        """The validated spec of a row, cached (parsing is not free)."""
        if not isinstance(lvl, dict):
            return None
        key = str(lvl.get("id") or "")
        if key and key in self._preview_cache:
            return self._preview_cache[key]
        try:
            spec = data.level_spec_from_public(lvl.get("level_data") or {}, 0)
        except (ValueError, TypeError, OverflowError):
            spec = None
        if key:
            self._preview_cache[key] = spec
        return spec

    def _draw_preview(self, surface, lvl: dict, rect: pygame.Rect):
        """Draw a tiny preview of the level layout inside ``rect``.

        The public ``level_data`` is validated first; an invalid row just
        leaves the empty preview instead of raising while the player browses.
        """
        preview = pygame.Rect(rect.x + px(10), rect.y + px(46), px(220), px(66))
        pygame.draw.rect(surface, (26, 34, 60), preview, border_radius=px(3))
        pygame.draw.rect(surface, config.PANEL_EDGE, preview, width=1, border_radius=px(3))
        spec = self._preview_spec(lvl)
        if spec is None:
            return

        pts = [spec.start, spec.target_center]
        for o in spec.obstacles:
            pts.append(o.center)
        for p in spec.pickups:
            pts.append(p.center)
        for h in getattr(spec, "holes", ()) or ():
            pts.append(h.black_center)
            pts.append(h.white_center)
        if not pts:
            return

        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        pad = 1.0
        minx, maxx = min(xs) - pad, max(xs) + pad
        miny, maxy = min(ys) - pad, max(ys) + pad
        world_w = maxx - minx or 1.0
        world_h = maxy - miny or 1.0
        scale = min(preview.w / world_w, preview.h / world_h)

        def to_screen(wx, wy):
            return (preview.x + (wx - minx) * scale, preview.bottom - (wy - miny) * scale)

        # 缩略图内对象半径上限：按最短边的 1/3 计算，避免障碍物/道具超出预览
        max_r = max(8, min(preview.w, preview.h) // 4)

        # Obstacles: use real rock pictures (fall back to light-grey circle if missing)
        for idx, o in enumerate(spec.obstacles):
            cx, cy = to_screen(*o.center)
            r = max(2, min(max_r, int(o.radius * scale)))
            if r < 2:
                continue
            rock_key = f"obstacle.rock{(idx % 2) + 1:02d}"
            img = load_image(rock_key, size_px=(max(1, 2 * r), max(1, 2 * r)))
            if img is not None:
                surface.blit(img, img.get_rect(center=(int(cx), int(cy))))
            else:
                # Fallback: light-grey circle
                pygame.draw.circle(surface, (130, 130, 150), (int(cx), int(cy)), r)
                pygame.draw.circle(surface, (180, 180, 200), (int(cx), int(cy)), r, 1)

        # Pickups: use real pickup pictures (fall back to colour disc)
        for p in spec.pickups:
            cx, cy = to_screen(*p.center)
            r = max(2, min(max_r, int(p.radius * scale)))
            if r < 2:
                continue
            pickup_key = {
                "shockwave": "pickup.shockwave",
                "extratime": "pickup.extratime",
                "shield": "pickup.shield",
                "life": "pickup.life",
                "money": "pickup.money",
                "unbound": "pickup.unbound",
            }.get(p.kind, "pickup.shockwave")
            img = load_image(pickup_key, size_px=(max(1, 2 * r), max(1, 2 * r)))
            if img is not None:
                surface.blit(img, img.get_rect(center=(int(cx), int(cy))))
            else:
                # Fallback: gold disc with dark edge
                pygame.draw.circle(surface, (240, 190, 60), (int(cx), int(cy)), r)
                pygame.draw.circle(surface, (40, 40, 50), (int(cx), int(cy)), r, 1)

        # Holes: use real black/white hole pictures (fall back to discs)
        for h in getattr(spec, "holes", ()) or ():
            bcx, bcy = to_screen(*h.black_center)
            wcx, wcy = to_screen(*h.white_center)
            r = max(2, min(max_r, int(float(getattr(h, "radius", 0.5)) * scale)))
            if r < 2:
                continue
            black_img = load_image("black_hole.black_hole01",
                                 size_px=(max(1, 2 * r), max(1, 2 * r)))
            if black_img is not None:
                surface.blit(black_img, black_img.get_rect(center=(int(bcx), int(bcy))))
            else:
                pygame.draw.circle(surface, (20, 20, 40), (int(bcx), int(bcy)), r)
                pygame.draw.circle(surface, (120, 80, 220), (int(bcx), int(bcy)), r, 1)
            white_img = load_image("white_hole.white_hole01",
                                  size_px=(max(1, 2 * r), max(1, 2 * r)))
            if white_img is not None:
                surface.blit(white_img, white_img.get_rect(center=(int(wcx), int(wcy))))
            else:
                pygame.draw.circle(surface, (240, 240, 255), (int(wcx), int(wcy)), r)
                pygame.draw.circle(surface, (180, 180, 220), (int(wcx), int(wcy)), r, 1)

        # Start: use the launch-pad marker picture
        sx, sy = to_screen(*spec.start)
        r_start = max(3, min(max_r, int(0.25 * scale)))
        img = load_image("ui.start_marker", size_px=(max(1, 2 * r_start), max(1, 2 * r_start)))
        if img is not None:
            surface.blit(img, img.get_rect(center=(int(sx), int(sy))))
        else:
            pygame.draw.circle(surface, (80, 200, 90), (int(sx), int(sy)), r_start)

        # Target: use the destination planet picture
        tx, ty = to_screen(*spec.target_center)
        r_target = max(4, min(max_r, int(0.35 * scale)))
        img = load_image("target.planet", size_px=(max(1, 2 * r_target), max(1, 2 * r_target)))
        if img is not None:
            surface.blit(img, img.get_rect(center=(int(tx), int(ty))))
        else:
            pygame.draw.circle(surface, (210, 90, 90), (int(tx), int(ty)), r_target)

    # -------------------------------------------------------------------- draw

    def _draw_toolbar(self, surface):
        """The search bar: two searches, the sort order and the filters."""
        label_color = config.TEXT_DIM
        draw_text(surface, "Name", (px(_NAME_CAPTION_X), px(_TOOLBAR_Y + 15)), 13,
                  label_color, anchor="midleft")
        self.name_input.draw(surface)
        draw_text(surface, "By", (px(_UPLOADER_CAPTION_X), px(_TOOLBAR_Y + 15)), 13,
                  label_color, anchor="midleft")
        self.uploader_input.draw(surface)
        self.sort_button.label = f"Sort: {SORT_LABELS.get(self.sort_key, self.sort_key)}"
        self.sort_button.draw(surface)
        self.sort_dir_button.label = "↓" if self.descending else "↑"
        self.sort_dir_button.draw(surface)
        self.pickup_button.label = f"Pickup: {PICKUP_LABELS.get(self.pickup_kind, self.pickup_kind)}"
        self.pickup_button.draw(surface)
        self.reset_button.draw(surface)

        draw_text(surface, "At least", (px(_MIN_CAPTION_X), px(_FILTER_Y + 14)), 13,
                  label_color, anchor="midleft")
        self.min_plays_input.draw(surface)
        self.min_clears_input.draw(surface)
        self.min_clearers_input.draw(surface)

        total = len(self.levels)
        shown = len(self._filtered)
        pages = self.page_count()
        if total:
            summary = f"{shown} of {total} level(s) · page {self.page + 1}/{pages}"
        else:
            summary = "no levels"
        if self.name_input.text or self.uploader_input.text:
            summary += " · closest match first"
        draw_text(surface, summary, (px(_MIN_INPUT_X + 3 * (_MIN_INPUT_W + _MIN_INPUT_GAP) + 8),
                                     px(_FILTER_Y + 14)), 13, config.TEXT, anchor="midleft")

    def _draw_card(self, surface, lvl: dict, info: CommunityLevelInfo, rect: pygame.Rect,
                   del_rect=None):
        """One level card: name, uploader, preview, layout numbers and stats."""
        pygame.draw.rect(surface, config.PANEL_BG, rect, border_radius=px(6))
        pygame.draw.rect(surface, config.PANEL_EDGE, rect, width=max(1, px(1)), border_radius=px(6))
        self._draw_preview(surface, lvl, rect)

        name = fit_text(info.name or "Community", rect.w - px(34), 15, kind="bold")
        draw_text(surface, name, (rect.x + px(10), rect.y + px(8)), 15, config.TEXT, kind="bold")
        uploader = fit_text(info.uploader or "—", rect.w - px(90), 12)
        draw_text(surface, uploader, (rect.x + px(10), rect.y + px(28)), 12, config.TEXT_DIM)
        created = (info.created_at or "")[:10]
        draw_text(surface, created, (rect.right - px(10), rect.y + px(28)), 11,
                  config.TEXT_FAINT, anchor="topright")

        layout = f"{info.time_limit:g}s · {info.obstacle_count} obstacles · {info.pickup_count} pickups"
        draw_text(surface, fit_text(layout, rect.w - px(20), 11), (rect.x + px(10), rect.y + px(114)),
                  11, config.TEXT_DIM)
        stats = (f"plays {info.play_count} · clears {info.clear_count}"
                 f" · players {info.clear_player_count}")
        draw_text(surface, fit_text(stats, rect.w - px(20), 11), (rect.x + px(10), rect.y + px(130)),
                  11, config.TEXT_DIM)

        # Delete button (only shown for the uploader).
        if del_rect is not None and self._is_owner(lvl):
            hover = del_rect.collidepoint(pygame.mouse.get_pos())
            bg = config.DANGER if hover else (140, 60, 70)
            pygame.draw.rect(surface, bg, del_rect, border_radius=px(3))
            draw_text(surface, "×", del_rect.center, 16, (255, 255, 255),
                      kind="bold", anchor="center")

    def draw(self, surface):
        surface.fill(config.BG)
        self.back_button.draw(surface)
        self.refresh_button.draw(surface)
        self.prev_page_button.draw(surface)
        self.next_page_button.draw(surface)
        if self._dirty:
            self._rebuild()
            self._dirty = False
        draw_text(surface, "Community Levels", (config.WINDOW_W // 2, px(30)), 28,
                  config.TEXT, kind="bold", anchor="center")
        self._draw_toolbar(surface)
        for (lvl, rect), del_rect, (_row, info) in zip(self.cards, self.delete_rects,
                                                        self._page_entries):
            self._draw_card(surface, lvl, info, rect, del_rect)
        if self.busy:
            draw_text(surface, self.status or "Loading...", (config.WINDOW_W // 2, config.WINDOW_H - px(60)),
                      15, config.WARNING, anchor="center")
        elif self.status:
            draw_text(surface, self.status, (config.WINDOW_W // 2, config.WINDOW_H - px(60)),
                      15, config.SUCCESS, anchor="center")
