"""Function Lab: write a force function, watch it act, name it, save it, import it.

The lab is a place of its own, opened from the level select.  The player
writes the two components of a force field (``Fx`` and ``Fy``), sees the field
it produces on a grid (with a probe particle tracing the path the ship would
take), gives it a name and saves it in the player's library.  A saved function
can be imported: the imported one is what the normal levels start with, and
the game screen's "Lab" button can load any of them into the editor.

Nothing here touches the game's flight or level code: the lab only reads and
writes the player's own library.
"""

import math

import pygame

from .. import config, render
from ..config import px
from ..coords import Viewport
from ..expr_parser import diagnose_expression
from ..function_library import (
    MAX_FUNCTIONS,
    MAX_NAME_LEN,
    SavedFunction,
    clean_name,
    make_function,
)
from ..physics import ForceField
from ..ui import Button, CodeEditor, TextInput, draw_text, fit_text, wrap_text
from .base import Scene

# --- layout (logical pixels, the 1280x720 base canvas) --------------------------
LEFT_X, LEFT_W = 24, 360            # the editing column
EDITOR_Y = 80                       # the code editor's top
NAME_LABEL_Y = 240                  # "NAME" above the name field
NAME_Y = 258                         # the name field and the Save button
NAME_W = 246
NEW_Y = 302                          # the New button
STATUS_Y = 344                       # the message under the buttons
HINT_Y = 440                         # the longer explanation
PLOT_X, PLOT_Y = 404, 80            # the field preview
PLOT_W, PLOT_H = 852, 330
LEGEND_TEXT_Y = 420                  # under the preview
LIST_HEADER_Y = 452                  # "SAVED FUNCTIONS"
ROWS_Y = 478                         # the first library row
ROW_H = 30
ROWS_PER_PAGE = 7
NAME_COL_X, NAME_COL_W = 404, 178    # the library columns
FX_COL_X, FX_COL_W = 590, 156
FY_COL_X, FY_COL_W = 754, 156
BTN_LOAD_X, BTN_LOAD_W = 1076, 72
BTN_IMPORT_X, BTN_IMPORT_W = 1154, 72
BTN_DEL_X, BTN_DEL_W = 1232, 24
PREV_X, PREV_W = 1110, 60            # the page arrows on the header line
NEXT_X, NEXT_W = 1176, 60
PAGE_TEXT_X = 996

# The probe: a 1 kg particle released on the map, integrated like the ship.
PROBE_MASS = 1.0
PROBE_START = (-6.0, 0.0)              # where the ship usually starts
PROBE_STEPS = 900                      # 7.5 s at the game's 1/120 s step
PROBE_LIMIT_M = 30.0                   # stop when it is this far out


