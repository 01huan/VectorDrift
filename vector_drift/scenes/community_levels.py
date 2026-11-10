"""Community levels: browse and play custom levels uploaded by other players.

Reads from the public ``community_levels`` Supabase table (anybody may read),
so no login is required to browse.  Opening a card downloads the level JSON,
registers it locally and starts the level.
"""

from __future__ import annotations

import pygame

from .. import config, data
from ..config import px
from ..data import LevelSpec, ObstacleSpec, PickupSpec, HoleSpec
from ..image_assets import load_image
from ..ui import Button, draw_text
from ..account import community
from .base import Scene


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
        self._load()

    def handle_event(self, event):
        if self.back_button.handle_event(event) == "click":
            self.audio.play("click")
            from .level_editor_menu import LevelEditorMenuScene
            self.manager.switch(LevelEditorMenuScene(self.manager))
            return
        if self.refresh_button.handle_event(event) == "click":
            self.audio.play("click")
            self._load()
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

    def _load(self):
        self.busy = True
        self.status = "Loading community levels..."
        self.cards = []
        self.delete_rects = []
        self.levels = []
        community.fetch_community_levels(on_success=self._on_loaded, on_error=self._on_error)

    def _on_loaded(self, rows):
        self.levels = rows or []
        self.status = f"Found {len(self.levels)} community level(s)."
        self.busy = False

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

    def _rebuild(self):
        self.cards = []
        self.delete_rects = []
        x, y = px(60), px(100)
        for i, lvl in enumerate(self.levels):
            rect = pygame.Rect(x + (i % 4) * px(260), y + (i // 4) * px(180), px(240), px(160))
            self.cards.append((lvl, rect))
            self.delete_rects.append(
                pygame.Rect(rect.right - px(22), rect.y + px(6), px(16), px(16))
            )

    def _deserialize(self, d: dict) -> LevelSpec:
        obstacles = tuple(
            ObstacleSpec(
                center=tuple(item["center"]),
                radius=float(item["radius"]),
                restitution=float(item.get("restitution", 1.0)),
                kind=item.get("kind", "bumper"),
            )
            for item in d.get("obstacles", ())
        )
        pickups = tuple(
            PickupSpec(
                center=tuple(item["center"]),
                radius=float(item.get("radius", 0.45)),
                kind=item.get("kind", "shockwave"),
            )
            for item in d.get("pickups", ())
        )
        holes = tuple(
            HoleSpec(
                black_center=tuple(item.get("black_center", item.get("black", (0.0, 0.0)))),
                white_center=tuple(item.get("white_center", item.get("white", (0.0, 0.0)))),
                radius=float(item.get("radius", 0.5)),
            )
            for item in d.get("holes", ())
        )
        return LevelSpec(
            id=int(d["id"]),
            name=str(d.get("name", "Community")),
            start=tuple(d["start"]),
            target_center=tuple(d["target_center"]),
            target_radius=float(d["target_radius"]),
            ship_id=str(d.get("ship_id", "ship01")),
            time_limit=float(d.get("time_limit", 10.0)),
            lives=int(d.get("lives", 5)),
            obstacles=obstacles,
            pickups=pickups,
            holes=holes,
        )

    def _open(self, lvl: dict):
        try:
            spec = self._deserialize(lvl.get("level_data") or {})
        except Exception as exc:  # noqa: BLE001 - show a friendly message
            self.status = f"Invalid level data: {exc}"
            return
        data.register_custom_level(spec)
        if spec.id not in self.session.custom_level_ids:
            self.session.custom_levels.append(spec)
            self.session.custom_level_ids.add(spec.id)
        self.session.level_id = spec.id
        self.session.fx_text = self.session.fy_text = ""
        self.session.random_seed = None
        self.session.level_source = "community"
        from .game import GameScene
        self.manager.switch(GameScene(self.manager))

    # ------------------------------------------------------------------ preview

    def _draw_preview(self, surface, lvl: dict, rect: pygame.Rect):
        """Draw a tiny preview of the level layout inside ``rect``."""
        preview = pygame.Rect(rect.x + px(10), rect.y + px(56), px(220), px(80))
        pygame.draw.rect(surface, (26, 34, 60), preview, border_radius=px(3))
        pygame.draw.rect(surface, config.PANEL_EDGE, preview, width=1, border_radius=px(3))

        data_ = lvl.get("level_data") or {}
        pts = [tuple(data_.get("start", (-7.0, 0.0))), tuple(data_.get("target_center", (7.0, 0.0)))]
        for o in data_.get("obstacles", ()):
            pts.append(tuple(o["center"]))
        for p in data_.get("pickups", ()):
            pts.append(tuple(p["center"]))
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
        for idx, o in enumerate(data_.get("obstacles", ())):
            cx, cy = to_screen(*o["center"])
            r = max(2, min(max_r, int(float(o.get("radius", 0.4)) * scale)))
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
        for p in data_.get("pickups", ()):
            cx, cy = to_screen(*p["center"])
            kind = p.get("kind", "shockwave")
            r = max(2, min(max_r, int(float(p.get("radius", 0.3)) * scale)))
            if r < 2:
                continue
            pickup_key = {
                "shockwave": "pickup.shockwave",
                "extratime": "pickup.extratime",
                "shield": "pickup.shield",
                "life": "pickup.life",
                "money": "pickup.money",
                "unbound": "pickup.unbound",
            }.get(kind, "pickup.shockwave")
            img = load_image(pickup_key, size_px=(max(1, 2 * r), max(1, 2 * r)))
            if img is not None:
                surface.blit(img, img.get_rect(center=(int(cx), int(cy))))
            else:
                # Fallback: gold disc with dark edge
                pygame.draw.circle(surface, (240, 190, 60), (int(cx), int(cy)), r)
                pygame.draw.circle(surface, (40, 40, 50), (int(cx), int(cy)), r, 1)

        # Start: use the launch-pad marker picture
        sx, sy = to_screen(*data_.get("start", (-7.0, 0.0)))
        r_start = max(3, min(max_r, int(0.25 * scale)))
        img = load_image("ui.start_marker", size_px=(max(1, 2 * r_start), max(1, 2 * r_start)))
        if img is not None:
            surface.blit(img, img.get_rect(center=(int(sx), int(sy))))
        else:
            pygame.draw.circle(surface, (80, 200, 90), (int(sx), int(sy)), r_start)

        # Target: use the destination planet picture
        tx, ty = to_screen(*data_.get("target_center", (7.0, 0.0)))
        r_target = max(4, min(max_r, int(0.35 * scale)))
        img = load_image("target.planet", size_px=(max(1, 2 * r_target), max(1, 2 * r_target)))
        if img is not None:
            surface.blit(img, img.get_rect(center=(int(tx), int(ty))))
        else:
            pygame.draw.circle(surface, (210, 90, 90), (int(tx), int(ty)), r_target)

    # ------------------------------------------------------------------ draw

    def draw(self, surface):
        surface.fill(config.BG)
        self.back_button.draw(surface)
        self.refresh_button.draw(surface)
        self._rebuild()
        draw_text(surface, "Community Levels", (config.WINDOW_W // 2, px(40)), 30,
                  config.TEXT, kind="bold", anchor="center")
        for (lvl, rect), del_rect in zip(self.cards, self.delete_rects):
            pygame.draw.rect(surface, config.PANEL_BG, rect, border_radius=px(6))
            pygame.draw.rect(surface, config.PANEL_EDGE, rect, width=max(1, px(1)), border_radius=px(6))
            self._draw_preview(surface, lvl, rect)
            name = str(lvl.get("level_name") or "Community")
            draw_text(surface, name, (rect.x + px(10), rect.y + px(10)), 16, config.TEXT, kind="bold")
            uploader = str(lvl.get("uploader_name") or "")
            draw_text(surface, uploader or "—", (rect.x + px(10), rect.y + px(146)), 12, config.TEXT_DIM)
            created = str(lvl.get("created_at") or "")[:10]
            draw_text(surface, created, (rect.right - px(10), rect.y + px(10)), 12, config.TEXT_DIM,
                      anchor="topright")
            # Delete button (only shown for the uploader).
            if self._is_owner(lvl):
                hover = del_rect.collidepoint(pygame.mouse.get_pos())
                bg = config.DANGER if hover else (140, 60, 70)
                pygame.draw.rect(surface, bg, del_rect, border_radius=px(3))
                draw_text(surface, "×", del_rect.center, 16, (255, 255, 255),
                          kind="bold", anchor="center")
        if self.busy:
            draw_text(surface, self.status or "Loading...", (config.WINDOW_W // 2, config.WINDOW_H - px(60)),
                      15, config.WARNING, anchor="center")
        elif self.status:
            draw_text(surface, self.status, (config.WINDOW_W // 2, config.WINDOW_H - px(60)),
                      15, config.SUCCESS, anchor="center")
