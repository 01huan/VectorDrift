"""Intro story: the six panels in intro_story.toml and the screen that plays them."""
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pygame
import pytest

from vector_drift import config, image_assets
from vector_drift import intro_story
from vector_drift.image_assets import AssetSpec
from vector_drift.scenes import story as story_module
from vector_drift.scenes.base import SceneManager
from vector_drift.scenes.story import StoryScene
from vector_drift.scenes.tutorial_screen import TutorialScene

pytestmark = pytest.mark.usefixtures("pygame_display")


# --- the data ---------------------------------------------------------------------

def test_story_has_six_panels_with_every_field():
    panels = intro_story.load_story()
    assert len(panels) == 6
    for n, panel in enumerate(panels, start=1):
        assert panel.image == f"story.panel{n}"
        assert panel.scene.startswith("[") and panel.scene.endswith("]")
        assert panel.speaker in ("SHIP", "")
        assert panel.line


def test_story_text_is_the_script():
    panels = intro_story.load_story()
    assert [p.speaker for p in panels] == ["SHIP", "SHIP", "SHIP", "", "SHIP", "SHIP"]
    assert panels[0].line == "Main engine offline. Fuel: zero."
    assert panels[2].line == "Broadcasting on all frequencies… Can anyone hear me?"
    assert panels[3].line == ("Someone answers. Not a ship. Not a station. "
                              "The one who shapes space itself.")
    assert panels[5].line == "I can't move on my own. Write the field, Architect. Guide me home."
    assert panels[4].scene.startswith("[Back at the rocket. The grid lines around it bend")


def test_story_images_are_registered_like_the_other_pictures():
    for n in range(1, 7):
        spec = image_assets.get_spec(f"story.panel{n}")
        assert spec is not None
        assert spec.path == Path(f"story/panel{n}.png")


def test_the_story_pictures_are_in_and_about_16_by_9():
    image_assets.clear_cache()
    try:
        for n in range(1, 7):
            key = f"story.panel{n}"
            image = image_assets.load_image(key)
            assert image is not None, key
            w, h = image.get_size()
            assert abs((w / h) / (16 / 9) - 1) <= 0.01, (key, w, h)
    finally:
        image_assets.clear_cache()


@pytest.mark.parametrize("missing", ["image", "scene", "speaker", "line"])
def test_a_panel_without_a_field_is_rejected(tmp_path, missing):
    fields = {"image": "story.panel1", "scene": "[x]", "speaker": "", "line": "y"}
    del fields[missing]
    path = tmp_path / "story.toml"
    path.write_text("[[panel]]\n" + "".join(f'{k} = "{v}"\n' for k, v in fields.items()),
                    encoding="utf-8")
    with pytest.raises(intro_story.StoryFormatError, match=missing):
        intro_story.load_story(path)


def test_a_story_without_panels_is_rejected(tmp_path):
    path = tmp_path / "story.toml"
    path.write_text("", encoding="utf-8")
    with pytest.raises(intro_story.StoryFormatError):
        intro_story.load_story(path)


# --- the player ----------------------------------------------------------------------

class Audio:
    def __init__(self, music_paths=None):
        self.music_paths = dict(music_paths or {})
        self.music_asked = []

    def play(self, *a, **k):
        pass

    def set_music(self, name):
        self.music_asked.append(name)

    def start_loop(self, *a, **k):
        pass

    def stop_loop(self, *a, **k):
        pass

    def toggle_mute(self):
        pass


@pytest.fixture
def no_pictures(tmp_path, monkeypatch):
    """No story pictures exist: images are looked up in an empty temporary folder."""
    monkeypatch.setattr(image_assets, "IMAGES_DIR", tmp_path)
    image_assets.clear_cache()
    yield tmp_path
    image_assets.clear_cache()


def _story(audio=None):
    manager = SceneManager(audio or Audio())
    scene = StoryScene(manager)
    manager.switch(scene)
    return scene


def _settle(scene):
    """Let any fade and typing finish, so the panel is fully shown."""
    for _ in range(4):
        scene.update(1.0)


def _key(scene, key):
    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key, mod=0, unicode="", scancode=0))


def _click(scene, pos):
    scene.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=pos))


def _next(scene):
    _settle(scene)
    _key(scene, pygame.K_SPACE)
    _settle(scene)


def test_story_starts_on_the_first_panel_and_counts_them():
    scene = _story()
    assert scene.index == 0
    assert scene.counter_text == "1 / 6"


