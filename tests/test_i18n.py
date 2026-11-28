"""Language selection uses the system once, then follows the synced profile."""

import json

import pygame
import pygame.surfarray
import pytest

from vector_drift import i18n
from vector_drift.account.integration import (
    apply_profile_to_session,
    profiles_equal,
    session_to_profile,
)
from vector_drift.scenes.base import Session


def test_first_run_uses_system_language_and_persists_it(tmp_path):
    path = tmp_path / "settings.json"
    prefs = i18n.LanguagePreferences(path, system_locale=lambda: "zh_TW")

    assert prefs.language == "zh-TW"
    assert path.read_text(encoding="utf-8")

    # A future OS language change does not replace a persisted selection.
    later = i18n.LanguagePreferences(path, system_locale=lambda: "en_US")
    assert later.language == "zh-TW"


def test_language_is_part_of_synced_profile(monkeypatch, tmp_path):
    prefs = i18n.LanguagePreferences(tmp_path / "settings.json", system_locale=lambda: "en_US")
    monkeypatch.setattr(i18n, "_preferences", prefs)
    session = Session(language="zh-TW")

    profile = session_to_profile(session, "player-1")
    assert profile.stats["language"] == "zh-TW"

    target = Session(language="en")
    apply_profile_to_session(target, profile, "player-1")
    assert target.language == "zh-TW"
    assert prefs.language == "zh-TW"


def test_legacy_profile_keeps_current_language(monkeypatch, tmp_path):
    prefs = i18n.LanguagePreferences(tmp_path / "settings.json", system_locale=lambda: "zh_TW")
    monkeypatch.setattr(i18n, "_preferences", prefs)
    session = Session(language="zh-TW")
    profile = session_to_profile(session, "player-1")
    profile.stats.pop("language")

    target = Session(language="zh-TW")
    apply_profile_to_session(target, profile, "player-1")
    assert target.language == "zh-TW"


def test_catalog_translates_toml_backed_tutorial_and_story_text(monkeypatch, tmp_path):
    prefs = i18n.LanguagePreferences(tmp_path / "settings.json", system_locale=lambda: "zh_TW")
    monkeypatch.setattr(i18n, "_preferences", prefs)

    assert i18n.translate("Rocks bounce the ship off. The bounce keeps its speed.") == "岩石會彈開飛船，反彈後會保持速度。"
    assert i18n.translate("Main engine offline. Fuel: zero.") == "主引擎離線。燃料：零。"


def test_english_interface_keeps_native_language_names(monkeypatch, tmp_path):
    prefs = i18n.LanguagePreferences(tmp_path / "settings.json", system_locale=lambda: "en_US")
    monkeypatch.setattr(i18n, "_preferences", prefs)

    assert i18n.translate("繁體中文") == "繁體中文"


@pytest.mark.parametrize("code", ["zh-TW", "zh-tw", "zh_TW", "ZH-TW", "zh-Hant", "zh-CN", "zh"])
def test_locale_spellings_resolve_to_the_supported_language(code):
    assert i18n.match_language(code) == "zh-TW"
    assert i18n.normalize_language(code) == "zh-TW"


@pytest.mark.parametrize("code, expected", [
    ("ja", "ja"), ("ja-JP", "ja"), ("ja_JP", "ja"), ("jp", "ja"),
    ("ko", "ko"), ("ko-KR", "ko"), ("ko_KR", "ko"), ("kr", "ko"),
])
def test_japanese_and_korean_locales_resolve(code, expected):
    assert i18n.match_language(code) == expected
    assert i18n.normalize_language(code) == expected


@pytest.mark.parametrize("language, cjk", [("zh-TW", True), ("ja", True), ("ko", True)])
def test_cjk_languages_have_a_font_list(language, cjk):
    assert (language in i18n.CJK_LANGUAGES) is cjk
    assert i18n.CJK_FONTS.get(language)


def test_wide_glyph_detection_covers_kana_and_hangul():
    from vector_drift.ui_fonts import _needs_cjk_font

    assert _needs_cjk_font("こんにちは")
    assert _needs_cjk_font("カタカナ")
    assert _needs_cjk_font("안녕하세요")
    assert _needs_cjk_font("漢字")
    assert not _needs_cjk_font("Start")


def test_unsupported_language_is_not_mistaken_for_a_valid_preference():
    assert i18n.match_language("fr") is None
    assert i18n.match_language(None) is None
    assert i18n.normalize_language("fr") == "en"


