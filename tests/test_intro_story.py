"""Intro story: the six panels in intro_story.toml and the screen that plays them."""
from pathlib import Path
from types import SimpleNamespace

import pygame
import pytest

from vector_drift import config, image_assets
from vector_drift import intro_story
from vector_drift.image_assets import AssetSpec
from vector_drift.scenes import story as story_module
from vector_drift.scenes.base import SceneManager
from vector_drift.scenes.levels import LevelSelectScene
from vector_drift.scenes.story import StoryScene

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
    """No story pictures exist (the real state today, made explicit)."""
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
    """Let any fade finish, so the panel is fully shown."""
    scene.update(1.0)
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


def test_next_on_the_last_panel_ends_the_story_at_level_select():
    scene = _story()
    for _ in range(5):
        _next(scene)
    assert scene.index == 5 and scene.counter_text == "6 / 6"
    _key(scene, pygame.K_SPACE)
    assert isinstance(scene.manager.scene, LevelSelectScene)


def test_skip_button_ends_the_story_at_level_select():
    scene = _story()
    _next(scene)
    _click(scene, scene.skip_button.rect.center)
    assert isinstance(scene.manager.scene, LevelSelectScene)


def test_escape_ends_the_story_at_level_select():
    scene = _story()
    _key(scene, pygame.K_ESCAPE)
    assert isinstance(scene.manager.scene, LevelSelectScene)


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


def test_scene_after_story_is_level_select_for_now():
    manager = SceneManager(Audio())
    assert isinstance(story_module.scene_after_story(manager), LevelSelectScene)


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
