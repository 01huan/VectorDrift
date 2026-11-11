"""Scene interface, shared session state and the scene manager."""

from dataclasses import dataclass, field

import pygame

from .. import config
from ..money import Money
from ..config import px
from ..desktop import set_cursor
from ..ui import Button, IconButton, draw_text


@dataclass
class Session:
    """State shared between scenes during one run of the game."""
    level_id: int = 1
    ship_id: str | None = None                      # None = the level's default ship
    fx_text: str = ""
    fy_text: str = ""
    editor_history: tuple | None = None             # (level_id, (fx, fy), editor history) kept for Retry
    random_seed: int | None = None  # fixed layout for one dynamic-level run (retry/replay)
    stats: dict = field(default_factory=dict)       # last win/fail details
    records: dict = field(default_factory=dict)     # level_id -> best total flight time (s)
    replays: list = field(default_factory=list)     # stored launch records (fixed capacity)
    hint_answer_confirmed: bool = False             # "Show the answer?" asked once per game launch
    paid_answer_levels: set = field(default_factory=set)  # fixed levels whose answer was paid this launch
    revealed_solver_maps: set = field(default_factory=set)  # (level_id, seed) with AI Solver paid this launch
    money: Money = field(default_factory=Money)     # player's currency balance
    purchased_items: set = field(default_factory=set)   # purchased shop item ids
    ability_charges: dict = field(default_factory=dict)  # consumable ability id -> remaining uses
    owned_ships: set = field(default_factory=lambda: {"ship01"})  # purchased ship skins
    collected_money_pickups: set = field(default_factory=set)  # (level_id, cx, cy) of money pickups already taken
    collected_random_coins: set = field(default_factory=set)   # (level_id, seed, (cx, cy)); this launch only, not saved
    clear_rewarded_levels: set = field(default_factory=set)    # fixed level ids whose clear reward was paid (saved)
    clear_rewarded_maps: set = field(default_factory=set)      # (level_id, seed) paid the clear reward; this launch only
    custom_levels: list = field(default_factory=list)   # player-created LevelSpecs
    custom_level_ids: set = field(default_factory=set)
    level_source: str | None = None  # where the current level was launched from
    seen_intro: bool = False        # the intro story has started once (saved; first Start plays it)
    # --- account (optional, Supabase) -------------------------------------
    user_id: str | None = None
    email: str | None = None
    display_name: str | None = None
    auth_status: str = "guest"          # guest | pending_verification | authenticated
    profile_loaded: bool = False
    sync_status: str = "idle"           # idle | syncing | error
    last_sync_error: str | None = None
    @property
    def launch_records(self):
        return self.replays

    @launch_records.setter
    def launch_records(self, value):
        self.replays = list(value or [])

    @property
    def replay_records(self):
        return self.replays

    @replay_records.setter
    def replay_records(self, value):
        self.replays = list(value or [])

    @property
    def launches(self):
        return self.replays

    @launches.setter
    def launches(self, value):
        self.replays = list(value or [])

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


# Alias properties so callers can use any of these names for the launch origin.
for _alias in ("play_source", "origin", "played_from", "level_origin",
               "source", "return_scene", "back_target"):
    def _make(alias):
        def getter(self):
            return self.level_source
        def setter(self, value):
            self.level_source = value
        return property(getter, setter)
    setattr(Session, _alias, _make(_alias))


def back_scene_for_level(session, scene=None):
    """Return the scene class to go back to from a level (play screen or result screen)."""
    custom_ids = set(getattr(session, "custom_level_ids", ()) or ())
    level_id = getattr(session, "level_id", None)
    is_custom = level_id in custom_ids

    source = None
    for obj in (scene, session):
        if obj is None:
            continue
        for attr in ("level_source", "play_source", "origin", "played_from",
                     "level_origin", "source", "return_scene", "back_target"):
            val = getattr(obj, attr, None)
            if val:
                source = val
                break
        if source:
            break
    # Also check the loaded level object for an origin tag.
    if source is None:
        level_obj = getattr(scene, "level", None) or getattr(scene, "full_level", None)
        if level_obj is not None:
            for attr in ("source", "origin", "level_source"):
                val = getattr(level_obj, attr, None)
                if val:
                    source = val
                    break

    if not is_custom:
        from .levels import LevelSelectScene
        return LevelSelectScene

    s = str(source).lower() if source is not None else ""
    if "community" in s:
        from .community_levels import CommunityLevelsScene
        return CommunityLevelsScene
    if "editor" in s:
        from .level_editor_menu import LevelEditorMenuScene
        return LevelEditorMenuScene
    from .levels import LevelSelectScene
    return LevelSelectScene