class FunctionLabScene(Scene):
    """The Function Lab screen."""

    music = "menu"

    def __init__(self, manager):
        super().__init__(manager)
        self.background = render.make_space_background((config.WINDOW_W, config.WINDOW_H),
                                                       seed=9, star_count=200)
        self.editor = CodeEditor((px(LEFT_X), px(EDITOR_Y)), px(LEFT_W),
                                 title="Function", on_change=self._on_text_change)
        self.name_input = TextInput((px(LEFT_X), px(NAME_Y), px(NAME_W), px(34)),
                                    "Name this function", font_size=15,
                                    max_length=MAX_NAME_LEN)
        self.save_button = Button((px(LEFT_X + NAME_W + 8), px(NAME_Y),
                                   px(LEFT_W - NAME_W - 8), px(34)),
                                  "Save", style="primary", font_size=16)
        self.new_button = Button((px(LEFT_X), px(NEW_Y), px(110), px(30)), "New",
                                 style="plain", font_size=15)
        self.back_button = Button((px(40), config.WINDOW_H - px(86), px(180), px(46)), "Levels",
                                  style="plain", font_size=17)
        self.prev_button = Button((px(PREV_X), px(LIST_HEADER_Y - 8), px(PREV_W), px(26)), "‹",
                                  style="plain", font_size=15)
        self.next_button = Button((px(NEXT_X), px(LIST_HEADER_Y - 8), px(NEXT_W), px(26)), "›",
                                  style="plain", font_size=15)

        # The field preview: a viewport on the usual world, so the player sees
        # the same map the levels use.
        self.plot_rect = pygame.Rect(px(PLOT_X), px(PLOT_Y), px(PLOT_W), px(PLOT_H))
        scale = min(self.plot_rect.w / 20.0, self.plot_rect.h / 15.0)
        self.viewport = Viewport(rect=self.plot_rect, scale=scale)
        self.plot_background = render.make_plot_background(self.viewport)

        self.field = None
        self.field_layer = None
        self.max_force = 0.0
        self.probe = []
        self.valid = False
        self.editing_id = None         # the saved function being edited
        self.message = ""
        self.message_color = config.TEXT
        self.message_timer = 0.0
        self.page = 0
        self.page_count = 1
        self.rows = []
        self._validate()
        self._rebuild()

    # ------------------------------------------------------------------ library
    def _library(self):
        """The player's saved functions (SavedFunction objects)."""
        functions = []
        for item in getattr(self.session, "function_library", ()) or ():
            if isinstance(item, SavedFunction):
                functions.append(item)
            elif isinstance(item, dict):
                function = SavedFunction.from_row(item)
                if function is not None:
                    functions.append(function)
        return functions

    def _imported_id(self):
        return getattr(self.session, "imported_function_id", None)

    def _persist(self):
        """Keep the library in the player profile (local file and cloud)."""
        from ..account.integration import save_progress

        try:
            save_progress(self.manager.account, self.session)
        except Exception:               # noqa: BLE001 - saving must never break the lab
            pass

    def _say(self, text, color=None):
        self.message = text
        self.message_color = color or config.TEXT
        self.message_timer = 3.5

    # ------------------------------------------------------------------ preview
    def _on_text_change(self, editor):
        self._validate()

    def _validate(self):
        """Check the formulas and redraw the preview."""
        fx_text, fy_text = self.editor.lines
        fx, fx_err, fx_pos = diagnose_expression(fx_text)
        fy, fy_err, fy_pos = diagnose_expression(fy_text)
        self.editor.set_errors([
            (fx_err, fx_pos) if fx_err else None,
            (fy_err, fy_pos) if fy_err else None,
        ])
        self.valid = fx is not None and fy is not None
        self.field = None
        self.field_layer = None
        self.probe = []
        if not self.valid:
            return
        field = ForceField.from_exprs(fx, fy)
        try:
            layer, max_force = render.make_field_layer(self.viewport, field)
        except (ArithmeticError, ValueError, TypeError, OverflowError,
                RecursionError, MemoryError, pygame.error):
            # Syntactically fine, but it cannot be drawn (a pole in the grid).
            self.valid = False
            self.editor.set_errors([("Cannot be shown on the grid", 0), None])
            return
        self.field = field
        self.field_layer = layer
        self.max_force = max_force
        self.probe = self._trace_probe(field)

    def _trace_probe(self, field):
        """Trace a probe particle through the field (semi-implicit Euler)."""
        x, y = PROBE_START
        vx = vy = 0.0
        dt = config.DT
        points = []
        for _ in range(PROBE_STEPS):
            try:
                fx, fy = field.at(x, y)
            except (ArithmeticError, ValueError, TypeError, OverflowError,
                    RecursionError, MemoryError):
                break
            if not (math.isfinite(fx) and math.isfinite(fy)):
                break
            vx += (fx / PROBE_MASS) * dt
            vy += (fy / PROBE_MASS) * dt
            x += vx * dt
            y += vy * dt
            if not (math.isfinite(x) and math.isfinite(y)):
                break
            points.append((x, y))
            if abs(x) > PROBE_LIMIT_M or abs(y) > PROBE_LIMIT_M:
                break
        return points

    # ------------------------------------------------------------------ actions
    def _save(self):
        """Store the editor's formulas in the library (or update the loaded one)."""
        if not self.valid:
            self._say("Fix the formulas before saving.", config.WARNING)
            self.audio.play("error")
            return
        fx, fy = self.editor.lines
        name = clean_name(self.name_input.text)
        functions = self._library()
        if self.editing_id:
            updated, found = [], False
            for function in functions:
                if function.id == self.editing_id:
                    updated.append(SavedFunction(id=function.id, name=name, fx=fx, fy=fy))
                    found = True
                else:
                    updated.append(function)
            if found:
                self.session.function_library = updated
                self._say(f"Updated “{name}”.", config.SUCCESS)
                self._persist()
                self._rebuild()
                return
            self.editing_id = None
        if len(functions) >= MAX_FUNCTIONS:
            self._say(f"The library holds at most {MAX_FUNCTIONS} functions.",
                      config.WARNING)
            self.audio.play("error")
            return
        function = make_function(name, fx, fy)
        self.session.function_library = functions + [function]
        self.editing_id = function.id
        self._say(f"Saved “{function.name}”.", config.SUCCESS)
        self._persist()
        self._rebuild()

    def _new(self):
        """Start a new function: an empty editor and an empty name."""
        self.editor.set_lines(["", ""])
        self.name_input.set_text("")
        self.editing_id = None
        self._say("New function. Write Fx and Fy, then save it.", config.TEXT_DIM)

    def _load(self, function):
        """Put a saved function into the editor so it can be changed."""
        self.editor.set_lines([function.fx, function.fy])
        self.name_input.set_text(function.name)
        self.editing_id = function.id
        self._say(f"Loaded “{function.name}”. Change it and save to update.",
                  config.TEXT_DIM)

    def _import(self, function):
        """Make this the function the normal levels use."""
        self.session.imported_function_id = function.id
        self.editor.set_lines([function.fx, function.fy])
        self.name_input.set_text(function.name)
        self.editing_id = function.id
        self._say(f"Imported “{function.name}”. It is now used in the levels.",
                  config.SUCCESS)
        self._persist()
        self._rebuild()

    def _delete(self, function):
        """Remove a function from the library."""
        functions = [f for f in self._library() if f.id != function.id]
        self.session.function_library = functions
        if self._imported_id() == function.id:
            self.session.imported_function_id = None
        if self.editing_id == function.id:
            self.editing_id = None
        self._say(f"Deleted “{function.name}”.", config.TEXT_DIM)
        self._persist()
        self._rebuild()

    def _to_levels(self):
        self.audio.play("click")
        from .levels import LevelSelectScene
        self.manager.switch(LevelSelectScene(self.manager))

    # ------------------------------------------------------------------ input
    def handle_event(self, event):
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self._to_levels()
            return
        # The name field and the code editor share the keyboard: only the
        # focused one gets the text.
        self.name_input.handle_event(event)
        if self.name_input.active:
            if event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP,
                              pygame.MOUSEMOTION):
                self.editor.handle_event(event)
        elif self.editor.handle_event(event):
            return
        if self.save_button.handle_event(event) == "click":
            self._save()
            return
        if self.new_button.handle_event(event) == "click":
            self._new()
            return
        if self.back_button.handle_event(event) == "click":
            self._to_levels()
            return
        if self.prev_button.handle_event(event) == "click":
            self.page -= 1
            self._rebuild()
            return
        if self.next_button.handle_event(event) == "click":
            self.page += 1
            self._rebuild()
            return
        for function, _rect, buttons in self.rows:
            if buttons["load"].handle_event(event) == "click":
                self._load(function)
                return
            if buttons["import"].handle_event(event) == "click":
                self._import(function)
                return
            if buttons["delete"].handle_event(event) == "click":
                self._delete(function)
                return

    def update(self, dt):
        self.editor.update(dt)
        if self.message_timer > 0:
            self.message_timer -= dt
            if self.message_timer <= 0:
                self.message = ""

    # ------------------------------------------------------------------ drawing
    def _rebuild(self):
        """The visible library rows (one page of them)."""
        functions = self._library()
        self.page_count = max(1, -(-len(functions) // ROWS_PER_PAGE))
        self.page = max(0, min(self.page, self.page_count - 1))
        start = self.page * ROWS_PER_PAGE
        self.rows = []
        y = ROWS_Y
        for function in functions[start:start + ROWS_PER_PAGE]:
            rect = pygame.Rect(px(PLOT_X), px(y), px(PLOT_W), px(ROW_H) - px(4))
            buttons = {
                "load": Button(pygame.Rect(px(BTN_LOAD_X), px(y + 4), px(BTN_LOAD_W),
                                           px(ROW_H) - px(12)), "Load", style="plain",
                               font_size=13),
                "import": Button(pygame.Rect(px(BTN_IMPORT_X), px(y + 4), px(BTN_IMPORT_W),
                                             px(ROW_H) - px(12)), "Import", style="plain",
                                 font_size=13),
                "delete": Button(pygame.Rect(px(BTN_DEL_X), px(y + 4), px(BTN_DEL_W),
                                             px(ROW_H) - px(12)), "×", style="plain",
                                 font_size=13),
            }
            self.rows.append((function, rect, buttons))
            y += ROW_H
        self.prev_button.enabled = self.page > 0
        self.next_button.enabled = self.page < self.page_count - 1

    def _draw_plot(self, surface):
        vp = self.viewport
        surface.blit(self.plot_background, (vp.left, vp.top))
        if self.field_layer is not None:
            surface.blit(self.field_layer, (vp.left, vp.top))
        if self.probe:
            points = [vp.to_screen(x, y) for x, y in self.probe]
            # The probe may leave the map: keep its trail inside the preview.
            previous_clip = surface.get_clip()
            surface.set_clip(self.plot_rect)
            try:
                if len(points) > 1:
                    pygame.draw.lines(surface, config.TRAIL, False, points, max(1, px(2)))
                pygame.draw.circle(surface, config.SUCCESS, points[0], px(4))
                pygame.draw.circle(surface, config.ACCENT, points[-1], px(4))
            finally:
                surface.set_clip(previous_clip)
        pygame.draw.rect(surface, config.PANEL_EDGE, self.plot_rect,
                         max(1, px(1)), border_radius=px(4))
        render.draw_legend(surface, (self.plot_rect.centerx, self.plot_rect.bottom - px(16)),
                           self.max_force)

    def _draw_library(self, surface):
        functions = self._library()
        draw_text(surface, "SAVED FUNCTIONS", (px(PLOT_X), px(LIST_HEADER_Y)), 14,
                  config.TEXT, kind="bold")
        draw_text(surface, f"{len(functions)} / {MAX_FUNCTIONS}", (px(PLOT_X + 210),
                  px(LIST_HEADER_Y)), 13, config.TEXT_DIM)
        if not functions:
            draw_text(surface, "No functions yet — write one and press Save.",
                      (px(PLOT_X), px(ROWS_Y + 6)), 14, config.TEXT_DIM)
            return
        imported = self._imported_id()
        for function, rect, buttons in self.rows:
            hovered = rect.collidepoint(pygame.mouse.get_pos())
            pygame.draw.rect(surface, config.EDITOR_LINE_HL if hovered else config.PANEL_BG,
                             rect, border_radius=px(4))
            name_color = config.ACCENT if function.id == imported else config.TEXT
            draw_text(surface, fit_text(function.name, px(NAME_COL_W - 8), 15, "bold"),
                      (px(NAME_COL_X) + px(6), rect.centery), 15, name_color,
                      kind="bold", anchor="midleft")
            if function.id == imported:
                draw_text(surface, "in use", (px(NAME_COL_X + NAME_COL_W - 4), rect.centery),
                          11, config.ACCENT, anchor="midright")
            draw_text(surface, fit_text(function.fx or "-", px(FX_COL_W - 8), 13, "mono"),
                      (px(FX_COL_X), rect.centery), 13, config.TEXT_DIM, kind="mono",
                      anchor="midleft")
            draw_text(surface, fit_text(function.fy or "-", px(FY_COL_W - 8), 13, "mono"),
                      (px(FY_COL_X), rect.centery), 13, config.TEXT_DIM, kind="mono",
                      anchor="midleft")
            for button in buttons.values():
                button.draw(surface)
        if self.page_count > 1:
            self.prev_button.draw(surface)
            self.next_button.draw(surface)
            draw_text(surface, f"Page {self.page + 1} / {self.page_count}",
                      (px(PAGE_TEXT_X), px(LIST_HEADER_Y - 8)), 12, config.TEXT_DIM)

    def draw(self, surface):
        surface.blit(self.background, (0, 0))
        draw_text(surface, "FUNCTION LAB", (px(LEFT_X), px(24)), 26, config.TEXT, kind="bold")
        draw_text(surface, "Write a force function, watch it act, name it and save it.",
                  (px(LEFT_X), px(54)), 14, config.TEXT_DIM)
        self.editor.draw(surface)
        draw_text(surface, "NAME", (px(LEFT_X), px(NAME_LABEL_Y)), 12, config.TEXT_DIM,
                  kind="bold")
        self.name_input.draw(surface)
        self.save_button.label = "Update" if self.editing_id else "Save"
        self.save_button.draw(surface)
        self.new_button.draw(surface)
        self.back_button.draw(surface)
        self._draw_plot(surface)

        probe_text = "Probe: a 1 kg particle released at (-6, 0) m."
        if self.probe:
            end = self.probe[-1]
            probe_text += f"  It ended at ({end[0]:.2f}, {end[1]:.2f}) m."
        elif self.valid:
            probe_text += "  It does not move (no force)."
        draw_text(surface, probe_text, (px(PLOT_X), px(LEGEND_TEXT_Y)), 13, config.TEXT_DIM)
        self._draw_library(surface)

        if self.message:
            for i, line in enumerate(wrap_text(self.message, 13, px(LEFT_W))[:3]):
                draw_text(surface, line, (px(LEFT_X), px(STATUS_Y + i * 18)), 13,
                          self.message_color)
        hint = ("Import a function to use it in the normal levels: the editor "
                "starts with it, and the game screen's Lab button loads any "
                "saved function.")
        for i, line in enumerate(wrap_text(hint, 13, px(LEFT_W))[:6]):
            draw_text(surface, line, (px(LEFT_X), px(HINT_Y + i * 18)), 13, config.TEXT_FAINT)


# Aliases (the scene is reachable under a few names in tests and scripts).
FunctionLab = FunctionLabScene
LabScene = FunctionLabScene
