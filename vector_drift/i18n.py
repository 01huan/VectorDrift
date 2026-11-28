"""Language preferences and translation lookup."""

from __future__ import annotations

import json
import locale
import os
import sys
import uuid
import re
from pathlib import Path
from typing import Mapping

from .translations import ZH_TW

DEFAULT_LANGUAGE = "en"

# Every supported language: code -> name in that language.
# Add a new language here and give it a catalog in _CATALOGS below; missing
# entries deliberately fall back to the original English string, so a partial
# translation never breaks the UI.  Nothing else in the app hardcodes a list
# of languages: read SUPPORTED_LANGUAGES / LANGUAGE_NAMES instead.
LANGUAGES: dict[str, str] = {
    "en": "English",
    "zh-TW": "繁體中文",
}
SUPPORTED_LANGUAGES: tuple[str, ...] = tuple(LANGUAGES)
# Backwards-compatible alias; same mapping as LANGUAGES.
LANGUAGE_NAMES = LANGUAGES
# Languages written in a script the bundled Latin font cannot render.  These
# use a platform CJK face and character-based wrapping (no spaces between
# words).  Add new CJK locales here when they are added to LANGUAGES.
CJK_LANGUAGES: frozenset[str] = frozenset({"zh-TW"})

# Parameterized text that cannot be listed as exact catalog keys.  Each
# language maps to (pattern, replacement) pairs; named groups keep the
# replacements readable and independent of the match order.  Patterns are
# deliberately strict: a loose "Level (\d+)" once turned the XP toast
# "Level 5" into the campaign wording "第 5 關".
_PATTERNS: dict[str, tuple[tuple[str, str], ...]] = {
    "zh-TW": (
        # "Level N" is ambiguous (campaign level vs player level). Callers use
        # t("Campaign level {level}") / t("Level {level}") instead, so no
        # blanket pattern is needed here.
        (r"Lv (?P<level>\d+)", "等級 {level}"),
        (r"Daily (?P<day>\d{4}-\d{2}-\d{2})", "每日挑戰 {day}"),
        (r"Ln (?P<line>\d+)", "第 {line} 行"),
        (r"Hint (?P<page>\d+) / (?P<total>\d+)", "提示 {page} / {total}"),
        (r"Page (?P<page>\d+) / (?P<total>\d+)", "第 {page} / {total} 頁"),
        (r"Tutorial (?P<step>\d+) / (?P<total>\d+)", "教學 {step} / {total}"),
        (r"Section (?P<section>\d+) / (?P<total>\d+)", "區段 {section} / {total}"),
        (r"LV(?P<level>\d+)", "等級 {level}"),
        (r"Mass: (?P<mass>[\d.]+) kg", "質量：{mass} kg"),
        (r"Streak bonus \+(?P<xp>\d+) \((?P<days>\d+) days?\)", "連續獎勵 +{xp}（{days} 天）"),
        (r"(?P<n>\d+) lives? left · back to start", "剩餘 {n} 條生命 · 回到起點"),
        (r"(?P<n>\d+) lives? left · resume from \((?P<x>-?[\d.]+), (?P<y>-?[\d.]+)\)",
         "剩餘 {n} 條生命 · 從 ({x}, {y}) 繼續"),
        (r"Daily (?P<day>\d{4}-\d{2}-\d{2}) · section (?P<n>\d+)/(?P<total>\d+)",
         "每日挑戰 {day} · 區段 {n}/{total}"),
        (r"uses (?P<uses>\d+) · users (?P<users>\d+)", "使用 {uses} 次 · 玩家 {users} 人"),
        (r"Uses (?P<uses>\d+) · successful (?P<ok>\d+) \((?P<pct>\d+)%\)",
         "使用 {uses} 次 · 成功 {ok} 次（{pct}%）"),
        (r"(?P<avg>\d+\.\d) · (?P<count>\d+) ratings? · you: (?P<mine>\d+)",
         "{avg} · {count} 則評分 · 你的評分：{mine}"),
        (r"(?P<avg>\d+\.\d) · (?P<count>\d+) ratings?", "{avg} · {count} 則評分"),
    ),
}

