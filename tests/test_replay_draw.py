import pygame

from vector_drift.scenes.replay import ReplayScene
from vector_drift.scenes.base import SceneManager
from vector_drift import audio


def test_replay_draw_with_records():
    pygame.display.set_mode((1280, 720))
    pygame.font.init()
    pygame.mixer.init()
    mgr = SceneManager(audio)
    mgr.session.replays = [
        {
            "level_id": 1,
            "ship_id": "ship01",
            "fx_text": "0",
            "fy_text": "0",
            "outcome": "timeout",
            "seed": 123,
            "frames": [
                {"t": 0, "x": -7, "y": 0, "vx": 0, "vy": 0, "fx": 0, "fy": 0},
                {"t": 1, "x": -6, "y": 0, "vx": 1, "vy": 0, "fx": 0, "fy": 0},
            ],
        }
    ]
    scene = ReplayScene(mgr)
    surf = pygame.Surface((1280, 720))
    scene.draw(surf)
    assert True
