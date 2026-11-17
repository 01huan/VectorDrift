"""Community levels: the Levels tab of the shared Community page.

Reads from the public ``community_levels`` Supabase table (anybody may read),
so no login is required to browse.  Opening a card downloads the level JSON,
registers it for this session and starts the level.  A community level is not
the player's own: it never joins the player's custom levels.

The shared browser (search, sort, filter, pagination, cards, tab bar) lives
in :mod:`vector_drift.scenes.community_browser` and is used identically by the
Functions tab; this module only carries what is specific to levels.

The rules live in :mod:`vector_drift.community_browse`; this module only
draws them.
"""

from __future__ import annotations

import pygame

from .. import config, data
from ..community_browse import (
    DEFAULT_PICKUP_KIND,
    PICKUP_KINDS,
    PICKUP_LABELS,
    SORT_DEFAULT_DESCENDING,
    SORT_NEWEST,
    SORT_TABLE,
    CommunityLevelInfo,
    filter_levels,
    level_info,
)
from ..config import px
from ..data import LevelSpec
from ..image_assets import load_image
from ..ui import Button, TextInput, draw_text, fit_text
from ..account import community
from .community_browser import (
    _EXTRA_W,
    _EXTRA_X,
    _FILTER_Y,
    _MIN_INPUT_GAP,
    _MIN_INPUT_W,
    _MIN_INPUT_X,
    _TOOLBAR_Y,
    CommunityBrowserScene,
)

_EDITOR_ID_SPACE = 1000     # the level editor hands out ids starting here


def _fresh_editor_id(session) -> int:
    """A fresh editor id for a local copy, unused by built-ins and customs."""
    custom_ids = getattr(session, "custom_level_ids", set()) if session is not None else set()
    candidate = _EDITOR_ID_SPACE

    def in_use(candidate: int) -> bool:
        if candidate < _EDITOR_ID_SPACE:
            return True
        if candidate in data.CUSTOM_LEVELS or candidate in custom_ids:
            return True
        return any(getattr(level, "id", None) == candidate for level in data.LEVELS)

    while in_use(candidate):
        candidate += 1
    return candidate


def _editable_local_id(level_data, session) -> int:
    """The id the local editable copy of a published level may keep.

    Keeping the original ``level_data.id`` lets the level editor's existing
    "re-upload updates the same community row" behaviour work: saving the
    edit syncs the published row instead of creating a duplicate.  The
    original id is only reused when it is a plausible editor id (>= 1000)
    and unused; otherwise a fresh editor id is handed out.
    """
    raw = level_data.get("id") if isinstance(level_data, dict) else None
    try:
        rid = int(raw)
    except (TypeError, ValueError, OverflowError):
        rid = None

    custom_ids = getattr(session, "custom_level_ids", set()) if session is not None else set()

    def in_use(candidate: int) -> bool:
        if candidate < _EDITOR_ID_SPACE:
            return True
        if candidate in data.CUSTOM_LEVELS or candidate in custom_ids:
            return True
        return any(getattr(level, "id", None) == candidate for level in data.LEVELS)

    if rid is not None and not in_use(rid):
        return rid
    return _fresh_editor_id(session)


