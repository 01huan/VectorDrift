"""Level editor menu: list of player-created levels + new button."""
import pygame

from .. import config, data
from ..config import px
from ..image_assets import load_image
from ..ui import Button, draw_text
from ..account import community
from .base import Scene


class LevelEditorMenuScene(Scene):
    music = "menu"

    def __init__(self, manager):
        super().__init__(manager)
        self.back_button = Button((px(40), config.WINDOW_H - px(86), px(180), px(46)), "Levels",
                                  style="plain", font_size=17)
        self.new_button = Button((config.WINDOW_W - px(200), px(20), px(180), px(40)), "New",
                                 style="primary", font_size=17)
        self.community_button = Button((px(60), px(20), px(200), px(40)), "Public Levels",
                                       style="plain", font_size=17)
        self.cards = []
        self.delete_rects = []        # parallel to self.cards: delete button per local custom level
        self.message = ""
        self.message_timer = 0.0
        self.page = 0
        self._rebuild()

    def _rebuild(self):
        self.cards = []
        self.delete_rects = []
        self.prev_button = None
        self.next_button = None
        
        all_levels = self.session.custom_levels
        page_size = 12
        self.page_count = max(1, (len(all_levels) + page_size - 1) // page_size)
        self.page = max(0, min(self.page, self.page_count - 1))
        
        current_page_levels = all_levels[self.page * page_size : (self.page + 1) * page_size]
        
        x, y = px(60), px(100)
        for i, lv in enumerate(current_page_levels):
            rect = pygame.Rect(x + (i % 4) * px(260), y + (i // 4) * px(180), px(240), px(160))
            preview = pygame.Rect(rect.x + px(10), rect.y + px(30), px(220), px(120))
            self.cards.append((lv, rect, preview))
            self.delete_rects.append(
                pygame.Rect(rect.right - px(22), rect.y + px(6), px(16), px(16))
            )

        if self.page_count > 1:
            self.prev_button = Button((px(260), config.WINDOW_H - px(86), px(100), px(46)), "Prev", style="plain", font_size=17)
            self.next_button = Button((config.WINDOW_W - px(160), config.WINDOW_H - px(86), px(100), px(46)), "Next", style="plain", font_size=17)

    def handle_event(self, event):
        if self.back_button.handle_event(event) == "click":
            self.audio.play("click")
            from .levels import LevelSelectScene
            self.manager.switch(LevelSelectScene(self.manager))
            return
        if self.prev_button and self.prev_button.handle_event(event) == "click":
            self.audio.play("click")
            self.page -= 1
            self._rebuild()
            return
        if self.next_button and self.next_button.handle_event(event) == "click":
            self.audio.play("click")
            self.page += 1
            self._rebuild()
            return
        if self.new_button.handle_event(event) == "click":
            self.audio.play("click")
            from .level_editor import LevelEditorScene
            self.manager.switch(LevelEditorScene(self.manager))
            return
        if self.community_button.handle_event(event) == "click":
            self.audio.play("click")
            from .community_levels import CommunityLevelsScene
            self.manager.switch(CommunityLevelsScene(self.manager))
            return
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            # Delete a locally created level (not uploaded to the community).
            for (lv, rect, _preview), del_rect in zip(self.cards, self.delete_rects):
                if del_rect.collidepoint(event.pos):
                    self.audio.play("click")
                    self._delete_local_level(lv)
                    return
            for lv, rect, _preview in self.cards:
                if rect.collidepoint(event.pos):
                    self.audio.play("click")
                    self.session.level_id = lv.id
                    self.session.fx_text = self.session.fy_text = ""
                    self.session.random_seed = None
                    self.session.level_source = "level_editor"
                    from .game import GameScene
                    self.manager.switch(GameScene(self.manager))
                    return
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
            for lv, rect, _preview in self.cards:
                if rect.collidepoint(event.pos):
                    # right click: edit
                    self.audio.play("click")
                    from .level_editor import LevelEditorScene
                    self.manager.switch(LevelEditorScene(self.manager, level=lv))
                    return

    def _delete_local_level(self, lv):
        """Remove a player-created level and its community upload (if any)."""
        self.session.custom_levels = [x for x in self.session.custom_levels if x.id != lv.id]
        self.session.custom_level_ids.discard(lv.id)
        # Custom levels live only in CUSTOM_LEVELS; built-in LEVELS are
        # immutable and must never be popped here.
        data.CUSTOM_LEVELS.pop(lv.id, None)
        # Persist locally and sync to the cloud if signed in.
        from ..account.integration import save_progress
        save_progress(self.manager.account, self.session)
        # 若該關卡先前上傳到社區，同步刪除對應的社區關卡（只刪自己的上傳）。
        account = self.manager.account
        if account is not None and account.is_authenticated():
            try:
                community.delete_community_level_by_local_id(account, lv.id)
            except Exception:  # noqa: BLE001 - 本機刪除已完成，社區刪除失敗不應回滾
                pass
        self.message = "Deleted."
        self.message_timer = 1.5

    def update(self, dt):
        self._rebuild()
        if getattr(self, "message_timer", 0) > 0:
            self.message_timer -= dt
            if self.message_timer <= 0:
                self.message = ""


    def _draw_level_preview(self, surface, lv, rect: pygame.Rect) -> None:
        """Draw a small layout preview of a player-created level inside ``rect``."""
        preview = rect
        pygame.draw.rect(surface, (26, 34, 60), preview, border_radius=px(3))
        pygame.draw.rect(surface, config.PANEL_EDGE, preview, width=1, border_radius=px(3))

        data_ = data.custom_level_to_snapshot(lv) or {}
        pts = [tuple(data_.get("start", (-7.0, 0.0))), tuple(data_.get("target_center", (7.0, 0.0)))]
        for o in data_.get("obstacles", ()):
            pts.append(tuple(o["center"]))
        for p in data_.get("pickups", ()):
            pts.append(tuple(p["center"]))
        for h in data_.get("holes", ()):
            pts.append(tuple(h.get("black_center", (0,0))))
            pts.append(tuple(h.get("white_center", (0,0))))
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
        off_x = (preview.w - world_w * scale) / 2.0
        off_y = (preview.h - world_h * scale) / 2.0

        def to_screen(wx, wy):
            return (preview.x + off_x + (wx - minx) * scale,
                    preview.bottom - off_y - (wy - miny) * scale)

        # Object radius cap so large objects do not overflow the preview.
        max_r = max(8, min(preview.w, preview.h) // 4)

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
                pygame.draw.circle(surface, (130, 130, 150), (int(cx), int(cy)), r)
                pygame.draw.circle(surface, (180, 180, 200), (int(cx), int(cy)), r, 1)

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
                pygame.draw.circle(surface, (240, 190, 60), (int(cx), int(cy)), r)
                pygame.draw.circle(surface, (40, 40, 50), (int(cx), int(cy)), r, 1)

        for h in data_.get("holes", ()):
            bc = to_screen(*h.get("black_center", (0,0)))
            wc = to_screen(*h.get("white_center", (0,0)))
            r = max(2, min(max_r, int(float(h.get("radius", 0.5)) * scale)))
            if r < 2: continue
            black_img = load_image("black_hole.black_hole01",
                                 size_px=(max(1, 2 * r), max(1, 2 * r)))
            if black_img is not None:
                surface.blit(black_img, black_img.get_rect(center=(int(bc[0]), int(bc[1]))))
            else:
                pygame.draw.circle(surface, (20, 20, 40), (int(bc[0]), int(bc[1])), r)
                pygame.draw.circle(surface, (120, 80, 220), (int(bc[0]), int(bc[1])), r, 1)
            white_img = load_image("white_hole.white_hole01",
                                 size_px=(max(1, 2 * r), max(1, 2 * r)))
            if white_img is not None:
                surface.blit(white_img, white_img.get_rect(center=(int(wc[0]), int(wc[1]))))
            else:
                pygame.draw.circle(surface, (240, 240, 255), (int(wc[0]), int(wc[1])), r)
                pygame.draw.circle(surface, (180, 180, 220), (int(wc[0]), int(wc[1])), r, 1)

        sx, sy = to_screen(*data_.get("start", (-7.0, 0.0)))
        r_start = max(3, min(max_r, int(0.25 * scale)))
        img = load_image("ui.start_marker", size_px=(max(1, 2 * r_start), max(1, 2 * r_start)))
        if img is not None:
            surface.blit(img, img.get_rect(center=(int(sx), int(sy))))
        else:
            pygame.draw.circle(surface, (80, 200, 90), (int(sx), int(sy)), r_start)

        tx, ty = to_screen(*data_.get("target_center", (7.0, 0.0)))
        r_target = max(4, min(max_r, int(0.35 * scale)))
        img = load_image("target.planet", size_px=(max(1, 2 * r_target), max(1, 2 * r_target)))
        if img is not None:
            surface.blit(img, img.get_rect(center=(int(tx), int(ty))))
        else:
            pygame.draw.circle(surface, (210, 90, 90), (int(tx), int(ty)), r_target)

    def draw(self, surface):
        surface.fill(config.BG)
        self.back_button.draw(surface)
        self.new_button.draw(surface)
        self.community_button.draw(surface)
        if self.prev_button:
            self.prev_button.draw(surface)
        if self.next_button:
            self.next_button.draw(surface)
        draw_text(surface, "Level Editor", (config.WINDOW_W // 2, px(40)), 30, config.TEXT, kind="bold", anchor="center")
        if self.page_count > 1:
            draw_text(surface, f"Page {self.page + 1} / {self.page_count}", (config.WINDOW_W // 2, config.WINDOW_H - px(60)), 15, config.TEXT, anchor="center")
        for (lv, rect, preview), del_rect in zip(self.cards, self.delete_rects):
            pygame.draw.rect(surface, config.PANEL_BG, rect, border_radius=px(6))
            pygame.draw.rect(surface, config.PANEL_EDGE, rect, width=max(1, px(1)), border_radius=px(6))
            self._draw_level_preview(surface, lv, preview)
            draw_text(surface, getattr(lv, "name", f"Level {lv.id}"),
                      (rect.x + px(90), rect.y + px(10)), 16, config.TEXT, kind="bold")
            hover = del_rect.collidepoint(pygame.mouse.get_pos())
            bg = config.DANGER if hover else (140, 60, 70)
            pygame.draw.rect(surface, bg, del_rect, border_radius=px(3))
            draw_text(surface, "×", del_rect.center, 16, (255, 255, 255),
                      kind="bold", anchor="center")
        if self.message:
            draw_text(surface, self.message, (config.WINDOW_W // 2, config.WINDOW_H - px(60)),
                      15, config.SUCCESS, anchor="center")


# aliases
LevelEditorSelectScene = LevelEditorMenuScene
EditorMenuScene = LevelEditorMenuScene
CustomLevelMenuScene = LevelEditorMenuScene
