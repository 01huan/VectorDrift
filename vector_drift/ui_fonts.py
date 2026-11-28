"""Fonts and basic widgets: Button, CodeEditor."""

import re
import warnings

import pygame

from . import config
from .config import px

_font_cache = {}

_FONT_CHOICES = {
    # kind: (asset file, system font fallbacks)
    # The fallbacks are tried in order, so Windows keeps its own fonts first;
    # macOS and Linux add theirs (Helvetica/Menlo, DejaVu/Liberation/Noto).
    "ui": ("ui.ttf", "segoeui,arial,helvetica,helveticaneue,liberationsans,"
                    "notosans,ubuntu,dejavusans"),
    "bold": ("ui_bold.ttf", "segoeuisemibold,segoeuibold,segoeui,arial,helvetica,"
                            "helveticaneue,liberationsans,notosans,ubuntu,dejavusans"),
    "mono": ("mono.ttf", "consolas,couriernew,dejavusansmono,liberationmono,"
                         "notosansmono,menlo,monaco,courier"),
}


def _system_font(names, size, bold):
    """The first available system font from a comma separated list of names.

    pygame warns when none of the names exists; the built-in font is a fine
    fallback and the warning would repeat for every new font size.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return pygame.font.SysFont(names, size, bold=bold)


def _needs_cjk_font(text):
    """Whether ``text`` contains glyphs the bundled Latin face cannot draw.

    Covers CJK ideographs (Chinese/Japanese kanji), kana and Hangul so mono
    labels and mixed strings use a CJK-capable font too.
    """
    if not isinstance(text, str):
        return False
    return any(
        "\u3040" <= char <= "\u30ff"      # hiragana / katakana
        or "\u3400" <= char <= "\u9fff"   # CJK ideographs
        or "\uac00" <= char <= "\ud7af"   # Hangul syllables
        or "\u1100" <= char <= "\u11ff"   # Hangul jamo
        for char in text
    )


def get_font(size, kind="ui", *, cjk=False):
    """Font at a logical size (scaled to real pixels)."""
    # The bundled Latin face does not contain CJK glyphs.  For Chinese,
    # Japanese or Korean use a platform CJK face first so translated text
    # never renders as empty boxes.
    from .i18n import CJK_FONTS, CJK_LANGUAGES, preferences
    language = preferences().language
    use_cjk = cjk or (language in CJK_LANGUAGES and kind in ("ui", "bold"))
    key = (kind, size, language, use_cjk)
    font = _font_cache.get(key)
    if font is None:
        filename, sys_names = _FONT_CHOICES[kind]
        path = config.ASSETS_DIR / "fonts" / filename
        if path.exists() and not use_cjk:
            font = pygame.font.Font(str(path), px(size))
        else:
            if use_cjk:
                # Language-specific faces first (Japanese and Korean need
                # different fonts from Traditional Chinese), then the usual
                # Latin fallbacks for digits and formulas.
                sys_names = CJK_FONTS.get(language, "notosans") + "," + sys_names
            font = _system_font(sys_names, px(size), bold=(kind == "bold"))
        _font_cache[key] = font
    return font


def draw_text(surface, text, pos, size=16, color=config.TEXT, kind="ui", anchor="topleft"):
    from .i18n import translate
    text = translate(text)
    img = get_font(size, kind, cjk=_needs_cjk_font(text)).render(text, True, color)
    rect = img.get_rect(**{anchor: pos})
    surface.blit(img, rect)
    return rect


def fit_text(text, max_width, size=16, kind="ui"):
    """`text` shortened with an ellipsis so it fits into `max_width` pixels.

    Used for labels that come from the outside (level names, uploader names)
    and must not spill out of their panel.  The cut is estimated first, so a
    long name does not need one font measurement per character.
    """
    from .i18n import translate
    text = translate("" if text is None else str(text))
    if max_width <= 0:
        return ""
    font = get_font(size, kind, cjk=_needs_cjk_font(text))
    width = font.size(text)[0]
    if width <= max_width:
        return text
    ellipsis = "…"
    ellipsis_width = font.size(ellipsis)[0]
    if ellipsis_width > max_width:
        return ""
    keep = max(1, int(len(text) * max_width / width))
    trimmed = text[:keep]
    while trimmed and font.size(trimmed)[0] + ellipsis_width > max_width:
        trimmed = trimmed[:-1]
    while len(trimmed) < len(text) and font.size(text[:len(trimmed) + 1])[0] + ellipsis_width <= max_width:
        trimmed = text[:len(trimmed) + 1]
    return trimmed + ellipsis


def wrap_text(text, size, max_width, kind="ui"):
    """Split `text` into lines no wider than `max_width` real pixels (word wrap).

    A single word wider than `max_width` keeps a line of its own.
    """
    from .i18n import translate
    text = translate(text)
    cjk = _needs_cjk_font(text)
    font = get_font(size, kind, cjk=cjk)
    lines, line = [], ""
    # CJK languages do not use spaces between words, so split them at
    # characters rather than returning one over-wide unbreakable line.
    words = list(text) if cjk else text.split()
    for word in words:
        trial = f"{line}{word}" if cjk or not line else f"{line} {word}"
        if line and font.size(trial)[0] > max_width:
            lines.append(line)
            line = word
        else:
            line = trial
    if line:
        lines.append(line)
    return lines


COIN_GOLD = (240, 190, 60)         # stand-in disc when a coin picture is missing


def _icon(key, side):
    """The picture for ``key`` at ``side`` x ``side`` real px, or a plain gold disc."""
    from .image_assets import load_image
    img = load_image(key, size_px=(side, side))
    if img is None:
        img = pygame.Surface((side, side), pygame.SRCALPHA)
        pygame.draw.circle(img, COIN_GOLD, (side / 2, side / 2), side / 2)
    return img


def draw_icon_row(surface, parts, pos, size=16, kind="bold", anchor="topleft", gap=5):
    """Draw text pieces and icons side by side, placed together by ``anchor``.

    ``parts`` holds ``(text, color)`` pairs and image keys (str) for icons,
    which are drawn at the font's height.  Returns the rect of the whole row.
    """
    from .i18n import translate
    cjk = any(_needs_cjk_font(translate(p[0])) for p in parts if not isinstance(p, str))
    font = get_font(size, kind, cjk=cjk)
    side = font.get_height()
    pieces = [_icon(p, side) if isinstance(p, str) else font.render(str(translate(p[0])), True, p[1])
              for p in parts]
    space = px(gap)
    rect = pygame.Rect(0, 0, sum(s.get_width() for s in pieces) + space * (len(pieces) - 1),
                       max((s.get_height() for s in pieces), default=0))
    setattr(rect, anchor, pos)
    x = rect.x
    for s in pieces:
        surface.blit(s, s.get_rect(midleft=(x, rect.centery)))
        x += s.get_width() + space
    return rect


def draw_coins(surface, amount, pos, size=16, color=config.TEXT, icon=None, kind="bold",
               anchor="topleft"):
    """A coin picture followed by ``amount``; coin_2 (prices, rewards) unless ``icon``."""
    from .image_assets import COIN_TRADE
    from . import ui as _ui
    return _ui.draw_icon_row(surface, [icon or COIN_TRADE, (amount, color)], pos, size, kind, anchor)


def coin_price_parts(price, available, lead="Price", color=config.TEXT):
    """Icon row parts: ``lead`` and the price (coin_2), then what the player has (coin_1).

    The price turns red when the player can't afford it.
    """
    from .image_assets import COIN_BALANCE, COIN_TRADE
    return [(lead, color), COIN_TRADE, (price, config.DANGER if price > available else color),
            ("· You have", color), COIN_BALANCE, (available, color)]


def draw_panel_box(surface, rect, fill=config.PANEL_BG, edge=config.PANEL_EDGE, radius=4):
    pygame.draw.rect(surface, fill, rect, border_radius=px(radius))
    pygame.draw.rect(surface, edge, rect, width=max(1, px(1)), border_radius=px(radius))


class Button:
    """Flat button (VS Code style)."""
    STYLES = {
        "primary": (config.BUTTON_PRIMARY, config.BUTTON_PRIMARY_HOVER),
        "danger": (config.BUTTON_DANGER, config.BUTTON_DANGER_HOVER),
        "plain": (config.BUTTON_PLAIN, config.BUTTON_PLAIN_HOVER),
    }

    def __init__(self, rect, label, style="primary", font_size=18):
        self.rect = pygame.Rect(rect)
        self.label = label
        self.style = style
        self.font_size = font_size
        self.enabled = True
        self.hover = False
        self.price = None           # coins it costs, shown after the label with coin_2
        self.price_short = False    # the player can't afford it: the price turns red

    def handle_event(self, event):
        """Return 'click', 'disabled' (clicked while disabled) or None."""
        if event.type == pygame.MOUSEMOTION:
            self.hover = self.rect.collidepoint(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                return "click" if self.enabled else "disabled"
        return None

    def draw(self, surface):
        bg, hover_bg = self.STYLES[self.style]
        text_color = (255, 255, 255)
        if not self.enabled:
            bg, text_color = config.BUTTON_DISABLED, config.TEXT_FAINT
        elif self.hover:
            bg = hover_bg
        pygame.draw.rect(surface, bg, self.rect, border_radius=px(3))
        if not self.enabled:
            pygame.draw.rect(surface, config.PANEL_EDGE, self.rect, width=max(1, px(1)), border_radius=px(3))
        if self.price is None:
            from . import ui as _ui
            _ui.draw_text(surface, self.label, self.rect.center, self.font_size, text_color,
                      kind="bold", anchor="center")
            return
        from .image_assets import COIN_TRADE
        price_color = config.DANGER if self.price_short else text_color
        from . import ui as _ui
        _ui.draw_icon_row(surface, [(self.label, text_color), COIN_TRADE, (self.price, price_color)],
                      self.rect.center, self.font_size, anchor="center")








__all__ = ['Button', 'COIN_GOLD', '_FONT_CHOICES', '_font_cache', '_icon', 'coin_price_parts', 'config', 'draw_coins', 'draw_icon_row', 'draw_panel_box', 'draw_text', 'fit_text', 'get_font', 'px', 'pygame', 're', 'warnings', 'wrap_text']
