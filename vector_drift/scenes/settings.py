"""Application settings scene."""

import pygame

from .. import config, i18n
from ..config import px
from ..ui import Button, draw_panel_box, draw_text
from .base import Scene


class SettingsScene(Scene):
    def __init__(self, manager):
        super().__init__(manager)
        self.back_button = Button((px(40), config.WINDOW_H - px(86), px(180), px(46)), "Back",
                                  style="plain", font_size=17)
        self.language_buttons = []
        width, height, gap = px(260), px(48), px(14)
        top = config.WINDOW_H // 2 - (len(i18n.SUPPORTED_LANGUAGES) * height
                                      + (len(i18n.SUPPORTED_LANGUAGES) - 1) * gap) // 2
        for index, language in enumerate(i18n.SUPPORTED_LANGUAGES):
            rect = (config.WINDOW_W // 2 - width // 2, top + index * (height + gap), width, height)
            self.language_buttons.append((language, Button(rect, i18n.LANGUAGE_NAMES[language],
                                                            style="plain", font_size=18)))

    def _current_language(self) -> str:
        """The language actually in use; keep the session mirroring it.

        i18n.preferences() is the single source of truth for rendering (an
        async profile restore can change it at any time).  Session.language is
        the copy persisted into the profile; keep the two in step so saving
        never writes a stale code.
        """
        current = i18n.preferences().language
        if getattr(self.session, "language", None) != current:
            self.session.language = current
        return current

    def handle_event(self, event):
        escaped = event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE
        if self.back_button.handle_event(event) == "click" or escaped:
            self._back()
            return
        for language, button in self.language_buttons:
            if button.handle_event(event) == "click":
                self._select_language(language)
                return

    def _select_language(self, language: str) -> None:
        previous = self._current_language()
        changed = i18n.set_language(language)
        self.session.language = language
        self.audio.play("click")
        # Save when the rendered language or the session's copy changed, so a
        # stale session.language is repaired instead of being left unsaved.
        if changed or language != previous:
            from vector_drift.account.integration import save_progress
            save_progress(self.manager.account, self.session)

    def _back(self):
        self.audio.play("click")
        from .menu import MenuScene
        self.manager.switch(MenuScene(self.manager))

    def draw(self, surface):
        surface.fill(config.BG)
        card = pygame.Rect(0, 0, px(560), px(350))
        card.center = (config.WINDOW_W // 2, config.WINDOW_H // 2)
        draw_panel_box(surface, card)
        current = self._current_language()
        draw_text(surface, "Language Settings", (card.centerx, card.y + px(44)), 30, config.ACCENT, kind="bold", anchor="center")
        draw_text(surface, "Choose the language used by Vector Drift.", (card.centerx, card.y + px(88)), 16, config.TEXT_DIM, anchor="center")
        for language, button in self.language_buttons:
            button.style = "primary" if language == current else "plain"
            button.draw(surface)
        self.back_button.draw(surface)