# Add new locales here.  Missing entries deliberately fall back to the
# original English string, so a partial translation never breaks the UI.
_CATALOGS: dict[str, Mapping[str, str]] = {
    "zh-TW": {
        # Bulk translations (hints, story, achievements, statuses, ...) live in
        # their own module so this file stays about language selection and
        # lookup.  Explicit entries below override them when a shorter or more
        # context-appropriate wording is needed.
        **ZH_TW,
        "Start": "開始", "Quit": "離開", "Login": "登入", "Account": "帳號",
        "Replays": "重播", "Achievements": "成就", "Settings": "設定",
        "Language": "語言", "Language Settings": "語言設定",
        "Choose the language used by Vector Drift.": "選擇 Vector Drift 使用的語言。",
        "Back": "返回", "Main Menu": "主選單", "Levels": "關卡", "Shop": "商店",
        "Daily": "每日挑戰", "Level Editor": "關卡編輯器", "Function Lab": "函數實驗室",
        "Tutorial": "教學", "Cancel": "取消", "Save": "儲存", "Play": "開始遊玩",
        "Pause": "暫停", "Resume": "繼續", "Retry": "再試一次", "Next": "下一步",
        "Prev": "上一頁", "Exit": "離開", "Buy": "購買", "Locked": "尚未解鎖",
        "Paused": "已暫停", "Continue": "繼續", "Close": "關閉", "Delete": "刪除",
        "Apply": "套用", "Shape the field, guide the ship": "塑造力場，引導飛船",
        "Enter: launch   L: login/account   Ctrl+M: mute": "Enter：開始   L：登入／帳號   Ctrl+M：靜音",
        "English": "English", "繁體中文": "繁體中文",
        "ACCOUNT": "帳號", "SHOP": "商店", "REPLAY": "重播", "REPLAYS": "重播紀錄",
        "MISSION COMPLETE": "任務完成", "ACHIEVEMENT UNLOCKED": "解鎖成就",
        "LEVEL UP": "等級提升", "Level": "關卡", "Time": "時間", "Position": "位置",
        "Velocity": "速度", "Force": "力", "Force formula": "力的公式", "Ship": "飛船",
        "Record": "紀錄", "Last flight": "上次飛行", "Attempts": "嘗試次數",
        "Lives left": "剩餘生命", "Total flight time": "總飛行時間",
        "Coins earned": "獲得金幣", "XP earned": "獲得 XP", "Price": "價格",
        "Owned": "已擁有", "Owned ×{count}": "已擁有 ×{count}",
        "No launch records saved yet.": "尚未儲存任何飛行紀錄。",
        "slow down": "減速", "speed up": "加速", "Refresh": "重新整理",
        "Refresh profile": "重新整理個人資料", "Logout": "登出", "Display name": "顯示名稱",
        "Status": "狀態", "Sync": "同步", "User": "使用者", "Records": "紀錄",
        "Change Account Name": "更改帳號名稱", "change name": "更改名稱",
        "new name": "新名稱", "save": "儲存", "cancel": "取消",
        "Delete local data": "刪除本機資料", "Email": "電子郵件", "Password": "密碼",
        "Confirm password": "確認密碼", "Create account": "建立帳號", "Confirm": "確認",
        "Forgot password": "忘記密碼", "Sign in": "登入", "Sign up": "註冊",
        "Use Local": "使用本機資料", "Use Cloud": "使用雲端資料",
        "Paused": "已暫停", "Restart": "重新開始", "Abort flight": "中止飛行",
        "Music: On": "音樂：開", "Music: Off": "音樂：關",
        "Sound: On": "音效：開", "Sound: Off": "音效：關",
        "Quit VectorDrift?": "要離開 Vector Drift 嗎？", "Skip": "跳過",
        "Hint": "提示", "Show answer": "顯示答案", "Show the answer?": "要顯示答案嗎？",
        "No problems": "沒有問題", "PROBLEMS": "問題", "Element guide": "元素指南",
        "Click a row to watch": "點擊項目觀看示範", "Obstacles": "障礙物",
        "Rock": "岩石", "Portals": "傳送門", "Black / white hole": "黑洞／白洞",
        "Pickups": "拾取物", "Shockwave": "震波", "Extratime": "延長時間",
        "Unbound": "解除邊界", "Shield": "護盾", "Start playing": "開始遊玩",
        "Fly home": "飛回家", "Time's up": "時間到", "Out of bounds": "超出範圍",
        "Help": "說明", "OK": "確定", "ARRIVED": "已抵達", "HOLD": "暫停等待",
        "DESCRIPTION": "說明", "TAGS": "標籤", "AVERAGE RATING": "平均評分",
        "NAME": "名稱", "Functions": "函數", "Public Levels": "公開關卡",
        "Import": "匯入", "Favorite": "收藏", "Edit": "編輯", "Upload": "上傳",
        "Search": "搜尋", "Reset": "重設", "Previous": "上一頁", "Next": "下一頁",
        "Loading...": "載入中…", "Coming soon": "即將推出", "Locked": "尚未解鎖",
        "Rocks bounce the ship off. The bounce keeps its speed.": "岩石會彈開飛船，反彈後會保持速度。",
        "Enter the black hole, come out of the white hole, at the same speed.": "進入黑洞後會從白洞出來，速度維持不變。",
        "Blasts every rock within 3 m.": "摧毀 3 公尺內的所有岩石。",
        "Adds 3 seconds to this flight.": "本次飛行增加 3 秒。",
        "For the rest of this life the ship can leave the map.": "在這條生命剩餘期間，飛船可以飛出地圖。",
        "Lasts 3 s. Stops the next hit: pass through one rock...": "持續 3 秒。抵擋下一次碰撞：穿過一塊岩石…",
        "...or bounce off the map edge once.": "…或在地圖邊緣反彈一次。",
        "Home! Reach the planet to clear a level.": "到家了！抵達星球即可通過關卡。",
        "It flew on from where it stopped.": "飛船會從停止的位置繼續飛行。",
        "Out of bounds. The ship left the map.": "超出範圍，飛船已離開地圖。",
        "Main engine offline. Fuel: zero.": "主引擎離線。燃料：零。",
        "No thrust. Home is out of reach.": "沒有推力，家園遙不可及。",
        "Broadcasting on all frequencies… Can anyone hear me?": "正在所有頻率廣播…有人聽得到嗎？",
        "Someone answers. Not a ship. Not a station. The one who shapes space itself.": "有人回應了。不是飛船，也不是太空站，而是塑造空間本身的存在。",
        "You can bend space… You are the Cosmic Architect.": "你能扭曲空間…你就是宇宙建築師。",
        "I can't move on my own. Write the field, Architect. Guide me home.": "我無法自行移動。建築師，寫下力場，引導我回家。",
        "SHIP": "飛船",
        "Daily Challenge": "每日挑戰",
        # Parameterized templates: translate the English template first, then
        # fill the placeholders (see t() below).  Reordering is allowed here.
        "Player level {level}": "等級 {level}",
        # Both render as "Level N" in English; distinct keys keep the Chinese
        # wording unambiguous (player level vs campaign level).
        "Level {level}": "等級 {level}",
        "Campaign level {level}": "第 {level} 關",
        "Owned ×{count}": "已擁有 ×{count}",
        "+{coins} coins": "+{coins} 金幣",
        "plays {plays} · clears {clears} · players {players}":
            "遊玩 {plays} 次 · 通關 {clears} 次 · 玩家 {players} 人",
    },
}


