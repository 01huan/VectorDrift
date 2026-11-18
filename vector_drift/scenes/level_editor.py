"""Level editor: place and modify objects in the playfield."""
import pygame

from .. import config, data, sprites
from ..config import px
from ..data import LevelSpec, ObstacleSpec, PickupSpec
from ..image_assets import load_image
from ..ui import Button, draw_text
from ..account import community
from ..account.integration import save_progress
from ..coords import Viewport
from .base import Scene


class LevelEditorScene(Scene):
    music = "menu"
    MIN_RADIUS = 0.1
    MAX_RADIUS = 5.0
    START_RADIUS = 0.45

    def __init__(self, manager, level=None):
        super().__init__(manager)
        self.level = level
        # Use the same viewport as the game scene for consistent coordinates
        self.viewport = Viewport()
        self.back_button = Button((config.WINDOW_W - px(260), config.WINDOW_H - px(60), px(120), px(40)),
                                 "Leave", style="plain", font_size=16)
        self.save_button = Button((config.WINDOW_W - px(130), config.WINDOW_H - px(60), px(120), px(40)),
                                 "Save", style="primary", font_size=16)
        self.upload_button = Button((config.WINDOW_W - px(390), config.WINDOW_H - px(60), px(120), px(40)),
                                    "Upload", style="primary", font_size=16)
        self.palette = ["start", "target", "obstacle", "hole", "shockwave", "extratime", "shield", "life", "money", "unbound"]
        self.add_checkpoint_button = Button((config.WINDOW_W - px(620), config.WINDOW_H - px(60), px(150), px(40)),
                                           "Add Checkpoint", style="primary", font_size=14)
        self.delete_checkpoint_button = Button((config.WINDOW_W - px(780), config.WINDOW_H - px(60), px(150), px(40)),
                                              "Delete Checkpoint", style="plain", font_size=14)
        self.prev_section_button = Button((config.WINDOW_W - px(940), config.WINDOW_H - px(60), px(70), px(40)),
                                         "Prev", style="plain", font_size=14)
        self.next_section_button = Button((config.WINDOW_W - px(860), config.WINDOW_H - px(60), px(70), px(40)),
                                         "Next", style="plain", font_size=14)
        self.checkpoint_button = self.add_checkpoint_button
        self.dragging = None
        self.moving = None
        self.move_offset = (0.0, 0.0)
        self.selected = None
        self.context_menu = None
        self.start = (-7.0, 0.0)
        self.target = (7.0, 0.0)
        self.target_radius = 1.0
        self.obstacles = []
        self.pickups = []
        self.holes = []
        self.time_limit = 10.0
        self.sections = []
        self.section_index = 0
        self._placed_start = False
        self._placed_target = False
        self.naming = False
        self._naming_upload = False   # naming mode is used for uploading to the community
        self.name_buffer = ""
        self.message = ""
        self.busy = False             # set while a community upload is in flight
        self.uploaded = False         # an upload finished; reported to achievements on the main thread
        if level is not None:
            self.start = getattr(level, "start", self.start)
            self.target = getattr(level, "target_center", self.target)
            self.target_radius = getattr(level, "target_radius", self.target_radius)
            self.obstacles = [dict(center=o.center, radius=o.radius) for o in getattr(level, "obstacles", ())]
            self.holes = [dict(black_center=tuple(getattr(h, "black_center", h[0] if isinstance(h, (tuple,list)) else (0.0,0.0))), white_center=tuple(getattr(h, "white_center", h[1] if isinstance(h, (tuple,list)) else (0.0,0.0))), radius=float(getattr(h, "radius", (h[2] if isinstance(h, (tuple,list)) and len(h)>2 else 0.5)))) for h in getattr(level, "holes", ())]
            self.pickups = [dict(center=p.center, radius=getattr(p, "radius", 0.45), kind=getattr(p, "kind", "shockwave")) for p in getattr(level, "pickups", ())]
            self.time_limit = float(getattr(level, "time_limit", 10.0))
            self._placed_start = True
            self._placed_target = True
            self.name_buffer = getattr(level, "name", "Custom")
            # Multi-section support.
            if getattr(level, "sections", ()):
                self.sections = [self._state_from_section(s) for s in level.sections]
            else:
                self.sections = [self._current_state()]
            self.section_index = 0
            # Ensure current fields mirror section 0.
            self._apply_section(0)
        else:
            self.sections = [self._current_state()]

    def _screen_to_world(self, pos):
        return self.viewport.to_world(*pos)

    def _state_from_section(self, section):
        def _get(attr, key, default):
            if isinstance(section, dict):
                return section.get(key, default)
            val = getattr(section, attr, None)
            if val is None:
                val = getattr(section, key, None)
            return default if val is None else val

        start = _get("start", "start", self.start)
        target = _get("target_center", "target_center", None)
        if target is None:
            target = _get("target", "target", self.target)
        target_radius = float(_get("target_radius", "target_radius", self.target_radius))
        time_limit = float(_get("time_limit", "time_limit", 10.0))
        # obstacles
        obs_raw = _get("obstacles", "obstacles", ())
        obstacles = []
        for o in obs_raw or ():
            if isinstance(o, dict):
                obstacles.append({"center": tuple(o.get("center", o.get("center"))), "radius": float(o.get("radius", 0.5))})
            else:
                obstacles.append({"center": tuple(getattr(o, "center", (0.0, 0.0))), "radius": float(getattr(o, "radius", 0.5))})
        # pickups
        pick_raw = _get("pickups", "pickups", ())
        pickups = []
        for p in pick_raw or ():
            if isinstance(p, dict):
                pickups.append({"center": tuple(p.get("center", (0.0, 0.0))), "radius": float(p.get("radius", 0.45)), "kind": str(p.get("kind", "shockwave"))})
            else:
                pickups.append({"center": tuple(getattr(p, "center", (0.0, 0.0))), "radius": float(getattr(p, "radius", 0.45)), "kind": str(getattr(p, "kind", "shockwave"))})
        # holes
        hole_raw = _get("holes", "holes", ())
        holes = []
        for h in hole_raw or ():
            if isinstance(h, dict):
                holes.append({
                    "black_center": tuple(h.get("black_center", h.get("black", (0.0, 0.0)))),
                    "white_center": tuple(h.get("white_center", h.get("white", (0.0, 0.0)))),
                    "radius": float(h.get("radius", 0.5)),
                })
            else:
                bc = getattr(h, "black_center", None)
                wc = getattr(h, "white_center", None)
                if bc is None and isinstance(h, (tuple, list)):
                    bc = h[0] if len(h) > 0 else (0.0, 0.0)
                    wc = h[1] if len(h) > 1 else (0.0, 0.0)
                holes.append({
                    "black_center": tuple(bc) if bc is not None else (0.0, 0.0),
                    "white_center": tuple(wc) if wc is not None else (0.0, 0.0),
                    "radius": float(getattr(h, "radius", (h[2] if isinstance(h, (tuple, list)) and len(h) > 2 else 0.5))),
                })
        return {
            "start": tuple(start),
            "target": tuple(target),
            "target_center": tuple(target),
            "target_radius": target_radius,
            "obstacles": obstacles,
            "pickups": pickups,
            "holes": holes,
            "time_limit": time_limit,
        }

    def _current_state(self):
        return {
            "start": tuple(self.start),
            "target": tuple(self.target),
            "target_center": tuple(self.target),
            "target_radius": float(self.target_radius),
            "obstacles": [dict(center=tuple(o["center"]), radius=float(o["radius"])) for o in self.obstacles],
            "pickups": [dict(center=tuple(p["center"]), radius=float(p["radius"]), kind=str(p["kind"])) for p in self.pickups],
            "holes": [dict(black_center=tuple(h["black_center"]), white_center=tuple(h["white_center"]), radius=float(h["radius"])) for h in self.holes],
            "time_limit": float(self.time_limit),
        }

    def _apply_section(self, index):
        if not self.sections:
            self.sections = [self._current_state()]
        if index < 0 or index >= len(self.sections):
            return
        self.section_index = index
        state = self.sections[index]
        self.start = tuple(state.get("start", self.start))
        self.target = tuple(state.get("target", state.get("target_center", self.target)))
        self.target_radius = float(state.get("target_radius", self.target_radius))
        self.obstacles = [dict(center=tuple(o["center"]), radius=float(o["radius"])) for o in state.get("obstacles", [])]
        self.pickups = [dict(center=tuple(p["center"]), radius=float(p["radius"]), kind=str(p["kind"])) for p in state.get("pickups", [])]
        self.holes = [dict(black_center=tuple(h["black_center"]), white_center=tuple(h["white_center"]), radius=float(h["radius"])) for h in state.get("holes", [])]
        self.time_limit = float(state.get("time_limit", 10.0))
        self._placed_start = True
        self._placed_target = True
        self.selected = None
        self.context_menu = None
        self.moving = None

    def _save_current_section(self):
        if not self.sections:
            self.sections = [self._current_state()]
            self.section_index = 0
            return
        if self.section_index < 0 or self.section_index >= len(self.sections):
            self.sections.append(self._current_state())
            self.section_index = len(self.sections) - 1
            return
        self.sections[self.section_index] = self._current_state()

    @property
    def section_count(self):
        return len(self.sections) if self.sections else 1

    @property
    def current_section(self):
        return self.section_index

    def goto_section(self, index):
        if index < 0 or index >= len(self.sections):
            return False
        self._save_current_section()
        self.section_index = index
        self._apply_section(index)
        return True

    def next_section(self):
        if self.section_index < len(self.sections) - 1:
            return self.goto_section(self.section_index + 1)
        return False

    def prev_section(self):
        if self.section_index > 0:
            return self.goto_section(self.section_index - 1)
        return False

    def add_checkpoint(self):
        self._save_current_section()
        prev_target = tuple(self.sections[self.section_index]["target"]) if self.sections else tuple(self.target)
        new_state = {
            "start": (-7.0, 0.0),
            "target": (7.0, 0.0),
            "target_center": (7.0, 0.0),
            "target_radius": 1.0,
            "obstacles": [],
            "pickups": [],
            "holes": [],
            "time_limit": 10.0,
        }
        # Insert after current section.
        insert_at = self.section_index + 1
        if insert_at > len(self.sections):
            insert_at = len(self.sections)
        self.sections.insert(insert_at, new_state)
        self.section_index = insert_at
        self._apply_section(self.section_index)
        return True

    def add_section(self):
        return self.add_checkpoint()

    def delete_checkpoint(self):
        # Delete a checkpoint boundary, merging sections to avoid data loss.
        if len(self.sections) <= 1:
            return False
        self._save_current_section()
        if self.section_index < len(self.sections) - 1:
            # Merge next section into current.
            cur = self.sections[self.section_index]
            nxt = self.sections[self.section_index + 1]
            cur["obstacles"] = list(cur.get("obstacles", [])) + list(nxt.get("obstacles", []))
            cur["pickups"] = list(cur.get("pickups", [])) + list(nxt.get("pickups", []))
            cur["holes"] = list(cur.get("holes", [])) + list(nxt.get("holes", []))
            del self.sections[self.section_index + 1]
            self._apply_section(self.section_index)
            return True
        # Current is last: merge into previous and move back.
        if self.section_index > 0:
            prev = self.sections[self.section_index - 1]
            cur = self.sections[self.section_index]
            prev["obstacles"] = list(prev.get("obstacles", [])) + list(cur.get("obstacles", []))
            prev["pickups"] = list(prev.get("pickups", [])) + list(cur.get("pickups", []))
            prev["holes"] = list(prev.get("holes", [])) + list(cur.get("holes", []))
            del self.sections[self.section_index]
            self.section_index -= 1
            self._apply_section(self.section_index)
            return True
        return False

    def delete_section(self):
        return self.delete_checkpoint()

    def remove_checkpoint(self):
        return self.delete_checkpoint()

    def remove_section(self):
        return self.delete_checkpoint()

    def _object_refs(self):
        refs = [("start", None), ("target", None)]
        refs.extend(("obstacle", i) for i in range(len(self.obstacles)))
        refs.extend(("pickup", i) for i in range(len(self.pickups)))
        refs.extend(("black_hole", i) for i in range(len(self.holes)))
        refs.extend(("white_hole", i) for i in range(len(self.holes)))
        return refs

    def _object_center(self, ref):
        kind, index = ref
        if kind == "start":
            return self.start
        if kind == "target":
            return self.target
        collection = self.obstacles if kind == "obstacle" else self.pickups
        if kind in ("black_hole", "hole"):
            return self.holes[index]["black_center"]
        if kind == "white_hole":
            return self.holes[index]["white_center"]
        return collection[index]["center"]

    def _object_radius(self, ref):
        kind, index = ref
        if kind == "start":
            return self.START_RADIUS
        if kind == "target":
            return self.target_radius
        collection = self.obstacles if kind == "obstacle" else self.pickups
        if kind in ("black_hole", "white_hole", "hole"):
            return self.holes[index]["radius"]
        return collection[index]["radius"]

    def _set_object_center(self, ref, center):
        kind, index = ref
        if kind == "start":
            self.start = center
        elif kind == "target":
            self.target = center
        else:
            if kind == "black_hole" or kind == "hole":
                self.holes[index]["black_center"] = center
            elif kind == "white_hole":
                self.holes[index]["white_center"] = center
            else:
                collection = self.obstacles if kind == "obstacle" else self.pickups
                collection[index]["center"] = center

    def _set_object_radius(self, ref, radius):
        kind, index = ref
        if kind == "target":
            self.target_radius = radius
        elif kind == "start":
            return
        else:
            if kind in ("black_hole", "white_hole", "hole"):
                self.holes[index]["radius"] = radius
            else:
                collection = self.obstacles if kind == "obstacle" else self.pickups
                collection[index]["radius"] = radius

    def _object_at(self, pos):
        world = self._screen_to_world(pos)
        for ref in reversed(self._object_refs()):
            kind, index = ref
            radius = self._object_radius(ref)
            if kind == "black_hole":
                h = self.holes[index]
                centers = [h["black_center"]]
            elif kind == "white_hole":
                h = self.holes[index]
                centers = [h["white_center"]]
            else:
                centers = [self._object_center(ref)]
            for c in centers:
                if (world[0] - c[0]) ** 2 + (world[1] - c[1]) ** 2 <= radius ** 2:
                    return ref
        return None

    def _overlaps(self, center, radius, ignore=None):
        from ..pickups import discs_overlap
        def centers_of(ref):
            kind, index = ref
            if kind == "black_hole":
                h = self.holes[index]
                return [h["black_center"]]
            if kind == "white_hole":
                h = self.holes[index]
                return [h["white_center"]]
            return [self._object_center(ref)]
        for ref in self._object_refs():
            if ref == ignore:
                continue
            for c in centers_of(ref):
                r = self._object_radius(ref)
                if discs_overlap(center, radius, c, r):
                    return True
        # also check the second center of a hole being placed? handled by caller? 
        return False

    def _in_playfield(self, pos):
        # Check if the mouse position is within the viewport (plot area)
        vp_rect = pygame.Rect(self.viewport.rect)
        return vp_rect.collidepoint(pos)

    def _place(self, kind, center):
        radius = self.START_RADIUS if kind == "start" else 1.0 if kind == "target" else 0.5 if kind == "obstacle" else 0.5 if kind in ("hole", "black_hole", "white_hole", "black", "white") else 0.45
        if kind in ("hole", "black_hole", "white_hole", "black", "white"):
            wc = (center[0] + 1.5, center[1])
            if self._overlaps(center, radius) or self._overlaps(wc, radius):
                self.message = "Objects cannot overlap"
                return
            self.holes.append({"black_center": center, "white_center": wc, "radius": radius})
            self.selected = ("black_hole", len(self.holes) - 1)
            self.message = ""
            return
        if self._overlaps(center, radius):
            self.message = "Objects cannot overlap"
            return
        if kind == "start":
            self.start = center
            self._placed_start = True
        elif kind == "target":
            self.target = center
            self.target_radius = radius
            self._placed_target = True
        elif kind == "obstacle":
            self.obstacles.append({"center": center, "radius": radius})
            self.selected = ("obstacle", len(self.obstacles) - 1)
        else:
            self.pickups.append({"center": center, "radius": radius, "kind": kind})
            self.selected = ("pickup", len(self.pickups) - 1)
        self.message = ""

    def _delete_object(self, ref):
        kind, index = ref
        if kind == "start":
            self._placed_start = False
            self.start = (-7.0, 0.0)
        elif kind == "target":
            self._placed_target = False
            self.target = (7.0, 0.0)
            self.target_radius = 1.0
        elif kind == "obstacle":
            self.obstacles.pop(index)
        elif kind in ("hole", "black_hole", "white_hole"):
            self.holes.pop(index)
        else:
            self.pickups.pop(index)
        self.selected = None
        self.context_menu = None
        self.moving = None

    def _open_context_menu(self, pos, ref):
        width, row_height = px(110), px(30)
        x = min(pos[0], config.WINDOW_W - width)
        y = min(pos[1], config.WINDOW_H - row_height * 2)
        self.context_menu = (ref, pygame.Rect(x, y, width, row_height * 2))

    def _handle_context_menu(self, event):
        if self.context_menu is None:
            return False
        ref, rect = self.context_menu
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if rect.collidepoint(event.pos):
                if event.pos[1] < rect.y + rect.height // 2:
                    self._delete_object(ref)
                else:
                    self.selected = ref
                    self.context_menu = None
                    self.message = "Drag to move; use mouse wheel or +/- to resize"
                return True
            self.context_menu = None
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
            self.context_menu = None
        else:
            return True
        return False

    def _resize_selected(self, amount):
        if self.selected is None or self.selected[0] == "start":
            return
        radius = self._object_radius(self.selected)
        new_radius = max(self.MIN_RADIUS, min(self.MAX_RADIUS, radius + amount))
        if new_radius != radius and not self._overlaps(
            self._object_center(self.selected), new_radius, ignore=self.selected
        ):
            self._set_object_radius(self.selected, new_radius)
            self.message = ""
        else:
            self.message = "Objects cannot overlap"

    def _move_selected(self, pos):
        world = self._screen_to_world(pos)
        center = (world[0] + self.move_offset[0], world[1] + self.move_offset[1])
        if not self._overlaps(center, self._object_radius(self.moving), ignore=self.moving):
            self._set_object_center(self.moving, center)
            self.message = ""
        else:
            self.message = "Objects cannot overlap"

    def handle_event(self, event):
        if self.naming:
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                # Cancel naming if clicked outside the name box
                box = pygame.Rect(config.WINDOW_W // 2 - px(220), config.WINDOW_H - px(120), px(440), px(44))
                if not box.collidepoint(event.pos):
                    self.naming = False
                    self.name_buffer = ""
                    self.message = ""
                    return
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_RETURN:
                    name = self.name_buffer or "Custom"
                    if self._naming_upload:
                        self._naming_upload = False
                        self.naming = False
                        self._try_upload(name)
                    elif self._save(name):
                        self.naming = False
                        from .level_editor_menu import LevelEditorMenuScene
                        self.manager.switch(LevelEditorMenuScene(self.manager))
                elif event.key == pygame.K_BACKSPACE:
                    self.name_buffer = self.name_buffer[:-1]
                elif event.unicode and event.unicode.isprintable():
                    self.name_buffer += event.unicode
            return
        if self._handle_context_menu(event):
            return
        if self.back_button.handle_event(event) == "click":
            self.audio.play("click")
            from .level_editor_menu import LevelEditorMenuScene
            self.manager.switch(LevelEditorMenuScene(self.manager))
            return
        if self.save_button.handle_event(event) == "click":
            self.audio.play("click")
            self.naming = True
            self._naming_upload = False
            if not self.name_buffer:
                self.name_buffer = "Custom"
            return
        if self.upload_button.handle_event(event) == "click":
            self.audio.play("click")
            self.naming = True
            self._naming_upload = True
            self.message = ""
            if not self.name_buffer:
                self.name_buffer = "Custom"
            return
        if self.add_checkpoint_button.handle_event(event) == "click":
            self.audio.play("click")
            self.add_checkpoint()
            return
        if self.delete_checkpoint_button.handle_event(event) == "click":
            self.audio.play("click")
            self.delete_checkpoint()
            return
        if self.prev_section_button.handle_event(event) == "click":
            self.audio.play("click")
            self.prev_section()
            return
        if self.next_section_button.handle_event(event) == "click":
            self.audio.play("click")
            self.next_section()
            return
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for i, kind in enumerate(self.palette):
                r = pygame.Rect(px(10), px(60 + i * 46), px(150), px(40))
                if r.collidepoint(event.pos):
                    self.dragging = kind
                    self.selected = None
                    return
            ref = self._object_at(event.pos)
            if ref is not None:
                self.selected = ref
                self.moving = ref
                world = self._screen_to_world(event.pos)
                center = self._object_center(ref)
                self.move_offset = (center[0] - world[0], center[1] - world[1])
                return
            self.selected = None
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
            ref = self._object_at(event.pos)
            if ref is not None:
                self._open_context_menu(event.pos, ref)
                return
        if event.type == pygame.MOUSEMOTION and self.moving is not None:
            self._move_selected(event.pos)
            return
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1 and self.dragging:
            if self._in_playfield(event.pos):
                if self.dragging == "start" and self._placed_start:
                    self.message = "Start is already placed"
                elif self.dragging == "target" and self._placed_target:
                    self.message = "Target is already placed"
                else:
                    self._place(self.dragging, self._screen_to_world(event.pos))
            self.dragging = None
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self.moving = None
        if event.type == pygame.MOUSEWHEEL:
            self._resize_selected(event.y * 0.1)
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_DELETE, pygame.K_BACKSPACE) and self.selected:
                self._delete_object(self.selected)
            elif event.key in (pygame.K_EQUALS, pygame.K_PLUS, pygame.K_KP_PLUS):
                self._resize_selected(0.1)
            elif event.key in (pygame.K_MINUS, pygame.K_KP_MINUS):
                self._resize_selected(-0.1)

    def update(self, dt):
        if self.uploaded:
            self.uploaded = False
            from ..achievements import unlock
            unlock(self.manager, "signal_sent")
        account = self.manager.account
        authenticated = bool(
            account is not None
            and account.is_configured()
            and account.is_authenticated()
            and account.current_user is not None
        )
        self.upload_button.enabled = authenticated
        self.upload_button.label = "Upload" if authenticated else "Upload (login)"

    def _name_conflict(self, name):
        """The player's other custom level carrying ``name``, or None.

        Names are compared ignoring case and repeated whitespace.  The
        level currently being edited is never a conflict with itself.
        """
        key = " ".join(str(name or "").split()).casefold()
        exclude = self.level.id if self.level is not None else None
        for lv in getattr(self.session, "custom_levels", ()) or ():
            if exclude is not None and getattr(lv, "id", None) == exclude:
                continue
            other = " ".join(str(getattr(lv, "name", "") or "").split()).casefold()
            if other == key:
                return lv
        return None

    def _build_spec(self, name="Custom"):
        """Validate the current layout and build a ``LevelSpec`` (or None)."""
        if any(self._overlaps(self._object_center(ref), self._object_radius(ref), ignore=ref)
               for ref in self._object_refs()):
            self.message = "Objects cannot overlap"
            return None
        self._save_current_section()
        level_id = self.level.id if self.level is not None else None
        if level_id is None:
            # Never re-issue an id: the high-water mark (saved in the profile)
            # plus every id the profile still references.  A recycled id would
            # inherit the dead level's records / paid-answer / reward state.
            ref_pools = (
                {lv.id for lv in data.LEVELS},
                getattr(self.session, "custom_level_ids", ()) or (),
                getattr(self.session, "records", ()) or (),          # dict keys
                getattr(self.session, "clear_rewarded_levels", ()) or (),
                getattr(self.session, "paid_answer_levels", ()) or (),
                getattr(self.session, "collected_money_pickups", ()) or (),
            )
            ref_ids = []
            for pool in ref_pools:
                for item in pool:
                    # pools of (level_id, x, y[, ...]) keys unpack to ints too
                    candidate = item[0] if isinstance(item, (tuple, list)) and item else item
                    try:
                        ref_ids.append(int(candidate))
                    except (TypeError, ValueError, OverflowError):
                        continue
            try:
                high_water = int(getattr(self.session, "next_custom_level_id", 1000) or 1000)
            except (TypeError, ValueError, OverflowError):
                high_water = 1000
            level_id = max([999, high_water - 1, *(ref_ids or [999])]) + 1
            self.session.next_custom_level_id = level_id + 1

        from vector_drift.data import HoleSpec, SectionSpec, multi_section_level

        def _convert_state(state):
            obs = tuple(ObstacleSpec(center=tuple(o["center"]), radius=o["radius"]) for o in state.get("obstacles", []))
            picks = tuple(PickupSpec(center=tuple(p["center"]), radius=p["radius"], kind=p["kind"]) for p in state.get("pickups", []))
            hs = tuple(HoleSpec(black_center=tuple(h["black_center"]), white_center=tuple(h["white_center"]), radius=h["radius"]) for h in state.get("holes", []))
            return SectionSpec(
                start=tuple(state.get("start", (-7.0, 0.0))),
                target_center=tuple(state.get("target", state.get("target_center", (7.0, 0.0)))),
                target_radius=float(state.get("target_radius", 1.0)),
                time_limit=float(state.get("time_limit", 10.0)),
                obstacles=obs,
                pickups=picks,
                holes=hs,
            )

        sections_states = self.sections or [self._current_state()]
        if len(sections_states) <= 1:
            st = sections_states[0]
            return LevelSpec(
                id=level_id,
                name=name,
                start=tuple(st.get("start", (-7.0, 0.0))),
                target_center=tuple(st.get("target", st.get("target_center", (7.0, 0.0)))),
                target_radius=float(st.get("target_radius", 1.0)),
                ship_id="ship01",
                time_limit=float(st.get("time_limit", 10.0)),
                obstacles=tuple(ObstacleSpec(center=tuple(o["center"]), radius=o["radius"]) for o in st.get("obstacles", [])),
                pickups=tuple(PickupSpec(center=tuple(p["center"]), radius=p["radius"], kind=p["kind"]) for p in st.get("pickups", [])),
                holes=tuple(HoleSpec(black_center=tuple(h["black_center"]), white_center=tuple(h["white_center"]), radius=h["radius"]) for h in st.get("holes", [])),
                sections=(),
            )
        section_specs = tuple(_convert_state(s) for s in sections_states)
        return multi_section_level(
            id=level_id,
            name=name,
            ship_id="ship01",
            sections=section_specs,
            lives=5,
        )

    def _save(self, name="Custom"):
        conflict = self._name_conflict(name)
        if conflict is not None:
            self.message = f'A level named "{" ".join(str(name).split())}" already exists in your library.'
            self.audio.play("error")
            return False
        spec = self._build_spec(name)
        if spec is None:
            return False
        data.register_custom_level(spec)
        self.session.custom_levels = [lv for lv in self.session.custom_levels if lv.id != spec.id]
        self.session.custom_levels.append(spec)
        self.session.custom_level_ids.add(spec.id)
        save_progress(self.manager.account, self.session)
        from ..achievements import unlock
        unlock(self.manager, "built_different")
        # 若該關卡曾上傳到社區，同步更新名稱與內容，讓公開卡片保持一致。
        # 同步是盡力而為：失敗（例如離峰時段名稱衝突、斷線）會吞掉，
        # 下次上傳前或下次存檔時還能再試。
        account = self.manager.account
        if account is not None and account.is_authenticated():
            try:
                community.update_community_level_by_local_id(
                    account, spec.id, name, community.serialize_level(spec),
                )
            except Exception:  # noqa: BLE001 - 本機儲存已完成，社區同步失敗不應回滾
                pass
        return True

    def _try_upload(self, name):
        """Upload the current editor layout to the public community table."""
        account = self.manager.account
        if account is None or not account.is_configured():
            self.message = "Supabase is not configured."
            return
        if not account.is_authenticated() or account.current_user is None:
            self.message = "Please log in to upload."
            return
        if self.busy:
            return
        conflict = self._name_conflict(name)
        if conflict is not None:
            self.message = f'A level named "{" ".join(str(name).split())}" already exists in your library.'
            return
        spec = self._build_spec(name)
        if spec is None:
            return  # _build_spec already showed the overlap message
        # 先把本機關卡儲存（登入狀態下會同步到雲端），這樣社區上傳才有
        # 正確的 id 與最新內容；若該關卡已上傳過，save 也會同步更新社區。
        if not self._save(spec.name):
            return  # the name is taken: nothing is uploaded
        self.busy = True
        self.message = "Uploading to community..."

        def on_ok(_resp):
            self.busy = False
            self.message = "Uploaded to the community."
            self.uploaded = True        # worker thread: update() unlocks Signal Sent

        def on_err(exc):
            self.busy = False
            self.message = f"Upload failed: {exc}"

        from ..account import community

        community.upload_community_level(
            account, spec.name, community.serialize_level(spec),
            on_success=on_ok, on_error=on_err,
        )

    def draw(self, surface):
        surface.fill(config.BG)
        for i, kind in enumerate(self.palette):
            r = pygame.Rect(px(10), px(60 + i * 46), px(150), px(40))
            pygame.draw.rect(surface, config.PANEL_BG, r, border_radius=px(6))
            label = kind
            center = (r.centerx - px(40), r.centery)
            if kind == "start":
                img = load_image("ui.start_marker", size_px=(px(24), px(24)))
                if img is not None:
                    surface.blit(img, img.get_rect(center=center))
                else:
                    pygame.draw.circle(surface, (100, 200, 100), center, px(8))
            elif kind == "target":
                img = load_image("target.planet", size_px=(px(24), px(24)))
                if img is not None:
                    surface.blit(img, img.get_rect(center=center))
                else:
                    pygame.draw.circle(surface, (200, 100, 100), center, px(10))
            elif kind == "obstacle":
                img = load_image("obstacle.rock01", size_px=(px(24), px(24)))
                if img is not None:
                    surface.blit(img, img.get_rect(center=center))
                else:
                    sprites.draw_obstacle(surface, center, px(12), 0.0)
            elif kind in ("hole", "black_hole", "white_hole", "black", "white"):
                pygame.draw.circle(surface, (20, 20, 40), center, px(10))
                pygame.draw.circle(surface, (220, 220, 255), (center[0]+px(18), center[1]), px(10))
            else:
                pickup_key = {
                    "shockwave": "pickup.shockwave",
                    "extratime": "pickup.extratime",
                    "shield": "pickup.shield",
                    "life": "pickup.life",
                    "money": "pickup.money",
                    "unbound": "pickup.unbound",
                }.get(kind, "pickup.shockwave")
                img = load_image(pickup_key, size_px=(px(24), px(24)))
                if img is not None:
                    surface.blit(img, img.get_rect(center=center))
                else:
                    sprites.draw_pickup(surface, center, px(12), 0.0, kind=kind)
            draw_text(surface, label, (r.x + px(90), r.centery), 12, config.TEXT, anchor="midleft")
        self.back_button.draw(surface)
        self.save_button.draw(surface)
        self.upload_button.draw(surface)
        self.add_checkpoint_button.draw(surface)
        self.delete_checkpoint_button.draw(surface)
        self.prev_section_button.draw(surface)
        self.next_section_button.draw(surface)
        draw_text(surface, f"Section {self.section_index + 1} / {self.section_count}", (config.WINDOW_W // 2, px(58)), 16, config.TEXT, kind="bold", anchor="center")
        draw_text(surface, "Level Editor", (config.WINDOW_W // 2, px(30)), 24, config.TEXT, kind="bold", anchor="center")
        # Use viewport for world-to-screen conversion (same as gameplay)
        sx, sy = self.viewport.to_screen(*self.start)
        sprites.draw_start_marker(surface, (sx, sy), self.START_RADIUS * self.viewport.scale, 0.0)
        tx, ty = self.viewport.to_screen(*self.target)
        if self.section_count > 1 and self.section_index < self.section_count - 1:
            sprites.draw_checkpoint(surface, (tx, ty), self.target_radius * self.viewport.scale, 0.0)
        else:
            sprites.draw_target(surface, (tx, ty), self.target_radius * self.viewport.scale, 0.0)
        for i, o in enumerate(self.obstacles):
            ox, oy = self.viewport.to_screen(*o["center"])
            sprites.draw_obstacle(surface, (ox, oy), o["radius"] * self.viewport.scale, 0.0)
            if self.selected == ("obstacle", i):
                pygame.draw.circle(surface, config.ACCENT, (int(ox), int(oy)), int(o["radius"] * self.viewport.scale) + px(3), 1)
        for i, p in enumerate(self.pickups):
            px_, py_ = self.viewport.to_screen(*p["center"])
            sprites.draw_pickup(surface, (px_, py_), p["radius"] * self.viewport.scale, 0.0, kind=p["kind"])
            if self.selected == ("pickup", i):
                pygame.draw.circle(surface, config.ACCENT, (int(px_), int(py_)), int(p["radius"] * self.viewport.scale) + px(3), 1)
        for i, h in enumerate(self.holes):
            bc = self.viewport.to_screen(*h["black_center"])
            wc = self.viewport.to_screen(*h["white_center"])
            r = h["radius"] * self.viewport.scale
            sprites.draw_black_hole(surface, bc, r, 0.0)
            sprites.draw_white_hole(surface, wc, r, 0.0)
            if self.selected == ("hole", i):
                pygame.draw.circle(surface, config.ACCENT, (int(bc[0]), int(bc[1])), int(r)+px(3), 1)
                pygame.draw.circle(surface, config.ACCENT, (int(wc[0]), int(wc[1])), int(r)+px(3), 1)
        if self.selected == ("start", None):
            pygame.draw.circle(surface, config.ACCENT, (int(sx), int(sy)), int(self.START_RADIUS * self.viewport.scale) + px(3), 1)
        elif self.selected == ("target", None):
            pygame.draw.circle(surface, config.ACCENT, (int(tx), int(ty)), int(self.target_radius * self.viewport.scale) + px(3), 1)
        if self.dragging:
            mx, my = pygame.mouse.get_pos()
            draw_text(surface, self.dragging, (mx + 10, my + 10), 14, config.ACCENT)
        if self.naming:
            box = pygame.Rect(config.WINDOW_W // 2 - px(220), config.WINDOW_H - px(120), px(440), px(44))
            pygame.draw.rect(surface, config.PANEL_BG, box, border_radius=px(6))
            pygame.draw.rect(surface, config.ACCENT, box, width=2, border_radius=px(6))
            draw_text(surface, "Name: " + self.name_buffer + "_", (box.x + px(12), box.centery), 20, config.ACCENT, anchor="midleft")
        else:
            draw_text(surface, "Right-click an object: Delete / Modify | Drag to move | Wheel or +/- to resize",
                      (config.WINDOW_W // 2, config.WINDOW_H - px(28)), 13, config.TEXT_DIM, anchor="center")
        if self.message:
            draw_text(surface, self.message, (config.WINDOW_W // 2, config.WINDOW_H - px(48)), 14, config.ACCENT, anchor="center")
        if self.context_menu is not None:
            _, rect = self.context_menu
            pygame.draw.rect(surface, config.PANEL_BG, rect, border_radius=px(4))
            pygame.draw.rect(surface, config.ACCENT, rect, width=1, border_radius=px(4))
            draw_text(surface, "Delete", (rect.centerx, rect.y + rect.height // 4), 13, config.TEXT, anchor="center")
            draw_text(surface, "Modify", (rect.centerx, rect.y + rect.height * 3 // 4), 13, config.TEXT, anchor="center")
