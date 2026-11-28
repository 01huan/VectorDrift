import os
import gc

import pytest

# Run headless at 1x scale (config reads these when first imported).
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")


# Capture the pristine built-in level registry at import time so every test
# starts from the same clean state regardless of prior registration/reset.
from vector_drift import data as _data_module

_BASE_LEVELS = tuple(_data_module.LEVELS)
_BASE_CUSTOM_LEVELS = {}


@pytest.fixture(autouse=True)
def reset_custom_level_registries():
    """Keep the global custom-level registry from leaking across tests."""
    from vector_drift import data as data_module

    previous_levels = list(data_module.LEVELS)
    previous_custom = dict(data_module.CUSTOM_LEVELS)
    data_module.LEVELS[:] = list(_BASE_LEVELS)
    data_module.CUSTOM_LEVELS.clear()
    data_module.CUSTOM_LEVELS.update(_BASE_CUSTOM_LEVELS)

    yield

    data_module.LEVELS[:] = previous_levels
    data_module.CUSTOM_LEVELS.clear()
    data_module.CUSTOM_LEVELS.update(previous_custom)


@pytest.fixture(autouse=True)
def guest_save_in_tmp(tmp_path, monkeypatch):
    """Keep the guest save file out of the real home folder."""
    from vector_drift.account import local_profile_manager
    monkeypatch.setattr(local_profile_manager, "_storage_path", lambda: tmp_path / "guest_profile.json")


@pytest.fixture(autouse=True)
def isolate_i18n(tmp_path, monkeypatch):
    """Keep language tests independent of the machine locale and real settings.

    Tests run with a fresh English preference stored in a temp file, never
    reading or writing ~/.vector_drift/settings.json, and the module-level
    singleton is reset afterwards.  Tests that need another language patch
    i18n._preferences themselves.
    """
    from vector_drift import i18n
    settings = tmp_path / "vector_drift_settings.json"
    monkeypatch.setattr(i18n, "_settings_path", lambda: settings)
    monkeypatch.setattr(i18n, "_preferences",
                        i18n.LanguagePreferences(settings, system_locale=lambda: "en"))


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


def pytest_collection_finish(session):
    """Move everything loaded during collection out of the collector's reach.

    Modules, pygame and level data live for the whole run; freezing them keeps
    the per-test gc.collect() below from rescanning them after every test.
    """
    gc.collect()
    gc.freeze()


@pytest.fixture(autouse=True)
def _collect_garbage_after_test():
    """Reclaim scenes/solvers promptly so background work cannot accumulate."""
    yield
    gc.collect()