def test_set_language_normalizes_and_rejects_unknown_codes(tmp_path):
    path = tmp_path / "settings.json"
    prefs = i18n.LanguagePreferences(path, system_locale=lambda: "en_US")
    assert prefs.set_language("zh_TW") is True
    assert prefs.language == "zh-TW"
    assert "zh-TW" in path.read_text(encoding="utf-8")
    assert prefs.set_language("zh-TW") is False
    with pytest.raises(ValueError):
        prefs.set_language("fr")


def test_profile_sync_normalizes_language_codes(monkeypatch, tmp_path):
    prefs = i18n.LanguagePreferences(tmp_path / "settings.json", system_locale=lambda: "en_US")
    monkeypatch.setattr(i18n, "_preferences", prefs)

    src = Session(language="zh_TW")
    profile = session_to_profile(src, "player-1")
    assert profile.stats["language"] == "zh-TW"

    # A legacy profile using another spelling still applies cleanly.
    profile.stats["language"] = "zh-tw"
    target = Session(language="en")
    apply_profile_to_session(target, profile, "player-1")
    assert target.language == "zh-TW"
    assert prefs.language == "zh-TW"


def test_unsupported_profile_language_keeps_the_current_preference(monkeypatch, tmp_path):
    prefs = i18n.LanguagePreferences(tmp_path / "settings.json", system_locale=lambda: "zh_TW")
    monkeypatch.setattr(i18n, "_preferences", prefs)
    session = Session(language="zh-TW")
    profile = session_to_profile(session, "player-1")
    profile.stats["language"] = "fr"

    target = Session(language="en")
    apply_profile_to_session(target, profile, "player-1")
    assert target.language == "zh-TW"
    assert prefs.language == "zh-TW"


def test_language_only_difference_is_not_a_progress_conflict():
    english = session_to_profile(Session(language="en"), "player-1")
    chinese = session_to_profile(Session(language="zh-TW"), "player-1")
    assert profiles_equal(english, chinese) is True
    # Save deduplication must still notice the preference change.
    assert profiles_equal(english, chinese, include_preferences=True) is False


def test_language_change_survives_local_save_deduplication(monkeypatch, tmp_path):
    from vector_drift.account import local_profile_manager
    from vector_drift.account.local_profile_manager import LocalProfileManager

    path = tmp_path / "guest_profile.json"
    monkeypatch.setattr(local_profile_manager, "_storage_path", lambda: path)
    manager = LocalProfileManager()
    session = Session(language="en")
    manager.save(session)

    def saved_language():
        return json.loads(path.read_text(encoding="utf-8"))["stats"]["language"]

    assert saved_language() == "en"
    session.language = "zh-TW"
    manager.save(session)
    assert saved_language() == "zh-TW"


def test_dynamic_strings_are_translated_precisely(monkeypatch, tmp_path):
    prefs = i18n.LanguagePreferences(tmp_path / "settings.json", system_locale=lambda: "zh_TW")
    monkeypatch.setattr(i18n, "_preferences", prefs)

    # Both render as "Level 5" in English, but translate unambiguously.
    assert i18n.t("Campaign level {level}", level=5) == "第 5 關"
    assert i18n.t("Level {level}", level=5) == "等級 5"
    assert i18n.translate("Lv 5") == "等級 5"
    assert i18n.t("Player level {level}", level=5) == "等級 5"
    assert i18n.translate("Daily Challenge") == "每日挑戰"
    assert i18n.translate("Daily 2026-11-28") == "每日挑戰 2026-11-28"
    assert i18n.t("Owned ×{count}", count=3) == "已擁有 ×3"
    assert i18n.t("+{coins} coins", coins=10) == "+10 金幣"
    assert i18n.translate("Page 2 / 4") == "第 2 / 4 頁"
    assert i18n.translate("2 lives left · back to start") == "剩餘 2 條生命 · 回到起點"
    assert i18n.translate("Streak bonus +10 (3 days)") == "連續獎勵 +10（3 天）"
    assert i18n.translate("uses 5 · users 3") == "使用 5 次 · 玩家 3 人"


@pytest.mark.parametrize("language", ["ja", "ko"])
def test_japanese_and_korean_catalogs_translate_and_keep_native_names(monkeypatch, tmp_path, language):
    prefs = i18n.LanguagePreferences(tmp_path / "settings.json", system_locale=lambda: language)
    monkeypatch.setattr(i18n, "_preferences", prefs)

    assert "Start" in i18n._CATALOGS[language]
    assert i18n.translate("Start") != "Start"
    for name in ("English", "繁體中文", "日本語", "한국어"):
        assert i18n.translate(name) == name


