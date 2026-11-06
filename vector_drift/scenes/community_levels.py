"""Community levels: browse and play custom levels uploaded by other players.

Reads from the public ``community_levels`` Supabase table (anybody may read),
so no login is required to browse.  Opening a card downloads the level JSON,
registers it locally and starts the level.
"""

from __future__ import annotations

import pygame

from .. import config, data
from ..config import px
from ..data import LevelSpec, ObstacleSpec, PickupSpec
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
            for lvl, rect in self.cards:
                if rect.collidepoint(event.pos):
                    self.audio.play("click")
                    self._open(lvl)
                    return

    def _load(self):
        self.busy = True
        self.status = "Loading community levels..."
        self.cards = []
        self.levels = []
        community.fetch_community_levels(on_success=self._on_loaded, on_error=self._on_error)

    def _on_loaded(self, rows):
        self.levels = rows or []
        self.status = f"Found {len(self.levels)} community level(s)."
        self.busy = False

    def _on_error(self, exc):
        self.status = f"Failed to load community levels: {exc}"
        self.busy = False

    def _rebuild(self):
        self.cards = []
        x, y = px(60), px(100)
        for i, lvl in enumerate(self.levels):
            rect = pygame.Rect(x + (i % 4) * px(260), y + (i // 4) * px(180), px(240), px(160))
            self.cards.append((lvl, rect))

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
        from .game import GameScene
        self.manager.switch(GameScene(self.manager))

    def draw(self, surface):
        surface.fill(config.BG)
        self.back_button.draw(surface)
        self.refresh_button.draw(surface)
        self._rebuild()
        draw_text(surface, "Community Levels", (config.WINDOW_W // 2, px(40)), 30,
                  config.TEXT, kind="bold", anchor="center")
        for lvl, rect in self.cards:
            pygame.draw.rect(surface, config.PANEL_BG, rect, border_radius=px(6))
            pygame.draw.rect(surface, config.PANEL_EDGE, rect, width=max(1, px(1)), border_radius=px(6))
            name = str(lvl.get("level_name") or "Community")
            draw_text(surface, name, (rect.x + px(10), rect.y + px(10)), 16, config.TEXT, kind="bold")
            email = str(lvl.get("uploader_email") or "")
            draw_text(surface, email, (rect.x + px(10), rect.y + px(38)), 13, config.TEXT_DIM)
            created = str(lvl.get("created_at") or "")[:10]
            draw_text(surface, created, (rect.right - px(10), rect.y + px(10)), 13, config.TEXT_DIM,
                      anchor="topright")
        if self.busy:
            draw_text(surface, self.status or "Loading...", (config.WINDOW_W // 2, config.WINDOW_H - px(60)),
                      15, config.WARNING, anchor="center")
        elif self.status:
            draw_text(surface, self.status, (config.WINDOW_W // 2, config.WINDOW_H - px(60)),
                      15, config.SUCCESS, anchor="center")
