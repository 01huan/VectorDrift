import pygame
import pytest

from vector_drift.scenes.auth import _TextInput
from vector_drift import config

pytestmark = pytest.mark.usefixtures("pygame_display")


def test_textinput_keydown_branches():
    inp = _TextInput((0, 0, 100, 30))
    inp.active = True
    inp.text = "abc"
    inp.cursor = 1
    surface = pygame.Surface((config.WINDOW_W, config.WINDOW_H))
    keys = [
        pygame.K_BACKSPACE, pygame.K_DELETE, pygame.K_LEFT, pygame.K_RIGHT,
        pygame.K_HOME, pygame.K_END, pygame.K_TAB, pygame.K_KP0, pygame.K_KP1,
        pygame.K_KP_PERIOD,
    ]
    for k in keys:
        inp.handle_event(pygame.event.Event(pygame.KEYDOWN, key=k, mod=0, unicode=""))
    # ctrl combos
    for k in (pygame.K_c, pygame.K_v, pygame.K_x, pygame.K_a):
        inp.handle_event(pygame.event.Event(pygame.KEYDOWN, key=k, mod=pygame.KMOD_CTRL, unicode=""))
    # printable
    inp.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_a, mod=0, unicode="z"))
    # up/down
    inp.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_UP, mod=0, unicode=""))
    inp.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_DOWN, mod=0, unicode=""))
    inp.draw(surface)