def _settings_path() -> Path:
    return Path.home() / ".vector_drift" / "settings.json"


def _atomic_write(path: Path, text: str) -> None:
    """Write preferences without coupling startup to optional account modules."""
    temporary = path.with_name(f"{path.name}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp")
    try:
        temporary.write_text(text, encoding="utf-8")
        os.replace(temporary, path)
    except OSError:
        try:
            temporary.unlink()
        except OSError:
            pass
        raise


def _match_language(candidate: object) -> str | None:
    """The supported language code a locale/tag names, or None.

    Accepts OS spellings (``zh_TW``, ``en-US``, ``zh-Hant`` ...): underscores
    become hyphens, matching is case-insensitive, and a region/script suffix
    falls back to its base language.  Chinese variants map to a supported
    Chinese language when one exists.
    """
    value = str(candidate or "").strip().replace("_", "-").lower()
    if not value:
        return None
    supported = {code.lower(): code for code in SUPPORTED_LANGUAGES}
    if value in supported:
        return supported[value]
    base = value.split("-", 1)[0]
    if base in supported:
        return supported[base]
    # e.g. zh-CN / zh-Hans / zh -> a supported zh-* language (zh-TW today).
    if value.startswith("zh"):
        for code in SUPPORTED_LANGUAGES:
            if code.lower().startswith("zh"):
                return code
    return None