@pytest.mark.parametrize("key", [pygame.K_SPACE, pygame.K_RIGHT])
def test_space_and_right_arrow_go_to_the_next_panel(key):
    scene = _story()
    _settle(scene)
    _key(scene, key)
    _settle(scene)
    assert scene.index == 1
    assert scene.counter_text == "2 / 6"


def test_a_click_goes_to_the_next_panel():
    scene = _story()
    _settle(scene)
    _click(scene, (config.WINDOW_W // 2, config.WINDOW_H // 3))
    _settle(scene)
    assert scene.index == 1


def test_left_arrow_goes_back_one_panel():
    scene = _story()
    _next(scene)
    _next(scene)
    assert scene.index == 2
    _key(scene, pygame.K_LEFT)
    _settle(scene)
    assert scene.index == 1


def test_left_arrow_on_the_first_panel_does_nothing():
    scene = _story()
    _settle(scene)
    _key(scene, pygame.K_LEFT)
    _settle(scene)
    assert scene.index == 0
    assert scene.manager.scene is scene


def test_next_on_the_last_panel_ends_the_first_story_at_basics():
    scene = _story()
    for _ in range(5):
        _next(scene)
    assert scene.index == 5 and scene.counter_text == "6 / 6"
    _key(scene, pygame.K_SPACE)
    assert isinstance(scene.manager.scene, TutorialScene)


def test_skip_button_ends_the_first_story_at_basics():
    scene = _story()
    _next(scene)
    _click(scene, scene.skip_button.rect.center)
    assert isinstance(scene.manager.scene, TutorialScene)


def test_escape_ends_the_first_story_at_basics():
    scene = _story()
    _key(scene, pygame.K_ESCAPE)
    assert isinstance(scene.manager.scene, TutorialScene)


def test_skip_click_does_not_also_count_as_next():
    scene = _story()
    _settle(scene)
    index = scene.index
    _click(scene, scene.skip_button.rect.center)
    assert scene.index == index


def test_where_the_story_ends_is_decided_in_one_place(monkeypatch):
    marker = SimpleNamespace(music=None)
    monkeypatch.setattr(story_module, "scene_after_story", lambda manager: marker)
    scene = _story()
    _key(scene, pygame.K_ESCAPE)
    assert scene.manager.scene is marker


def test_scene_after_the_story_is_the_tutorial_screen():
    manager = SceneManager(Audio())
    after = story_module.scene_after_story(manager)
    assert isinstance(after, TutorialScene) and after.inner.index == 0


@pytest.mark.parametrize("how", ["played through", "skip", "esc"])
def test_every_way_out_of_the_story_goes_to_the_same_place(monkeypatch, how):
    marker = SimpleNamespace(music=None)
    monkeypatch.setattr(story_module, "scene_after_story", lambda manager: marker)
    scene = _story()
    if how == "played through":
        for _ in range(5):
            _next(scene)
        _key(scene, pygame.K_SPACE)
    elif how == "skip":
        _click(scene, scene.skip_button.rect.center)
    else:
        _key(scene, pygame.K_ESCAPE)
    assert scene.manager.scene is marker


def test_a_story_takes_no_other_end():
    import inspect
    assert "after" not in inspect.signature(StoryScene.__init__).parameters


# --- fades ---------------------------------------------------------------------------

def test_next_while_the_line_fades_in_only_shows_it_in_full():
    scene = _story()
    scene.update(story_module.FADE_S + 0.05)          # picture in, line still fading in
    assert not scene.fully_shown
    _key(scene, pygame.K_SPACE)
    assert scene.index == 0 and scene.fully_shown       # shown in full, same panel
    assert scene.line_alpha == 255
    _key(scene, pygame.K_SPACE)                         # now it moves on
    _settle(scene)
    assert scene.index == 1


def test_next_right_at_the_start_also_only_shows_the_panel_in_full():
    scene = _story()
    _key(scene, pygame.K_RIGHT)
    _settle(scene)
    assert scene.index == 0


def test_panels_fade_out_then_in():
    scene = _story()
    _settle(scene)
    _key(scene, pygame.K_SPACE)
    scene.update(story_module.FADE_S / 2)
    assert scene.index == 0 and 0 < scene.dark_alpha < 255     # fading out
    scene.update(story_module.FADE_S)
    assert scene.index == 1 and scene.dark_alpha == 255        # new panel, still dark
    scene.update(story_module.FADE_S / 2)
    assert 0 < scene.dark_alpha < 255 and scene.line_alpha == 0  # fading in, line waits
    scene.update(story_module.FADE_S / 2 + story_module.LINE_FADE_S + 0.01)
    assert scene.dark_alpha == 0 and scene.line_alpha == 255


def test_fade_timings_are_about_a_third_of_a_second():
    assert 0.2 <= story_module.FADE_S <= 0.4


# --- drawing -------------------------------------------------------------------------

def test_every_panel_draws_without_pictures(no_pictures):
    scene = _story()
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    for _ in range(6):
        for _ in range(4):
            scene.draw(surface)
            scene.update(0.15)
        if scene.index < 5:
            _next(scene)
    scene.draw(surface)


def test_without_a_picture_the_scene_text_is_shown(no_pictures, monkeypatch):
    drawn = []
    real = story_module.draw_text
    monkeypatch.setattr(story_module, "draw_text",
                        lambda surface, text, *a, **k: drawn.append(text) or real(surface, text, *a, **k))
    scene = _story()
    _settle(scene)
    scene.draw(pygame.Surface((config.WINDOW_W, config.WINDOW_H)))
    shown = " ".join(drawn)
    assert "Deep space" in shown and "Main engine offline." in shown and "SHIP" in shown
    assert "1 / 6" in shown
    assert scene.skip_button.label == "Skip"


def test_narration_shows_no_speaker_name(no_pictures, monkeypatch):
    drawn = []
    real = story_module.draw_text
    monkeypatch.setattr(story_module, "draw_text",
                        lambda surface, text, *a, **k: drawn.append(text) or real(surface, text, *a, **k))
    scene = _story()
    for _ in range(3):
        _next(scene)
    assert scene.panel.speaker == ""
    drawn.clear()
    scene.draw(pygame.Surface((config.WINDOW_W, config.WINDOW_H)))
    assert "SHIP" not in drawn


def test_a_story_picture_fills_the_screen_keeping_its_shape(no_pictures, monkeypatch):
    (no_pictures / "story").mkdir()
    picture = pygame.Surface((400, 200))
    picture.fill((200, 40, 40))
    pygame.image.save(picture, str(no_pictures / "story" / "panel1.png"))
    scene = _story()
    _settle(scene)
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    scene.draw(surface)
    assert surface.get_at((config.WINDOW_W // 2, config.WINDOW_H // 4))[:3] == (200, 40, 40)
    # 2:1 in a 16:9 window: full width, dark bands above and below.
    assert surface.get_at((config.WINDOW_W // 2, 2))[:3] != (200, 40, 40)
    assert surface.get_at((2, config.WINDOW_H // 4))[:3] == (200, 40, 40)


# --- slow zoom (Ken Burns) -------------------------------------------------------------

def _with_test_picture(folder, size=(320, 180)):
    """A plain 16:9 picture for story.panel1..6 in ``folder`` (the no_pictures folder)."""
    (folder / "story").mkdir(exist_ok=True)
    picture = pygame.Surface(size)
    picture.fill((90, 140, 200))
    pygame.draw.rect(picture, (250, 220, 40), (size[0] // 4, size[1] // 4, size[0] // 2, size[1] // 2))
    for n in range(1, 7):
        pygame.image.save(picture, str(folder / "story" / f"panel{n}.png"))


def test_zoom_settings():
    assert story_module.ZOOM_END == 1.06
    assert story_module.ZOOM_S == 8.0
    assert story_module.ZOOM_ANCHOR == (0.5, 0.4)


def test_a_panel_starts_at_full_size_and_slowly_zooms_in_then_stays():
    scene = _story()
    assert scene.zoom == 1.0
    zooms = [scene.zoom]
    for _ in range(100):                                # 10 s in steps of 0.1 s
        scene.update(0.1)
        zooms.append(scene.zoom)
    assert all(later > earlier for earlier, later in zip(zooms[:80], zooms[1:81]))
    assert zooms[-1] == pytest.approx(story_module.ZOOM_END)
    scene.update(30.0)
    assert scene.zoom == pytest.approx(story_module.ZOOM_END)


def test_the_zoom_eases_out():
    scene = _story()
    scene.update(story_module.ZOOM_S / 2)
    grown = scene.zoom - 1.0
    assert grown > (story_module.ZOOM_END - 1.0) * 0.6     # well past half way at half time
    scene.update(story_module.ZOOM_S / 2 - 0.001)
    assert scene.zoom < story_module.ZOOM_END
    scene.update(0.002)
    assert scene.zoom == pytest.approx(story_module.ZOOM_END)


def test_showing_the_panel_in_full_does_not_move_the_zoom():
    scene = _story()
    scene.update(story_module.FADE_S / 2)
    before = scene.zoom
    _key(scene, pygame.K_SPACE)
    assert scene.revealed and scene.index == 0
    assert scene.zoom == before
    scene.update(0.5)
    later = scene.zoom
    scene2 = _story()
    scene2.update(story_module.FADE_S / 2)
    scene2.update(0.5)
    assert later == pytest.approx(scene2.zoom)          # same as without the press


def test_the_zoom_goes_on_while_fading_out_and_restarts_on_the_next_panel():
    scene = _story()
    _settle(scene)
    _key(scene, pygame.K_SPACE)                         # leave for panel 2
    before = scene.zoom
    scene.update(story_module.FADE_S / 2)
    assert scene.leaving_to == 1 and scene.zoom > before
    scene.update(story_module.FADE_S)
    assert scene.index == 1 and scene.zoom == 1.0
    scene.update(1.0)
    assert scene.zoom > 1.0


def test_the_picture_grows_about_the_anchor(no_pictures):
    _with_test_picture(no_pictures)
    scene = _story()
    _key(scene, pygame.K_SPACE)                         # shown in full (no veil), still 1.00x
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    scene.draw(surface)
    assert scene.zoom == 1.0
    first = surface.copy()
    scene.update(100.0)
    scene.draw(surface)
    w, h = config.WINDOW_W, config.WINDOW_H
    ax, ay = round(w * 0.5), round(h * 0.4)
    assert surface.get_at((ax, ay))[:3] == first.get_at((ax, ay))[:3]
    # The yellow box (a quarter in from each side) has moved out from the anchor.
    def left_edge(s):
        y = h // 2
        return next(x for x in range(w) if s.get_at((x, y))[:3] == (250, 220, 40))
    assert left_edge(surface) < left_edge(first)


def test_each_panel_asks_load_image_for_one_size_only(no_pictures, monkeypatch):
    _with_test_picture(no_pictures)
    asked = {}
    real = story_module.load_image
    monkeypatch.setattr(story_module, "load_image",
                        lambda key, size_px=None: asked.setdefault(key, set()).add(size_px) or real(key, size_px))
    scene = _story()
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    for _ in range(6):
        for _ in range(60):
            scene.draw(surface)
            scene.update(1 / 20)
        _key(scene, pygame.K_SPACE)
        for _ in range(20):
            scene.draw(surface)
            scene.update(1 / 20)
    assert set(asked) == {f"story.panel{n}" for n in range(1, 7)}
    assert all(len(sizes) == 1 for sizes in asked.values()), asked


def test_a_missing_picture_draws_its_scene_text_without_zooming(monkeypatch):
    key = "test.story_panel_that_does_not_exist"
    monkeypatch.setitem(image_assets._SPECS, key,
                        AssetSpec(key, Path("story/no_such_panel_for_tests.png")))
    image_assets._sources.pop(key, None)
    scene = _story()
    scene.panels = [replace(p, image=key) for p in scene.panels]
    drawn = []
    real = story_module.draw_text
    monkeypatch.setattr(story_module, "draw_text",
                        lambda surface, text, *a, **k: drawn.append((text, a[0])) or real(surface, text, *a, **k))
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    scene.draw(surface)
    early = [d for d in drawn if d[0].startswith("[")]
    drawn.clear()
    scene.update(100.0)
    scene.draw(surface)
    late = [d for d in drawn if d[0].startswith("[")]
    assert early and early == late                      # same text at the same place
    image_assets._sources.pop(key, None)


# --- the ship's lines are typed out ----------------------------------------------------

def _subtitle_texts(scene, monkeypatch):
    """(text, position) of everything drawn for one frame."""
    drawn = []
    real = story_module.draw_text
    monkeypatch.setattr(story_module, "draw_text",
                        lambda surface, text, *a, **k: drawn.append((text, a[0])) or real(surface, text, *a, **k))
    scene.draw(pygame.Surface((config.WINDOW_W, config.WINDOW_H)))
    monkeypatch.setattr(story_module, "draw_text", real)
    return drawn


def _go_to_narration(scene):
    while scene.panel.speaker:
        _next(scene)


def test_type_speed():
    assert story_module.TYPE_CPS == 35


def test_a_ship_line_is_typed_out_once_the_picture_is_in():
    scene = _story()
    line = scene.panel.line
    assert scene.panel.speaker == "SHIP"
    assert scene.typed_chars == 0
    scene.update(story_module.FADE_S - 0.01)
    assert scene.typed_chars == 0
    counts = []
    for _ in range(60):
        scene.update(0.05)
        counts.append(scene.typed_chars)
    assert all(later >= earlier for earlier, later in zip(counts, counts[1:]))
    assert 0 < counts[4] < counts[10] < len(line)
    assert counts[-1] == len(line)


def test_typing_takes_the_line_length_over_the_speed():
    scene = _story()
    n = len(scene.panel.line)
    scene.update(story_module.FADE_S + (n - 2) / story_module.TYPE_CPS)
    assert scene.typed_chars == n - 2 and not scene.fully_shown
    scene.update(2 / story_module.TYPE_CPS + 0.001)
    assert scene.typed_chars == n and scene.fully_shown


def test_the_ellipsis_counts_as_one_character():
    scene = _story()
    _next(scene)
    _next(scene)
    line = scene.panel.line
    assert "…" in line and "..." not in line
    scene.t = story_module.FADE_S + (len(line) - 0.5) / story_module.TYPE_CPS
    assert scene.typed_chars == len(line) - 1 and not scene.fully_shown
    scene.t = story_module.FADE_S + (len(line) + 0.5) / story_module.TYPE_CPS
    assert scene.typed_chars == len(line) and scene.fully_shown


def test_the_name_and_box_show_at_once_but_the_line_is_typed(monkeypatch):
    scene = _story()
    scene.update(story_module.FADE_S + 5 / story_module.TYPE_CPS + 0.001)
    assert scene.line_alpha == 255
    texts = [t for t, _ in _subtitle_texts(scene, monkeypatch)]
    assert "SHIP" in texts
    assert scene.panel.line[:5] in texts and scene.panel.line not in texts


def test_narration_still_fades_in_and_is_not_typed(monkeypatch):
    scene = _story()
    _go_to_narration(scene)
    scene.t = 0.0                                       # as if the narration had just come up
    assert scene.panel.speaker == "" and not scene.revealed
    assert scene.typed_chars == len(scene.panel.line)
    scene.update(story_module.FADE_S + story_module.LINE_FADE_S / 2)
    assert 0 < scene.line_alpha < 255 and not scene.fully_shown
    texts = [t for t, _ in _subtitle_texts(scene, monkeypatch)]
    assert any(scene.panel.line.startswith(t) and len(t) > 20 for t in texts)
    scene.update(story_module.LINE_FADE_S / 2 + 0.01)
    assert scene.line_alpha == 255 and scene.fully_shown


def test_next_while_typing_shows_the_whole_line_then_moves_on(monkeypatch):
    scene = _story()
    scene.update(story_module.FADE_S + 0.2)
    assert 0 < scene.typed_chars < len(scene.panel.line) and not scene.fully_shown
    _key(scene, pygame.K_SPACE)
    assert scene.index == 0 and scene.leaving_to is None
    assert scene.typed_chars == len(scene.panel.line) and scene.fully_shown
    assert scene.panel.line in [t for t, _ in _subtitle_texts(scene, monkeypatch)]
    _key(scene, pygame.K_SPACE)
    _settle(scene)
    assert scene.index == 1


def test_a_typed_line_breaks_where_the_whole_line_does(monkeypatch):
    long_line = ("Main engine offline. Fuel: zero. Broadcasting on all frequencies… "
                 "Can anyone hear me? Write the field, Architect, and guide me home through the dark.")
    scene = _story()
    scene.panels = [replace(p, line=long_line) for p in scene.panels]
    scene.update(100.0)
    full = [(t, pos) for t, pos in _subtitle_texts(scene, monkeypatch)
            if t and t in long_line and t != "SHIP"]
    assert len(full) >= 2, "the test line should wrap"
    for typed in range(1, len(long_line) + 1, 7):
        scene.t = story_module.FADE_S + (typed + 0.5) / story_module.TYPE_CPS
        assert scene.typed_chars == typed
        partial = [(t, pos) for t, pos in _subtitle_texts(scene, monkeypatch)
                   if t and t in long_line and t != "SHIP"]
        assert len(partial) <= len(full)
        for (part, part_pos), (whole, whole_pos) in zip(partial, full):
            assert whole.startswith(part) and part_pos == whole_pos
        assert " ".join(t for t, _ in partial).rstrip(" ") == long_line[:typed].rstrip(" ")


# --- music ---------------------------------------------------------------------------

def test_the_opening_track_plays_when_it_exists():
    audio = Audio(music_paths={"opening": Path("opening.ogg")})
    scene = _story(audio)
    assert scene.music == "opening"
    assert audio.music_asked == ["opening"]


def test_without_the_opening_track_the_music_is_left_alone():
    audio = Audio()
    scene = _story(audio)
    assert scene.music is None
    assert audio.music_asked == []
