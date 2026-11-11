"""Painting the code editor widget (header, code lines, problems, footer)."""

import pygame

from . import config
from .config import px
from .ui_fonts import get_font, draw_text
from .ui_editor_syntax import _dim, draw_squiggle, error_span, highlight


class CodeEditorDrawMixin:

    def update(self, dt):
        self._blink += dt

    def _keep_cursor_visible(self, i):
        area = self.text_area(i)
        cx = self.font.size(self.lines[i][: self.col])[0]
        if cx - self._scroll[i] > area.w - px(2):
            self._scroll[i] = cx - area.w + px(2)
        elif cx < self._scroll[i]:
            self._scroll[i] = cx
        text_w = self.font.size(self.lines[i])[0]
        self._scroll[i] = max(0, min(self._scroll[i], max(0, text_w - area.w + px(2))))

    def draw(self, surface):
        r = self.rect
        active = self.enabled and self.focused
        pygame.draw.rect(surface, config.EDITOR_BG, r)
        self._draw_header(surface, active)
        for i in range(self.n):
            self._draw_line(surface, i, active and i == self.line)
        self._draw_problems(surface)
        if self.footer_title:
            f = self.footer_rect
            pygame.draw.line(surface, config.EDITOR_BORDER, f.topleft, (f.right - 1, f.top), max(1, px(1)))
            draw_text(surface, self.footer_title, (f.x + px(10), f.y + self.PROB_HEADER_H // 2 + px(1)), 11,
                      config.TEXT_DIM, kind="bold", anchor="midleft")
        pygame.draw.rect(surface, config.EDITOR_BORDER, r, max(1, px(1)))

    def _draw_header(self, surface, active):
        """Title bar; its right end is left free for a run/stop button."""
        bar = self.header_rect
        pygame.draw.rect(surface, config.EDITOR_TABBAR, bar)
        pygame.draw.line(surface, config.ACCENT if active else config.EDITOR_GUTTER,
                         bar.topleft, (bar.right - 1, bar.top), max(2, px(2)))
        icon = self.small_mono.render("{}", True, config.SYN_NUMBER)
        label = get_font(13).render(self.title, True, config.TEXT if self.enabled else config.TEXT_DIM)
        surface.blit(icon, icon.get_rect(midleft=(bar.x + px(10), bar.centery)))
        surface.blit(label, label.get_rect(midleft=(bar.x + px(16) + icon.get_width(), bar.centery)))

    def _draw_line(self, surface, i, is_cur):
        lr = self.line_rect(i)
        if is_cur:
            pygame.draw.rect(surface, config.EDITOR_LINE_HL, lr)
        num_color = config.EDITOR_GUTTER_ACTIVE if is_cur else config.EDITOR_GUTTER
        draw_text(surface, str(i + 1), (lr.x + self.GUTTER_W - px(6), lr.centery), 14, num_color,
                  kind="mono", anchor="midright")

        def fade(c):
            return c if self.enabled else _dim(c, 0.55)

        x = lr.x + self.GUTTER_W + self.TEXT_PAD
        for chunk, color in ((self.prefixes[i], config.SYN_KEYWORD), (" = ", config.SYN_OPERATOR)):
            img = self.font.render(chunk, True, fade(color))
            surface.blit(img, img.get_rect(midleft=(x, lr.centery)))
            x += img.get_width()

        area = self.text_area(i)
        if is_cur:
            self._keep_cursor_visible(i)
        scroll = self._scroll[i]
        prev_clip = surface.get_clip()
        surface.set_clip(area.clip(prev_clip))
        text = self.lines[i]
        sel = self.selection() if i == self.line and self.enabled else None
        if sel:
            x0 = area.x - scroll + self.font.size(text[: sel[0]])[0]
            x1 = area.x - scroll + self.font.size(text[: sel[1]])[0]
            pygame.draw.rect(surface, config.EDITOR_SELECTION,
                             (x0, lr.y + px(4), x1 - x0, lr.h - px(8)))
        if text:
            cx = area.x - scroll
            for chunk, color in highlight(text):
                img = self.font.render(chunk, True, fade(color))
                surface.blit(img, img.get_rect(midleft=(cx, lr.centery)))
                cx += img.get_width()
        elif not is_cur:
            img = self.font.render("0", True, config.EDITOR_GUTTER)
            surface.blit(img, img.get_rect(midleft=(area.x, lr.centery)))

        err = self.errors[i]
        if err and self.enabled:
            start, end = error_span(text, err[1])
            x0 = area.x - scroll + self.font.size(text[:start])[0]
            if end <= len(text):
                x1 = area.x - scroll + self.font.size(text[:end])[0]
            else:
                x1 = area.x - scroll + self.font.size(text)[0] + self.font.size("0")[0]
            draw_squiggle(surface, x0, x1, lr.bottom - px(6))

        if is_cur and (self._blink % 1.0) < 0.55:
            cx = area.x - scroll + self.font.size(text[: self.col])[0]
            pygame.draw.line(surface, config.EDITOR_CURSOR, (cx, lr.y + px(5)), (cx, lr.bottom - px(6)),
                             max(2, px(2)))
        surface.set_clip(prev_clip)

    def _draw_problems(self, surface):
        r = self.rect
        top = self.body.bottom
        pygame.draw.line(surface, config.EDITOR_BORDER, (r.x, top), (r.right - 1, top), max(1, px(1)))
        head = draw_text(surface, "PROBLEMS", (r.x + px(10), top + self.PROB_HEADER_H // 2 + px(1)), 11,
                         config.TEXT_DIM, kind="bold", anchor="midleft")
        listed = [(i, e) for i, e in enumerate(self.errors) if e] if self.enabled else []
        if not listed:
            pr = self.problem_rect(0)
            ok = (pr.x + px(16), pr.centery)
            check = [(ok[0] - px(4), ok[1]), (ok[0] - px(1), ok[1] + px(3)), (ok[0] + px(4), ok[1] - px(3))]
            pygame.draw.lines(surface, config.SUCCESS, False, check, max(2, px(2)))
            draw_text(surface, "No problems", (pr.x + px(28), pr.centery), 12, config.TEXT_DIM, anchor="midleft")
            return

        badge = (head.right + px(12), head.centery)
        pygame.draw.circle(surface, config.SQUIGGLE, badge, px(7))
        draw_text(surface, str(len(listed)), badge, 11, (255, 255, 255), kind="bold", anchor="center")
        for k, (i, (msg, pos)) in enumerate(listed):
            pr = self.problem_rect(k)
            ic = (pr.x + px(16), pr.centery)
            d, lw = px(2), max(1, px(1))
            pygame.draw.circle(surface, config.SQUIGGLE, ic, px(5))
            pygame.draw.line(surface, (255, 255, 255), (ic[0] - d, ic[1] - d), (ic[0] + d, ic[1] + d), lw)
            pygame.draw.line(surface, (255, 255, 255), (ic[0] - d, ic[1] + d), (ic[0] + d, ic[1] - d), lw)
            loc = self.small_mono.render(f"Ln {i + 1}  ", True, config.EDITOR_GUTTER)
            surface.blit(loc, loc.get_rect(midleft=(pr.x + px(28), pr.centery)))
            text_x = pr.x + px(28) + loc.get_width()
            room = pr.right - px(8) - text_x
            size = 12
            while size > 9 and get_font(size).size(msg)[0] > room:
                size -= 1
            draw_text(surface, msg, (text_x, pr.centery), size, config.TEXT, anchor="midleft")
