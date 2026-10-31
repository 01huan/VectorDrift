"""Scene interface, shared session state and the scene manager."""

from dataclasses import dataclass, field

import pygame

from .. import config
from ..money import Money
from ..config import px
from ..desktop import set_cursor
from ..ui import Button, draw_text


@dataclass
class Session:
    """State shared between scenes during one run of the game."""
    level_id: int = 1
    ship_id: str | None = None                      # None = the level's default ship
    fx_text: str = ""
    fy_text: str = ""
    random_seed: int | None = None  # fixed layout for one dynamic-level run (retry/replay)
    stats: dict = field(default_factory=dict)       # last win/fail details
    records: dict = field(default_factory=dict)     # level_id -> best total flight time (s)
    hint_answer_confirmed: bool = False             # "Show the answer?" asked once per game launch
    money: Money = field(default_factory=Money)     # player's currency balance
    purchased_items: set = field(default_factory=set)   # purchased shop item ids
    owned_ships: set = field(default_factory=lambda: {"ship01"})  # purchased ship skins
    collected_money_pickups: set = field(default_factory=set)  # (level_id, cx, cy) of money pickups already taken
    story_seen: set = field(default_factory=set)    # story.py keys: the crawl and level lines already shown
    # --- account (optional, Supabase) -------------------------------------
    user_id: str | None = None
    email: str | None = None
    display_name: str | None = None
    auth_status: str = "guest"          # guest | pending_verification | authenticated
    profile_loaded: bool = False
    sync_status: str = "idle"           # idle | syncing | error
    last_sync_error: str | None = None
    @property
    def unlocked_ships(self):
        return self.owned_ships

    @unlocked_ships.setter
    def unlocked_ships(self, value):
        self.owned_ships = set(value) if value is not None else {"ship01"}

    @property
    def purchased_ships(self):
        return self.owned_ships

    @purchased_ships.setter
    def purchased_ships(self, value):
        self.owned_ships = set(value) if value is not None else {"ship01"}

    @property
    def owned_ship_ids(self):
        return self.owned_ships

    @owned_ship_ids.setter
    def owned_ship_ids(self, value):
        self.owned_ships = set(value) if value is not None else {"ship01"}

    @property
    def unlocked_ship_ids(self):
        return self.owned_ships

    @unlocked_ship_ids.setter
    def unlocked_ship_ids(self, value):
        self.owned_ships = set(value) if value is not None else {"ship01"}


class Scene:
    # Music track for this scene (audio.MUSIC_SLOTS); None keeps whatever plays.
    music = None

    def __init__(self, manager):
        self.manager = manager

    @property
    def session(self):
        return self.manager.session

    @property
    def audio(self):
        return self.manager.audio

    def handle_event(self, event):
        pass

    def update(self, dt):
        pass

    def draw(self, surface):
        pass

    def on_exit(self):
        """Called once when this scene is replaced or the game quits."""
        pass


class SceneManager:
    def __init__(self, audio, account_manager=None):
        self.audio = audio
        self.account = account_manager
        self.session = Session()
        self.scene = None
        self.running = True
        self.time = 0.0
        self.screen = None          # the surface the game draws on (set by main)

    def switch(self, scene):
        if self.scene is not scene:
            self._exit_scene()
        self.scene = scene
        set_cursor("arrow")
        if scene.music is not None and hasattr(self.audio, "set_music"):
            self.audio.set_music(scene.music)

    def quit(self):
        self._exit_scene()
        self.running = False

    def _exit_scene(self):
        on_exit = getattr(self.scene, "on_exit", None)
        if on_exit is not None:
            on_exit()

    def handle_event(self, event):
        if event.type == pygame.QUIT:
            self.quit()
            return
        if event.type == pygame.KEYDOWN and event.key == pygame.K_m and event.mod & pygame.KMOD_CTRL:
            self.audio.toggle_mute()
            return
        self.scene.handle_event(event)

    def update(self, dt):
        self.time += dt
        if hasattr(self.audio, "update"):
            self.audio.update(dt)
        if self.account is not None:
            try:
                self.account.poll()
            except Exception:
                pass
        self.scene.update(dt)

    def draw(self, surface):
        self.scene.draw(surface)


def draw_overlay_card(surface, background, title, title_color, lines, card_h=320):
    'Dimmed snapshot + centered card.'
    if background is not None:
        surface.blit(background, (0, 0))
    shade = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
    shade.fill((5, 8, 18, 200))
    surface.blit(shade, (0, 0))

    card = pygame.Rect(0, 0, px(520), px(card_h))
    card.center = (config.WINDOW_W // 2, config.WINDOW_H // 2)
    pygame.draw.rect(surface, config.PANEL_BG, card, border_radius=px(6))
    pygame.draw.rect(surface, title_color, card, width=max(1, px(1)), border_radius=px(6))
    draw_text(surface, title, (card.centerx, card.y + px(28)), 34, title_color, kind="bold", anchor="midtop")

    y = card.y + px(104)
    for label, value in lines:
        draw_text(surface, label, (card.x + px(48), y), 17, config.TEXT_DIM, anchor="midleft")
        draw_text(surface, value, (card.right - px(48), y), 17, config.TEXT, kind="mono", anchor="midright")
        y += px(30)
    return card


def result_buttons(first_label):
    'Three buttons under a result card.'
    cx, cy = config.WINDOW_W // 2, config.WINDOW_H // 2
    w, h, gap = px(150), px(46), px(14)
    left = cx - (3 * w + 2 * gap) // 2
    labels = (first_label, "Levels", "Main Menu")
    styles = ("primary", "plain", "plain")
    return [Button((left + i * (w + gap), 0, w, h), label, style=style, font_size=17)
            for i, (label, style) in enumerate(zip(labels, styles))]
