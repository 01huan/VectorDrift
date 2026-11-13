"""The Windows launcher keeps the bits cmd.exe depends on."""

import os
import re
from pathlib import Path

LAUNCHER = Path(__file__).resolve().parent.parent / "run.bat"


def _text():
    return LAUNCHER.read_text(encoding="utf-8")


def test_launcher_ships_with_the_project():
    assert LAUNCHER.is_file()


def test_launcher_is_plain_ascii_without_a_bom():
    raw = LAUNCHER.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")       # a BOM breaks cmd.exe
    assert all(byte < 128 for byte in raw)            # no code page surprises


def test_launcher_uses_crlf_line_endings():
    if os.name != "nt":
        return
    raw = LAUNCHER.read_bytes()
    assert raw.count(b"\r\n") == raw.count(b"\n")    # no bare LF


def test_launcher_probes_the_common_python_commands():
    text = _text()
    for candidate in ("py -3", "python", "python3"):
        assert f"call :try_python {candidate}" in text


def test_launcher_requires_python_311_or_newer():
    assert "version_info >= (3,11)" in _text()


def test_launcher_prepares_a_private_environment_and_the_dependencies():
    text = _text()
    assert "-m venv --system-site-packages" in text
    assert "import pygame, numpy, supabase, dotenv" in text
    assert "pip install" in text
    for package in ("pygame", "numpy", "supabase", "python-dotenv"):
        assert package in text


def test_launcher_installs_only_the_missing_packages():
    text = _text()
    assert '-c "import %~1"' in text         # skips packages that already import
    assert "pygame-ce" in text               # fallback for Pythons without wheels


def test_launcher_starts_the_game_and_reports_failures():
    text = _text()
    assert '"%PY_RUN%" main.py %*' in text
    assert "pause" in text                            # keep the window open on error


def test_launcher_quotes_the_interpreter_path():
    # An interpreter below "C:\\Program Files\\..." only runs when it is quoted.
    text = _text()
    assert not re.findall(r'^\s*%(?:PY_RUN|PY_EXE|PY_READY|VENV_PY)%\s', text, re.M)
    for variable in ("%PY_RUN%", "%PY_EXE%", "%VENV_PY%"):
        assert f'"{variable}"' in text


def test_launcher_calls_the_candidate_interpreter():
    # A python.bat wrapper ends the script when it returns without "call".
    text = _text()
    assert "call %* -c" in text
    assert not re.search(r'^\s*%\*\s+-c', text, re.M)


def test_launcher_never_builds_a_package_from_source_first():
    # Building pygame from source takes minutes and fails on the newest
    # Pythons, so a wheel is always tried before a source build.
    text = _text()
    assert "--only-binary=:all:" in text
    assert ":pip_install --only-binary=:all: pygame" in text
    assert ":pip_install --only-binary=:all: pygame-ce" in text


def test_launcher_keeps_the_test_dependencies_optional():
    # pytest is only needed for the test suite, so it must never block the game.
    text = _text()
    assert '-c "import pytest"' in text
    optional = text.index('-c "import pytest"')
    assert text.index("deps_failed") > optional


def test_launcher_explains_a_missing_pip():
    assert ":no_pip" in _text()