def system_language() -> str:
    """Return the closest supported language for the operating system locale."""
    candidates = []
    if sys.platform == "win32":
        try:
            import ctypes
            buffer = ctypes.create_unicode_buffer(85)
            if ctypes.windll.kernel32.GetUserDefaultLocaleName(buffer, len(buffer)):
                candidates.append(buffer.value)
        except (AttributeError, OSError):
            pass
    try:
        candidates.append(locale.getlocale()[0])
    except (TypeError, ValueError):
        pass
    for candidate in candidates:
        matched = _match_language(candidate)
        if matched is not None:
            return matched
    return DEFAULT_LANGUAGE


def match_language(language: object) -> str | None:
    """The canonical supported code for any locale spelling, or None.

    Unlike :func:`normalize_language`, an unknown code returns None instead of
    silently becoming English.  Callers that must not overwrite a valid saved
    preference (e.g. profile sync) use this to tell "unsupported" apart from
    "not set".
    """
    return _match_language(language)


def normalize_language(language: object) -> str:
    """A supported language code, or DEFAULT_LANGUAGE for anything unknown."""
    return _match_language(language) or DEFAULT_LANGUAGE


class LanguagePreferences:
    """Local fallback until an account profile supplies a synced preference."""

    def __init__(self, path: Path | None = None, system_locale=None) -> None:
        self.path = Path(path) if path is not None else _settings_path()
        self._system_locale = system_locale or system_language
        self.language = self._load_or_initialize()

    def _load_or_initialize(self) -> str:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8")).get("language")
        except (AttributeError, OSError, ValueError, json.JSONDecodeError):
            value = None
        matched = _match_language(value)
        if matched is not None:
            return matched
        language = normalize_language(self._system_locale())
        self._write(language)
        return language

    def set_language(self, language: str) -> bool:
        matched = _match_language(language)
        if matched is None:
            raise ValueError(f"Unsupported language: {language}")
        changed = matched != self.language
        self.language = matched
        self._write(matched)
        return changed

    def _write(self, language: str) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            _atomic_write(self.path, json.dumps({"language": language}, ensure_ascii=False))
        except OSError:
            pass


_preferences: LanguagePreferences | None = None


def preferences() -> LanguagePreferences:
    global _preferences
    if _preferences is None:
        _preferences = LanguagePreferences()
    return _preferences


def set_language(language: str) -> bool:
    return preferences().set_language(language)


def current_language() -> str:
    """The code currently in use; use it to invalidate cached, translated layout."""
    return preferences().language


def translate(text: object) -> object:
    """Render ``text`` in the current language; unknown strings stay as-is.

    Only string keys are looked up; anything already translated, unknown, or
    not a string is returned unchanged, so calling translate twice is safe.
    """
    if not isinstance(text, str):
        return text
    language = preferences().language
    translated = _CATALOGS.get(language, {}).get(text)
    if translated is not None:
        return translated
    # Parameterized strings that cannot be enumerated in the catalog. Every
    # pattern contains a number, so plain prose skips the regex loop entirely
    # (translate runs on every drawn label, including hot HUD paths).
    if not any(char.isdigit() for char in text):
        return text
    for pattern, replacement in _PATTERNS.get(language, ()):
        if match := re.fullmatch(pattern, text):
            return replacement.format(**match.groupdict())
    return text


def t(template: str, **values: object) -> str:
    """Translate a parameterized English template, then fill its placeholders.

    Templates are their own English keys, so the untranslated call already
    reads correctly.  Translated catalogs may reword or reorder placeholders;
    if a translation is malformed, the English template is used instead so a
    partially translated catalog can never break the UI.
    """
    language = preferences().language
    translated = _CATALOGS.get(language, {}).get(template, template)
    try:
        return translated.format(**values)
    except (KeyError, IndexError, ValueError):
        return template.format(**values)