@pytest.mark.parametrize("language, level, hint, page", [
    ("ja", "レベル 5", "ヒント 2 / 4", "2 / 4 ページ"),
    ("ko", "레벨 5", "힌트 2 / 4", "2 / 4 페이지"),
])
def test_japanese_and_korean_dynamic_patterns(monkeypatch, tmp_path, language, level, hint, page):
    prefs = i18n.LanguagePreferences(tmp_path / "settings.json", system_locale=lambda: language)
    monkeypatch.setattr(i18n, "_preferences", prefs)
    assert i18n.translate("Lv 5") == level
    assert i18n.translate("Hint 2 / 4") == hint
    assert i18n.translate("Page 2 / 4") == page


def test_settings_scene_offers_every_language(monkeypatch, pygame_display):
    from types import SimpleNamespace

    from vector_drift.scenes.base import SceneManager
    from vector_drift.scenes.settings import SettingsScene

    manager = SceneManager(SimpleNamespace(play=lambda *a, **k: None))
    scene = SettingsScene(manager)
    assert [code for code, _button in scene.language_buttons] == list(i18n.SUPPORTED_LANGUAGES)


def test_parameterized_templates_fall_back_to_english(monkeypatch, tmp_path):
    prefs = i18n.LanguagePreferences(tmp_path / "settings.json", system_locale=lambda: "en_US")
    monkeypatch.setattr(i18n, "_preferences", prefs)
    assert i18n.t("Player level {level}", level=5) == "Player level 5"


@pytest.mark.parametrize("locale, code", [
    ("en_US", "en"), ("zh_TW", "zh-TW"), ("ja_JP", "ja"), ("ko_KR", "ko"),
])
def test_ui_draws_in_every_language(monkeypatch, pygame_display, tmp_path, locale, code):
    from types import SimpleNamespace

    from vector_drift import config
    from vector_drift.scenes.base import SceneManager
    from vector_drift.scenes.menu import MenuScene
    from vector_drift.scenes.settings import SettingsScene

    prefs = i18n.LanguagePreferences(tmp_path / "settings.json", system_locale=lambda: locale)
    monkeypatch.setattr(i18n, "_preferences", prefs)
    audio = SimpleNamespace(play=lambda *a, **k: None, set_music=lambda *a, **k: None)
    manager = SceneManager(audio)
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    manager.switch(MenuScene(manager))
    manager.draw(surface)
    manager.switch(SettingsScene(manager))
    manager.draw(surface)
    assert i18n.current_language() == code


def test_rendered_menu_changes_with_language(monkeypatch, pygame_display, tmp_path):
    from types import SimpleNamespace

    from vector_drift import config
    from vector_drift.scenes.base import SceneManager
    from vector_drift.scenes.menu import MenuScene

    audio = SimpleNamespace(play=lambda *a, **k: None, set_music=lambda *a, **k: None)

    def pixels(system_language):
        prefs = i18n.LanguagePreferences(tmp_path / f"{system_language}.json",
                                         system_locale=lambda: system_language)
        monkeypatch.setattr(i18n, "_preferences", prefs)
        manager = SceneManager(audio)
        surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
        manager.switch(MenuScene(manager))
        manager.draw(surface)
        return pygame.surfarray.array3d(surface).tobytes()

    assert pixels("en_US") != pixels("zh_TW")


def test_settings_scene_applies_and_saves_language(monkeypatch, pygame_display, tmp_path):
    from types import SimpleNamespace

    from vector_drift.account import integration
    from vector_drift.scenes.base import SceneManager
    from vector_drift.scenes.settings import SettingsScene

    calls = []
    monkeypatch.setattr(integration, "save_progress",
                        lambda account, session: calls.append((account, session.language)))
    prefs = i18n.LanguagePreferences(tmp_path / "settings.json", system_locale=lambda: "en_US")
    monkeypatch.setattr(i18n, "_preferences", prefs)

    audio = SimpleNamespace(play=lambda *a, **k: None)
    manager = SceneManager(audio)
    scene = SettingsScene(manager)
    manager.switch(scene)

    language, button = scene.language_buttons[1]
    assert language == "zh-TW"
    scene.handle_event(pygame.event.Event(
        pygame.MOUSEBUTTONDOWN, button=1, pos=button.rect.center))
    assert prefs.language == "zh-TW"
    assert manager.session.language == "zh-TW"
    assert calls and calls[-1][1] == "zh-TW"
