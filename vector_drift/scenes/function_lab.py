"""Function Lab: write a force function, watch it act, name it, save it, import it.

The lab is a place of its own, opened from the level select.  The player
writes the two components of a force field (``Fx`` and ``Fy``), sees the field
it produces on a grid (with a probe particle tracing the path the ship would
take), gives it a name and saves it in the player's library.  A saved function
can be imported: the imported one is what the normal levels start with, and
the game screen's "Lab" button can load any of them into the editor.

The point where the probe is released is the player's choice: it is written in
the two coordinate fields (or picked with a click on the preview), so a field
can be watched from any place on the map.

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
    clean_description,
    clean_name,
    find_function,
    make_function,
    name_taken,
)
from ..community_function_browse import (
    MAX_DESCRIPTION_LEN,
    MAX_TAG_LEN,
    parse_tags,
    tags_to_text,
    MAX_TAGS,
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
START_LABEL_Y = 340                 # "PROBE START" above the coordinate fields
START_Y = 358                        # the coordinate fields and the Reset button
START_FIELD_W = 118                  # one coordinate field
START_X_LABEL_X = LEFT_X             # the "x" and "y" labels
START_X_FIELD_X = LEFT_X + 14
START_Y_LABEL_X = LEFT_X + 138
START_Y_FIELD_X = LEFT_X + 152
START_RESET_X = LEFT_X + 276
START_RESET_W = 84
DESC_LABEL_Y = 398                   # "DESCRIPTION" above the description field
DESC_Y = 414                         # the description field
TAGS_LABEL_Y = 450                   # "TAGS" above the tags field
TAGS_Y = 466                         # the tags field
STATUS_Y = 504                       # the message under the buttons
HINT_Y = 562                         # the longer explanation
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
START_MARGIN_M = 0.25                  # the start marker stays inside the preview
MAX_COORD_LEN = 12                     # characters in a coordinate field


def _parse_coordinate(text):
    """The number written in a coordinate field, or None when it is not one.

    Plain decimal numbers only (an optional minus sign, digits, a dot).  A
    unicode minus (some keyboards type one) is understood.
    """
    if not isinstance(text, str):
        return None
    cleaned = text.strip().replace("\u2212", "-")
    if not cleaned:
        return None
    try:
        value = float(cleaned)
    except ValueError:
        return None
    if not math.isfinite(value):
        return None
    return value


def _format_coordinate(value):
    """A coordinate as short text: "-6", "0", "1.5"."""
    try:
        value = float(value)
    except (TypeError, ValueError):
        return "0"
    if not math.isfinite(value):
        return "0"
    if value == int(value):
        return str(int(value))
    return f"{value:g}"


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
        self.upload_button = Button((px(LEFT_X + 250), px(NEW_Y), px(110), px(30)),
                                    "Upload", style="primary", font_size=14)
        self.new_button = Button((px(LEFT_X), px(NEW_Y), px(70), px(30)), "New",
                                 style="plain", font_size=15)
        # Where the probe is released: the player's choice, in metres.
        self.start_x_input = TextInput((px(START_X_FIELD_X), px(START_Y),
                                        px(START_FIELD_W), px(34)),
                                       "x (m)", font_size=15,
                                       max_length=MAX_COORD_LEN,
                                       on_change=self._on_start_change)
        self.start_y_input = TextInput((px(START_Y_FIELD_X), px(START_Y),
                                        px(START_FIELD_W), px(34)),
                                       "y (m)", font_size=15,
                                       max_length=MAX_COORD_LEN,
                                       on_change=self._on_start_change)
        self.start_reset_button = Button((px(START_RESET_X), px(START_Y + 2),
                                          px(START_RESET_W), px(30)),
                                         "Reset", style="plain", font_size=14)
        self.desc_input = TextInput((px(LEFT_X), px(DESC_Y), px(LEFT_W), px(30)),
                                    "Describe this function (shown in the community)",
                                    font_size=13, max_length=MAX_DESCRIPTION_LEN)
        self.tags_input = TextInput((px(LEFT_X), px(TAGS_Y), px(LEFT_W), px(30)),
                                    "tags, comma separated", font_size=13,
                                    max_length=MAX_TAG_LEN * (MAX_TAGS + 1))
        self.back_button = Button((px(40), config.WINDOW_H - px(86), px(180), px(46)), "Levels",
                                  style="plain", font_size=17)
        self.community_button = Button((px(LEFT_X + 80), px(NEW_Y), px(160), px(30)), "Public Functions",
                                       style="plain", font_size=14)
        self.public_button = self.community_button
        self.public_functions_button = self.community_button
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
        self.busy = False
        self.page = 0
        self.page_count = 1
        self.rows = []
        # The probe's start point: the fields are the truth, these are the
        # last values that were read from them.
        self.start_x, self.start_y = PROBE_START
        self.start_error = {}          # the fields that hold no usable number
        self.start_message = None      # the last complaint about the start
        self._validate()
        self._rebuild()
        self.start_x_input.set_text(_format_coordinate(self.start_x))
        self.start_y_input.set_text(_format_coordinate(self.start_y))

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

    def _start_limits(self):
        """The largest start point the preview can show (metres)."""
        return (max(0.0, self.viewport.half_w - START_MARGIN_M),
                max(0.0, self.viewport.half_h - START_MARGIN_M))

    def _on_start_change(self, _text=None):
        """A coordinate field changed: read both and trace the probe again.

        A field that holds no number (or one outside the preview) keeps its
        last good value: the probe stays where it was until the entry is
        fixed, and the offending field is marked.
        """
        limit_x, limit_y = self._start_limits()
        values = {"x": _parse_coordinate(self.start_x_input.text),
                  "y": _parse_coordinate(self.start_y_input.text)}
        limits = {"x": limit_x, "y": limit_y}
        problems = {}
        for name, value in values.items():
            if value is None:
                problems[name] = "number"
            elif abs(value) > limits[name]:
                problems[name] = "range"
        if problems:
            self.start_error = problems
            kinds = {kind for kind in problems.values()}
            if kinds == {"number"}:
                text = "The start point must be a number (metres)."
            elif kinds == {"range"}:
                text = (f"The start point must stay inside the preview "
                        f"(x within ±{limit_x:.1f} m, y within ±{limit_y:.1f} m).")
            else:
                text = "The start point must be a number inside the preview."
            self.start_message = text
            self._say(text, config.WARNING)
            return
        self.start_error = {}
        if self.message == self.start_message:
            # The complaint about the start point is over.
            self.message = ""
            self.message_timer = 0.0
        x, y = values["x"], values["y"]
        if (x, y) != (self.start_x, self.start_y):
            self.start_x, self.start_y = x, y
            self._retrace()

    def _retrace(self):
        """Trace the probe again from the current start point."""
        self.probe = self._trace_probe(self.field) if self.field is not None else []

    def _no_probe_reason(self):
        """Why the probe is not on the map (the start point is unusable)."""
        if self.field is None:
            return "  It does not move."
        try:
            fx, fy = self.field.at(self.start_x, self.start_y)
        except (ArithmeticError, ValueError, TypeError, OverflowError,
                RecursionError, MemoryError):
            return "  The force cannot be used at that point."
        if not (math.isfinite(fx) and math.isfinite(fy)):
            return "  The force cannot be used at that point."
        return "  It does not move."

    def _reset_start(self):
        """Put the probe back to the default start point."""
        self.start_message = None
        self.start_x_input.set_text(_format_coordinate(PROBE_START[0]))
        self.start_y_input.set_text(_format_coordinate(PROBE_START[1]))
        self.start_error = {}
        self._retrace()
        self._say(f"Start point back at ({_format_coordinate(PROBE_START[0])}, "
                  f"{_format_coordinate(PROBE_START[1])}) m.", config.TEXT_DIM)

    def _set_start_from_preview(self, pos):
        """Release the probe where the player clicked in the preview."""
        if not self.plot_rect.collidepoint(pos):
            return
        x, y = self.viewport.to_world(*pos)
        limit_x, limit_y = self._start_limits()
        x = max(-limit_x, min(limit_x, x))
        y = max(-limit_y, min(limit_y, y))
        self.start_x_input.set_text(_format_coordinate(x))
        self.start_y_input.set_text(_format_coordinate(y))
        self._retrace()

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
        from ..function_preview import trace_probe

        return trace_probe(field, (self.start_x, self.start_y),
                           steps=PROBE_STEPS, limit_m=PROBE_LIMIT_M)

    # ------------------------------------------------------------------ actions
    def _save(self):
        """Store the editor's formulas in the library (or update the loaded one).

        Returns True when the function was saved, False otherwise.
        """
        if not self.valid:
            self._say("Fix the formulas before saving.", config.WARNING)
            self.audio.play("error")
            return False
        fx, fy = self.editor.lines
        name = clean_name(self.name_input.text)
        description = clean_description(self.desc_input.text)
        tags = parse_tags(self.tags_input.text)
        functions = self._library()
        # --- name conflicts (one player, one name) --------------------------
        # The player may never end up with two functions under the same
        # name; the loaded function is not a conflict with itself.
        if name_taken(name, functions, exclude_id=self.editing_id):
            self._say(f"A function called “{name}” already exists in your library.",
                      config.WARNING)
            self.audio.play("error")
            return False
        saved = None
        if self.editing_id:
            updated, found = [], False
            for function in functions:
                if function.id == self.editing_id:
                    saved = SavedFunction(id=function.id, name=name, fx=fx, fy=fy,
                                          description=description, tags=tags,
                                          source=function.source,
                                          community_id=function.community_id)
                    updated.append(saved)
                    found = True
                else:
                    updated.append(function)
            if found:
                self.session.function_library = updated
                self._say(f"Updated “{name}”.", config.SUCCESS)
            else:
                self.editing_id = None
        if saved is None:
            if len(functions) >= MAX_FUNCTIONS:
                self._say(f"The library holds at most {MAX_FUNCTIONS} functions.",
                          config.WARNING)
                self.audio.play("error")
                return False
            saved = make_function(name, fx, fy, description=description, tags=tags)
            self.session.function_library = functions + [saved]
            self.editing_id = saved.id
            self._say(f"Saved “{saved.name}”.", config.SUCCESS)
        self._persist()
        self._rebuild()
        # Publishing is one thing, staying in sync is another: saving a
        # local function that came from (or went to) the community also
        # refreshes the published copy.
        self._sync_community_copy(saved)
        return True

    def _sync_community_copy(self, function):
        """Push a local save of a published function to its community copy."""
        community_id = getattr(function, "community_id", None)
        if not community_id:
            return
        account = self.manager.account
        if account is None or not account.is_authenticated():
            return
        try:
            from ..account import community
            community.update_community_function(
                str(community_id), account,
                function_name=function.name, fx=function.fx, fy=function.fy,
                description=function.description, tags=function.tags,
                on_error=lambda exc: self._say(
                    f"Saved locally; the community copy could not be updated: {exc}",
                    config.WARNING),
            )
        except Exception:  # noqa: BLE001 - the local save must never block on the network
            pass

    def _try_upload(self):
        """Upload the current function to the public community table."""
        account = self.manager.account
        if account is None or not getattr(account, "is_configured", lambda: True)():
            self._say("Supabase is not configured.", config.WARNING)
            return
        if account is None or not account.is_authenticated() or account.current_user is None:
            self._say("Please log in to upload.", config.WARNING)
            return
        if self.busy:
            return
        if not self.valid:
            self._say("Fix the formulas before uploading.", config.WARNING)
            self.audio.play("error")
            return
        # Store locally first (the levels work the same way): the library
        # then carries the id the community copy is linked to.
        if not self._save():
            return  # the formulas are invalid or the name is taken
        fx, fy = self.editor.lines
        name = clean_name(self.name_input.text)
        description = clean_description(self.desc_input.text)
        tags = parse_tags(self.tags_input.text)
        current = find_function(self._library(), self.editing_id) if self.editing_id else None
        self.busy = True
        self._say("Uploading to community...", config.TEXT_DIM)

        def on_ok(_resp=None):
            self.busy = False
            self._say("Uploaded to the community.", config.SUCCESS)
            self._link_community_row(_resp)

        def on_err(exc):
            self.busy = False
            self._say(f"Upload failed: {exc}", config.WARNING)

        from ..account import community
        community.upload_community_function(
            account,
            function_name=name, fx=fx, fy=fy,
            description=description, tags=tags,
            community_id=(current.community_id if current else None),
            on_success=on_ok, on_error=on_err)

    def _link_community_row(self, resp):
        """Attach the id of the freshly uploaded community row to the local
        function, so later local saves and deletes stay in sync with it."""
        row_id = None
        try:
            data = getattr(resp, "data", None)
            if isinstance(data, (list, tuple)) and data and isinstance(data[0], dict):
                row_id = str(data[0].get("id") or "") or None
        except Exception:  # noqa: BLE001 - a missing id only means no future sync
            row_id = None
        if not row_id or not self.editing_id:
            return
        functions = self._library()
        updated = []
        for function in functions:
            if function.id == self.editing_id and function.community_id != row_id:
                updated.append(SavedFunction(id=function.id, name=function.name,
                                             fx=function.fx, fy=function.fy,
                                             description=function.description,
                                             tags=function.tags,
                                             source=function.source,
                                             community_id=row_id))
            else:
                updated.append(function)
        self.session.function_library = updated
        self._persist()

    def _new(self):
        """Start a new function: an empty editor and an empty name."""
        self.editor.set_lines(["", ""])
        self.name_input.set_text("")
        self.desc_input.set_text("")
        self.tags_input.set_text("")
        self.editing_id = None
        self._say("New function. Write Fx and Fy, then save it.", config.TEXT_DIM)

    def _load(self, function):
        """Put a saved function into the editor so it can be changed."""
        self.editor.set_lines([function.fx, function.fy])
        self.name_input.set_text(function.name)
        self.desc_input.set_text(getattr(function, "description", "") or "")
        self.tags_input.set_text(tags_to_text(getattr(function, "tags", ()) or ()))
        self.editing_id = function.id
        origin = " from the community" if getattr(function, "community_id", None) else ""
        self._say(f"Loaded “{function.name}”{origin}. Change it and save to update.",
                  config.TEXT_DIM)

    def _import(self, function):
        """Make this the function the normal levels use."""
        self.session.imported_function_id = function.id
        self.editor.set_lines([function.fx, function.fy])
        self.name_input.set_text(function.name)
        self.desc_input.set_text(getattr(function, "description", "") or "")
        self.tags_input.set_text(tags_to_text(getattr(function, "tags", ()) or ()))
        self.editing_id = function.id
        self._say(f"Imported “{function.name}”. It is now used in the levels.",
                  config.SUCCESS)
        self._persist()
        self._rebuild()

    def _delete(self, function):
        """Remove a function from the library (and from the community).

        When the function was published, the community copy is removed with
        it — the same behaviour the custom levels have.
        """
        functions = [f for f in self._library() if f.id != function.id]
        self.session.function_library = functions
        if self._imported_id() == function.id:
            self.session.imported_function_id = None
        if self.editing_id == function.id:
            self.editing_id = None
        self._say(f"Deleted “{function.name}”.", config.TEXT_DIM)
        self._persist()
        self._rebuild()
        community_id = getattr(function, "community_id", None)
        account = self.manager.account
        if community_id and account is not None and account.is_authenticated():
            try:
                from ..account import community
                community.delete_community_function(
                    function_id=community_id, account=account,
                    on_error=lambda exc: self._say(
                        f"Deleted locally; the community copy could not be removed: {exc}",
                        config.WARNING))
            except Exception:  # noqa: BLE001 - the local delete must never block
                pass

    def _to_levels(self):
        self.audio.play("click")
        from .levels import LevelSelectScene
        self.manager.switch(LevelSelectScene(self.manager))

    # ------------------------------------------------------------------ input
    def _text_field_active(self):
        """True when one of the lab's text fields has the keyboard."""
        return (self.name_input.active or self.start_x_input.active
                or self.start_y_input.active
                or self.desc_input.active or self.tags_input.active)

    def handle_event(self, event):
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self._to_levels()
            return
        # The name field, the two coordinate fields, the description and the
        # tags share the keyboard: only the focused one gets the text.
        self.name_input.handle_event(event)
        self.start_x_input.handle_event(event)
        self.start_y_input.handle_event(event)
        self.desc_input.handle_event(event)
        self.tags_input.handle_event(event)
        if self._text_field_active():
            if event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP,
                              pygame.MOUSEMOTION):
                self.editor.handle_event(event)
        elif self.editor.handle_event(event):
            return
        if self.save_button.handle_event(event) == "click":
            self._save()
            return
        if self.upload_button.handle_event(event) == "click":
            self._try_upload()
            return
        if self.new_button.handle_event(event) == "click":
            self._new()
            return
        if self.community_button.handle_event(event) == "click":
            self.audio.play("click")
            from .community import open_community
            open_community(self.manager, "functions", back_to=FunctionLabScene)
            return
        if self.start_reset_button.handle_event(event) == "click":
            self._reset_start()
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
        if (event.type == pygame.MOUSEBUTTONDOWN and event.button == 1
                and self.plot_rect.collidepoint(event.pos)):
            # A click on the preview releases the probe there.
            self._set_start_from_preview(event.pos)
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

    def _draw_start_fields(self, surface):
        """The probe's start point: the two coordinate fields and the Reset."""
        draw_text(surface, "PROBE START", (px(LEFT_X), px(START_LABEL_Y)), 12,
                  config.TEXT_DIM, kind="bold")
        draw_text(surface, "x", (px(START_X_LABEL_X), px(START_Y + 17)), 13,
                  config.TEXT_DIM, anchor="midleft")
        draw_text(surface, "y", (px(START_Y_LABEL_X), px(START_Y + 17)), 13,
                  config.TEXT_DIM, anchor="midleft")
        self.start_x_input.draw(surface)
        self.start_y_input.draw(surface)
        self.start_reset_button.draw(surface)
        # A field that holds no usable number is marked.
        for name, field in (("x", self.start_x_input), ("y", self.start_y_input)):
            if name in self.start_error:
                pygame.draw.rect(surface, config.DANGER, field.rect,
                                 width=max(1, px(1)), border_radius=px(4))

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
        self.community_button.draw(surface)
        self.upload_button.draw(surface)
        self._draw_start_fields(surface)
        self.back_button.draw(surface)
        draw_text(surface, "DESCRIPTION", (px(LEFT_X), px(DESC_LABEL_Y)), 12,
                  config.TEXT_DIM, kind="bold")
        self.desc_input.draw(surface)
        draw_text(surface, "TAGS", (px(LEFT_X), px(TAGS_LABEL_Y)), 12,
                  config.TEXT_DIM, kind="bold")
        self.tags_input.draw(surface)
        self._draw_plot(surface)

        probe_text = (f"Probe: a 1 kg particle released at "
                      f"({_format_coordinate(self.start_x)}, "
                      f"{_format_coordinate(self.start_y)}) m.")
        if self.probe:
            end = self.probe[-1]
            probe_text += f"  It ended at ({end[0]:.2f}, {end[1]:.2f}) m."
        elif self.valid:
            probe_text += self._no_probe_reason()
        draw_text(surface, probe_text, (px(PLOT_X), px(LEGEND_TEXT_Y)), 13, config.TEXT_DIM)
        self._draw_library(surface)

        if self.message:
            for i, line in enumerate(wrap_text(self.message, 13, px(LEFT_W))[:3]):
                draw_text(surface, line, (px(LEFT_X), px(STATUS_Y + i * 18)), 13,
                          self.message_color)
        hint = ("The probe's start point is yours to choose: write it in the two "
                "coordinate fields or click the preview. "
                "Import a function to use it in the normal levels: the editor "
                "starts with it, and the game screen's Lab button loads any "
                "saved function.")
        for i, line in enumerate(wrap_text(hint, 13, px(LEFT_W))[:6]):
            draw_text(surface, line, (px(LEFT_X), px(HINT_Y + i * 18)), 13, config.TEXT_FAINT)


# Aliases (the scene is reachable under a few names in tests and scripts).
FunctionLab = FunctionLabScene
LabScene = FunctionLabScene
