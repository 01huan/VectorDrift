"""Scene interface, shared session state and the scene manager."""

import logging
from dataclasses import dataclass, field
from datetime import date

import pygame

from .. import config
from ..data import is_community_level, is_custom_map
from ..money import Money
from ..config import px
from ..desktop import set_cursor
from ..ui import Button, draw_text

log = logging.getLogger(__name__)


@dataclass
class Session:
    """State shared between scenes during one run of the game."""
    level_id: int = 1
    ship_id: str | None = None                      # the ship the current level flies (set by GameScene)
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
    owned_ships: set = field(default_factory=lambda: {"ship01"})  # ships bought before levels fixed them; kept, unused
    collected_money_pickups: set = field(default_factory=set)  # (level_id, cx, cy) of money pickups already taken
    collected_random_coins: set = field(default_factory=set)   # (level_id, seed, (cx, cy)); this launch only, not saved
    clear_rewarded_levels: set = field(default_factory=set)    # fixed level ids whose clear reward was paid (saved)
    clear_rewarded_maps: set = field(default_factory=set)      # (level_id, seed) paid the clear reward; this launch only
    random_map_clears: dict = field(default_factory=dict)      # (level_id, seed) -> clears; this launch only (XP)
    custom_levels: list = field(default_factory=list)   # player-created LevelSpecs
    custom_level_ids: set = field(default_factory=set)
    next_custom_level_id: int = 1000  # monotonic high-water for custom level ids (saved); never re-issued
    # The Function Lab's library: named Fx/Fy pairs the player saved.
    function_library: list = field(default_factory=list)     # list of SavedFunction
    imported_function_id: str | None = None                 # the one imported for levels
    level_source: str | None = None  # where the current level was launched from
    level_select_page: tuple | None = None  # (page, level_id) level select last showed; this launch only
    seen_intro: bool = False        # the intro story has started once (saved; first Start plays it)
    player_key: str | None = None   # local id of this player (community statistics); saved
    achievements: dict = field(default_factory=dict)          # achievement id -> ISO time unlocked (saved)
    achievement_progress: dict = field(default_factory=dict)  # counters toward achievements (saved)
    # --- experience and player level (all saved; see xp.py) ----------------
    xp_total: int = 0                                         # all XP ever gained
    fixed_clear_counts: dict = field(default_factory=dict)    # fixed level id -> clears so far
    xp_achievements: set = field(default_factory=set)         # achievement ids that paid their XP
    xp_rewarded_level: int = 1                                # highest level whose coins were paid
    # --- daily challenge (see daily_records.py) ----------------------------
    daily_records: dict = field(default_factory=dict)         # "YYYY-MM-DD" -> that day's record (saved)
    daily_day: date | None = None   # the day whose map this daily run plays; this launch only
    # --- account (optional, Supabase) -------------------------------------
    user_id: str | None = None
    email: str | None = None
    display_name: str | None = None
    auth_status: str = "guest"          # guest | pending_verification | authenticated
    profile_loaded: bool = False
    sync_status: str = "idle"           # idle | syncing | error
    cloud_save_pending: bool = False    # deferred cloud upload while account busy
    last_sync_error: str | None = None

    @property
    def imported_function(self):
        """The function the player imported for use in the normal levels."""
        from ..function_library import find_function

        return find_function(self.function_library, self.imported_function_id)

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
    level_id = getattr(session, "level_id", None)

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

    s = str(source).lower() if source is not None else ""

    # A community level is somebody else's level: it goes back to the public
    # browser it was opened from, never to the player's own level list.
    if "community" in s or is_community_level(level_id):
        from .community_levels import CommunityLevelsScene
        return CommunityLevelsScene

    if not is_custom_map(level_id, session):
        from .levels import LevelSelectScene
        return LevelSelectScene

    if "editor" in s:
        from .level_editor_menu import LevelEditorMenuScene
        return LevelEditorMenuScene
    from .levels import LevelSelectScene
    return LevelSelectScene


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


ACHIEVEMENT_CHECK_S = 1.0       # how often SceneManager re-checks saved progress


class SceneManager:
    def __init__(self, audio, account_manager=None):
        self.audio = audio
        self.account = account_manager
        self.session = Session()
        self.scene = None
        self.running = True
        self.time = 0.0
        self.screen = None          # the surface the game draws on (set by main)
        from .achievement_ui import ToastStack
        self.toasts = ToastStack()  # achievement popups, drawn over every scene
        self._achievement_check_in = 0.0

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
            # Retry a cloud upload that was deferred because the account
            # manager was busy.  By now poll() has drained the queue, so a
            # still-idle manager means we can safely start the upload.
            try:
                if (not getattr(self.account, "is_busy", False)
                        and getattr(self.session, "cloud_save_pending", False)):
                    from vector_drift.account.integration import save_progress
                    save_progress(self.account, self.session)
            except Exception:
                pass
        self.scene.update(dt)
        self.toasts.update(dt)
        self._achievement_check_in -= dt
        if self._achievement_check_in <= 0.0:
            # Unlocks that saved progress already proves: purchases, old
            # saves loaded from disk or the cloud, ...
            self._achievement_check_in = ACHIEVEMENT_CHECK_S
            try:
                from ..achievements import check_state
                check_state(self)
            except Exception:       # noqa: BLE001 - a broken check never stops the game
                log.debug("achievement check skipped", exc_info=True)

    def draw(self, surface):
        self.scene.draw(surface)
        self.toasts.draw(surface)


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
