import os
import gc

import pytest

# Run headless at 1x scale (config reads these when first imported).
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")


@pytest.fixture(autouse=True)
def guest_save_in_tmp(tmp_path, monkeypatch):
    """Keep the guest save file out of the real home folder."""
    from vector_drift.account import local_profile_manager
    monkeypatch.setattr(local_profile_manager, "_storage_path", lambda: tmp_path / "guest_profile.json")


@pytest.fixture(autouse=True)
def no_solver(monkeypatch, request):
    """Keep the heavy offline AI solver (PSO + process pool) out of scene tests."""
    from types import SimpleNamespace

    module_name = getattr(getattr(request, "module", None), "__name__", "")
    if "solver_lifecycle" in module_name:
        yield []
        return

    calls = []

    def fake_run(solver, level, **kwargs):
        calls.append(getattr(level, "id", None))
        return SimpleNamespace(running=True, cancel=lambda: None, error=None, result=None)

    from vector_drift.scenes import game as game_module
    monkeypatch.setattr(game_module, "run_solver_async", fake_run)
    yield calls


@pytest.fixture(scope="module")
def pygame_display():
    """pygame with a tiny display for one test module."""
    import pygame
    from vector_drift import ui
    ui._font_cache.clear()
    pygame.init()
    pygame.display.set_mode((1, 1))
    yield
    ui._font_cache.clear()
    pygame.quit()


@pytest.fixture(autouse=True)
def _collect_garbage_after_test():
    """Reclaim scenes/solvers promptly so background work cannot accumulate."""
    yield
    gc.collect()
