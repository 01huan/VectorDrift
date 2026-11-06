"""Level editor menu: list of player-created levels + new button."""
import pygame
from .. import config
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

    def _rebuild(self):
        self.cards = []
        levels = self.session.custom_levels
        x, y = px(60), px(100)
        for i, lv in enumerate(levels):
            rect = pygame.Rect(x + (i % 4) * px(260), y + (i // 4) * px(180), px(240), px(160))
            self.cards.append((lv, rect))

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

    def update(self, dt):
        self._rebuild()

    def draw(self, surface):
        surface.fill(config.BG)
        self.back_button.draw(surface)
        self.new_button.draw(surface)
        self.community_button.draw(surface)
        draw_text(surface, "Level Editor", (config.WINDOW_W // 2, px(40)), 30, config.TEXT, kind="bold", anchor="center")
        for lv, rect in self.cards:
            pygame.draw.rect(surface, config.PANEL_BG, rect, border_radius=px(6))
            draw_text(surface, getattr(lv, "name", f"Level {lv.id}"), (rect.x + px(10), rect.y + px(10)), 16, config.TEXT, kind="bold")


# aliases
LevelEditorSelectScene = LevelEditorMenuScene
EditorMenuScene = LevelEditorMenuScene
CustomLevelMenuScene = LevelEditorMenuScene