class CommunityLevelsScene(CommunityBrowserScene):
    kind = "levels"
    content_label = "levels"
    back_label = "Back"

    def _default_back_target(self):
        from .level_editor_menu import LevelEditorMenuScene

        return LevelEditorMenuScene

    # ------------------------------------------------------------------ hooks

    def _default_sort_key(self):
        return SORT_NEWEST

    @staticmethod
    def _default_direction(sort_key: str) -> bool:
        return SORT_DEFAULT_DESCENDING.get(sort_key, False)

    def _sort_table(self):
        return SORT_TABLE

    def _build_extra_widgets(self):
        self.sort_key = SORT_NEWEST
        self.descending = True
        self.pickup_kind = DEFAULT_PICKUP_KIND
        self.pickup_button = Button((px(_EXTRA_X), px(_TOOLBAR_Y), px(_EXTRA_W), px(30)),
                                    "Pickup: Money", style="plain", font_size=14)
        self.min_plays_input = TextInput(
            (px(_MIN_INPUT_X), px(_FILTER_Y), px(_MIN_INPUT_W), px(28)),
            "plays", font_size=13, numeric=True, on_change=self._on_filter_changed)
        self.min_clears_input = TextInput(
            (px(_MIN_INPUT_X + _MIN_INPUT_W + _MIN_INPUT_GAP), px(_FILTER_Y), px(_MIN_INPUT_W), px(28)),
            "clears", font_size=13, numeric=True, on_change=self._on_filter_changed)
        self.min_clearers_input = TextInput(
            (px(_MIN_INPUT_X + 2 * (_MIN_INPUT_W + _MIN_INPUT_GAP)), px(_FILTER_Y), px(_MIN_INPUT_W), px(28)),
            "players", font_size=13, numeric=True, on_change=self._on_filter_changed)

    def _extra_inputs(self):
        return (self.min_plays_input, self.min_clears_input, self.min_clearers_input)

    def _extra_state(self):
        return {"pickup_kind": self.pickup_kind}

    def _restore_extra_state(self, state):
        kind = state.get("pickup_kind")
        if kind in PICKUP_KINDS:
            self.pickup_kind = kind

    def _reset_extra_filters(self):
        self.pickup_kind = DEFAULT_PICKUP_KIND

    def _handle_extra_event(self, event):
        if self.pickup_button.handle_event(event) == "click":
            self.audio.play("click")
            self._cycle_pickup_kind()
            return True
        return False

    def _cycle_pickup_kind(self):
        """Next pickup kind for the "how many of this pickup" sort."""
        try:
            index = PICKUP_KINDS.index(self.pickup_kind)
        except ValueError:
            index = 0
        self.pickup_kind = PICKUP_KINDS[(index + 1) % len(PICKUP_KINDS)]
        self._on_filter_changed()

    def _draw_extra_toolbar(self, surface):
        self.pickup_button.label = f"Pickup: {PICKUP_LABELS.get(self.pickup_kind, self.pickup_kind)}"
        self.pickup_button.draw(surface)

    def _draw_extra_filters(self, surface):
        self.min_plays_input.draw(surface)
        self.min_clears_input.draw(surface)
        self.min_clearers_input.draw(surface)

    def _filter_caption(self):
        return "At least"

    # ---------------------------------------------------------------- data hooks

    def _fetch_rows(self, on_success, on_error):
        community.fetch_community_levels(on_success=on_success, on_error=on_error)

    def _delete_row(self, row_id, account, on_success, on_error):
        community.delete_community_level(row_id, account, on_success=on_success, on_error=on_error)

    def _info_for_row(self, row):
        return level_info(row)

    def _filter_infos(self, infos):
        return filter_levels(
            infos,
            name_query=self.name_input.text,
            uploader_query=self.uploader_input.text,
            min_plays=self._min_count(self.min_plays_input),
            min_clears=self._min_count(self.min_clears_input),
            min_clearers=self._min_count(self.min_clearers_input),
            sort_key=self.sort_key,
            descending=self.descending,
            pickup_kind=self.pickup_kind,
        )

    def _manage_rect(self, rect):
        return self._card_button_rect(rect, 52)

    def _favorite_rect(self, rect, row=None):
        """The ↓ (import) button: last on owned cards, first otherwise.

        Occupies the engagement slot shared with the Functions tab's
        favorite button.
        """
        owner = self._is_owner(row) if row is not None else False
        return self._card_button_rect(rect, 78 if owner else 26)

    def _toggle_favorite(self, row):
        """The import action: save a private copy into your custom levels.

        The published level is never modified and the local copy always gets
        a fresh editor id, so importing never overwrites or shadows any
        existing custom level — not even one of your own.
        """
        if not isinstance(row, dict):
            self.status = "Invalid level data: cannot import."
            return
        level_data = row.get("level_data")
        if not isinstance(level_data, dict):
            self.status = "Invalid level data: cannot import."
            return
        local_id = _fresh_editor_id(self.session)
        try:
            spec = data.level_spec_from_public(level_data, local_id)
        except (ValueError, TypeError, OverflowError) as exc:
            self.status = f"Invalid level data: {exc}"
            return
        try:
            data.register_custom_level(spec)
        except ValueError as exc:
            self.status = f"Cannot import: {exc}"
            return
        custom = list(getattr(self.session, "custom_levels", ()) or [])
        if all(getattr(item, "id", None) != spec.id for item in custom):
            custom.append(spec)
            self.session.custom_levels = custom
        ids = set(getattr(self.session, "custom_level_ids", set()) or set())
        ids.add(spec.id)
        self.session.custom_level_ids = ids
        try:
            from ..account.integration import save_progress
            save_progress(self.manager.account, self.session)
        except Exception:  # noqa: BLE001 - importing must not block the page
            pass
        self.status = f"Imported “{spec.name}” into your custom levels."
        self._dirty = True

    def _edit(self, lvl):
        """Open a local, editable copy of a level the user published.

        The copy is added to the player's own custom levels (it is never an
        alias of the published row); keeping the original ``level_data.id``
        when it is free lets the level editor sync the published row on
        save through the existing machinery.  If no local id is reusable the
        copy gets a fresh id and re-publishing creates a new row.
        """
        if not self._is_owner(lvl):
            self.status = "You can only edit your own uploads."
            return
        level_data = lvl.get("level_data") if isinstance(lvl, dict) else None
        if not isinstance(level_data, dict):
            self.status = "Invalid level data: cannot open the editor."
            return
        try:
            local_id = _editable_local_id(level_data, self.session)
            spec = data.level_spec_from_public(level_data, local_id)
        except (ValueError, TypeError, OverflowError) as exc:
            self.status = f"Invalid level data: {exc}"
            return
        try:
            data.register_custom_level(spec)
        except ValueError as exc:
            self.status = f"Cannot edit: {exc}"
            return
        custom = list(getattr(self.session, "custom_levels", ()) or [])
        if all(getattr(item, "id", None) != spec.id for item in custom):
            custom.append(spec)
            self.session.custom_levels = custom
        ids = set(getattr(self.session, "custom_level_ids", set()) or set())
        ids.add(spec.id)
        self.session.custom_level_ids = ids
        try:
            from ..account.integration import save_progress
            save_progress(self.manager.account, self.session)
        except Exception:  # noqa: BLE001 - saving the copy must not block the editor
            pass
        self.status = f"Editing “{spec.name}” — a local copy. Save re-publishes your upload."
        from .level_editor import LevelEditorScene
        self.manager.switch(LevelEditorScene(self.manager, level=spec))

    def _primary_action(self, row):
        self._open(row)

    # ------------------------------------------------------------------ cards

    def _open(self, lvl: dict):
        level_id = data.community_level_id(lvl.get("id"))
        try:
            spec = self._deserialize(lvl.get("level_data") or {}, level_id)
        except (ValueError, TypeError, OverflowError) as exc:
            self.status = f"Invalid level data: {exc}"
            return
        # A community level belongs to another player: it is registered in the
        # community registry only.  It is never added to the player's own
        # custom levels, so playing it does not put it into the level editor
        # list (and does not save it with the profile).
        data.register_community_level(spec)
        self.session.level_id = spec.id
        self.session.fx_text = self.session.fy_text = ""
        self.session.random_seed = None
        self.session.level_source = "community"
        from .game import GameScene
        self.manager.switch(GameScene(self.manager))

    def _deserialize(self, d: dict, level_id: int) -> LevelSpec:
        """Validate public ``level_data`` into a spec with a local id.

        The uploader-supplied ``id`` is ignored: ``level_id`` is generated
        locally from the remote row UUID (see ``data.community_level_id``), so
        a crafted integer can never become a global level id.
        """
        return data.level_spec_from_public(d, level_id)

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

    def _draw_card(self, surface, lvl: dict, info: CommunityLevelInfo, rect: pygame.Rect,
                   del_rect=None, manage_rect=None, fav_rect=None):
        """One level card: name, uploader, preview, layout numbers and stats."""
        self._draw_card_frame(surface, rect)
        self._draw_preview(surface, lvl, rect)

        name_w = rect.w - px(150) if self._is_owner(lvl) else rect.w - px(34)
        name = fit_text(info.name or "Community", max(60, name_w), 15, kind="bold")
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

        # Management buttons (only for the uploader) + the import action.
        self._draw_owner_buttons(surface, lvl, del_rect, manage_rect)
        if fav_rect is not None:
            hover = fav_rect.collidepoint(pygame.mouse.get_pos())
            bg = (52, 155, 105) if hover else (40, 120, 80)
            pygame.draw.rect(surface, bg, fav_rect, border_radius=px(3))
            draw_text(surface, "↓", fav_rect.center, 15, (255, 255, 255),
                      kind="bold", anchor="center")


# Aliases (the scene is reachable under a few names in tests and scripts).
CommunityLevelScene = CommunityLevelsScene
CommunityBrowserLevelsScene = CommunityLevelsScene
