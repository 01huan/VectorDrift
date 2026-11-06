"""Level editor menu: list of player-created levels + new button."""
import pygame
from .. import config, data
from ..config import px
from ..ui import Button, draw_text
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

    def _rebuild(self):
        self.cards = []
        self.delete_rects = []
        levels = self.session.custom_levels
        x, y = px(60), px(100)
        for i, lv in enumerate(levels):
            rect = pygame.Rect(x + (i % 4) * px(260), y + (i // 4) * px(180), px(240), px(160))
            self.cards.append((lv, rect))
            self.delete_rects.append(
                pygame.Rect(rect.right - px(22), rect.y + px(6), px(16), px(16))
            )

    def handle_event(self, event):
        if self.back_button.handle_event(event) == "click":
            self.audio.play("click")
            from .levels import LevelSelectScene
            self.manager.switch(LevelSelectScene(self.manager))
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
            for (lv, rect), del_rect in zip(self.cards, self.delete_rects):
                if del_rect.collidepoint(event.pos):
                    self.audio.play("click")
                    self._delete_local_level(lv)
                    return
            for lv, rect in self.cards:
                if rect.collidepoint(event.pos):
                    self.audio.play("click")
                    self.session.level_id = lv.id
                    self.session.fx_text = self.session.fy_text = ""
                    self.session.random_seed = None
                    from .game import GameScene
                    self.manager.switch(GameScene(self.manager))
                    return
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
            for lv, rect in self.cards:
                if rect.collidepoint(event.pos):
                    # right click: edit
                    self.audio.play("click")
                    from .level_editor import LevelEditorScene
                    self.manager.switch(LevelEditorScene(self.manager, level=lv))
                    return

    def _delete_local_level(self, lv):
        """Remove a player-created level that was never uploaded to the community."""
        self.session.custom_levels = [x for x in self.session.custom_levels if x.id != lv.id]
        self.session.custom_level_ids.discard(lv.id)
        data.CUSTOM_LEVELS.pop(lv.id, None)
        for index, level in enumerate(data.LEVELS):
            if level.id == lv.id:
                data.LEVELS.pop(index)
                break
        # Persist locally and sync to the cloud if signed in.
        from ..account.integration import save_progress
        save_progress(self.manager.account, self.session)
        self.message = "Deleted."
        self.message_timer = 1.5

    def update(self, dt):
        self._rebuild()
        if getattr(self, "message_timer", 0) > 0:
            self.message_timer -= dt
            if self.message_timer <= 0:
                self.message = ""


    def draw(self, surface):
        surface.fill(config.BG)
        self.back_button.draw(surface)
        self.new_button.draw(surface)
        self.community_button.draw(surface)
        draw_text(surface, "Level Editor", (config.WINDOW_W // 2, px(40)), 30, config.TEXT, kind="bold", anchor="center")
        for (lv, rect), del_rect in zip(self.cards, self.delete_rects):
            pygame.draw.rect(surface, config.PANEL_BG, rect, border_radius=px(6))
            pygame.draw.rect(surface, config.PANEL_EDGE, rect, width=max(1, px(1)), border_radius=px(6))
            draw_text(surface, getattr(lv, "name", f"Level {lv.id}"), (rect.x + px(10), rect.y + px(10)), 16, config.TEXT, kind="bold")
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
