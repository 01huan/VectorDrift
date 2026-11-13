"""Fonts and basic widgets: Button, CodeEditor."""

import re

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


def get_font(size, kind="ui"):
    """Font at a logical size (scaled to real pixels)."""
    key = (kind, size)
    font = _font_cache.get(key)
    if font is None:
        filename, sys_names = _FONT_CHOICES[kind]
        path = config.ASSETS_DIR / "fonts" / filename
        if path.exists():
            font = pygame.font.Font(str(path), px(size))
        else:
            font = pygame.font.SysFont(sys_names, px(size), bold=(kind == "bold"))
        _font_cache[key] = font
    return font


def draw_text(surface, text, pos, size=16, color=config.TEXT, kind="ui", anchor="topleft"):
    img = get_font(size, kind).render(text, True, color)
    rect = img.get_rect(**{anchor: pos})
    surface.blit(img, rect)
    return rect


def wrap_text(text, size, max_width, kind="ui"):
    """Split `text` into lines no wider than `max_width` real pixels (word wrap).

    A single word wider than `max_width` keeps a line of its own.
    """
    font = get_font(size, kind)
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}" if line else word
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
    font = get_font(size, kind)
    side = font.get_height()
    pieces = [_icon(p, side) if isinstance(p, str) else font.render(str(p[0]), True, p[1])
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








__all__ = ['Button', 'COIN_GOLD', '_FONT_CHOICES', '_font_cache', '_icon', 'coin_price_parts', 'config', 'draw_coins', 'draw_icon_row', 'draw_panel_box', 'draw_text', 'get_font', 'px', 'pygame', 're', 'wrap_text']