class InventoryMixin:
    """Shared inventory icon + modal popup for every screen."""

    def _init_inventory(self):
        self.inventory_button = IconButton((config.WINDOW_W - px(44), px(65), px(32), px(32)),
                                            "inventory", style="circle", color=config.TEXT)
        self.inventory_open = False
        self.inventory_popup = False

    def _handle_inventory_event(self, event):
        result = self.inventory_button.handle_event(event)
        if result == "click":
            try:
                self.audio.play("click")
            except Exception:
                pass
            self.inventory_open = not self.inventory_open
            self.inventory_popup = self.inventory_open
            return True
        if self.inventory_open:
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self.inventory_open = False
                self.inventory_popup = False
                return True
            # Clicking anywhere outside the panel closes it.
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                card = pygame.Rect(0, 0, px(420), px(360))
                card.center = (config.WINDOW_W // 2, config.WINDOW_H // 2)
                if not card.collidepoint(event.pos):
                    self.inventory_open = False
                    self.inventory_popup = False
                    return True
            # Swallow other input while open.
            if event.type in (pygame.MOUSEBUTTONDOWN, pygame.KEYDOWN, pygame.MOUSEMOTION):
                return True
        return False

    def _draw_inventory_button(self, surface):
        try:
            self.inventory_button.draw(surface)
        except Exception:
            pass

    def _draw_inventory_popup(self, surface):
        if not getattr(self, "inventory_open", False):
            return
        shade = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        shade.fill((5, 8, 18, 200))
        surface.blit(shade, (0, 0))
        card = pygame.Rect(0, 0, px(420), px(360))
        card.center = (config.WINDOW_W // 2, config.WINDOW_H // 2)
        pygame.draw.rect(surface, config.PANEL_BG, card, border_radius=px(6))
        pygame.draw.rect(surface, config.ACCENT, card, width=max(1, px(1)), border_radius=px(6))
        draw_text(surface, "Inventory", (card.centerx, card.y + px(22)), 26,
                  config.TEXT, kind="bold", anchor="center")
        session = self.session
        y = card.y + px(64)
        draw_text(surface, "Coins", (card.x + px(24), y), 17, config.ACCENT, kind="bold")
        y += px(24)
        draw_text(surface, f"{int(session.money)} coins", (card.x + px(40), y), 15, config.TEXT)
        y += px(30)
        draw_text(surface, "Skins", (card.x + px(24), y), 17, config.ACCENT, kind="bold")
        y += px(24)
        owned_ships = sorted(getattr(session, "owned_ships", set()) or set())
        if not owned_ships:
            owned_ships = ["ship01"]
        for sid in owned_ships:
            draw_text(surface, str(sid), (card.x + px(40), y), 15, config.TEXT)
            y += px(20)
        y += px(10)
        draw_text(surface, "Active Skills", (card.x + px(24), y), 17, config.ACCENT, kind="bold")
        y += px(24)
        charges = getattr(session, "ability_charges", {}) or {}
        skill_names = {
            "ability_boost": "Boost",
            "ability_shield_pulse": "Shield Pulse",
            "ability_magnet": "Magnet",
        }
        skill_keys = {
            "ability_boost": "B",
            "ability_shield_pulse": "V",
            "ability_magnet": "M",
        }
        any_skill = False
        for aid, name in skill_names.items():
            count = int(charges.get(aid, 0)) if isinstance(charges, dict) else 0
            owned = aid in getattr(session, "purchased_items", set()) or count > 0
            if not owned:
                continue
            any_skill = True
            label = f"{name} ({skill_keys[aid]})"
            if count > 0:
                label = f"{label} x{count}"
            draw_text(surface, label, (card.x + px(40), y), 15, config.TEXT)
            y += px(20)
        if not any_skill:
            draw_text(surface, "None", (card.x + px(40), y), 15, config.TEXT_DIM)
            y += px(20)


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
        from vector_drift.account.integration import save_progress

        save_progress(self.account, self.session)
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
