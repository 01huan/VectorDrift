"""The Linux/macOS launchers keep the bits /bin/sh depends on."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LAUNCHER = ROOT / "run.sh"
MAC_LAUNCHER = ROOT / "run.command"


def _text(path=LAUNCHER):
    return path.read_text(encoding="utf-8")


def test_launchers_ship_with_the_project():
    assert LAUNCHER.is_file()
    assert MAC_LAUNCHER.is_file()


def test_launchers_are_plain_ascii_without_a_bom():
    for path in (LAUNCHER, MAC_LAUNCHER):
        raw = path.read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf")       # a BOM breaks /bin/sh
        assert all(byte < 128 for byte in raw)            # no encoding surprises


def test_launchers_use_lf_line_endings():
    # A CRLF shebang ("#!/bin/sh\r") is not a valid interpreter on Linux/macOS.
    for path in (LAUNCHER, MAC_LAUNCHER):
        assert b"\r\n" not in path.read_bytes()


def test_launchers_start_with_a_shebang():
    assert _text().startswith("#!/bin/sh\n")
    assert _text(MAC_LAUNCHER).startswith("#!/bin/sh\n")


def test_mac_launcher_runs_the_shell_launcher():
    # macOS opens .sh files in a text editor, so run.command is the entry
    # point there; it must not duplicate the launcher logic.
    text = _text(MAC_LAUNCHER)
    assert "run.sh" in text
    assert "exec " in text


def test_launcher_probes_the_common_python_commands():
    text = _text()
    assert "for cmd in python3 python python3.13 python3.12 python3.11; do" in text


def test_launcher_requires_python_311_or_newer():
    assert "version_info >= (3, 11)" in _text()


def test_launcher_prepares_a_private_environment_and_the_dependencies():
    text = _text()
    assert "-m venv --system-site-packages" in text
    assert "import pygame, numpy, supabase, dotenv" in text
    assert "pip install" in text
    for package in ("pygame", "numpy", "supabase", "python-dotenv"):
        assert package in text


def test_launcher_installs_only_the_missing_packages():
    text = _text()
    assert '-c "import $1"' in text         # skips packages that already import
    assert "pygame-ce" in text               # fallback for Pythons without wheels


def test_launcher_starts_the_game_and_reports_failures():
    text = _text()
    assert '"$PY_RUN" main.py "$@"' in text
    assert "pause" in text                   # keep the terminal open on error


def test_launcher_quotes_the_interpreter_path():
    # An interpreter below "/usr/local/bin" only runs when it is quoted.
    text = _text()
    for variable in ("$PY_RUN", "$PY_EXE", "$PY_READY", "$VENV_PY"):
        assert f'"{variable}"' in text


def test_launcher_never_builds_a_package_from_source_first():
    # Building pygame from source takes minutes and fails on the newest
    # Pythons, so a wheel is always tried before a source build.
    text = _text()
    assert "--only-binary=:all:" in text
    assert "pip_install --only-binary=:all: pygame" in text
    assert "pip_install --only-binary=:all: pygame-ce" in text


def test_launcher_keeps_the_test_dependencies_optional():
    # pytest is only needed for the test suite, so it must never block the game.
    text = _text()
    assert '-c "import pytest"' in text
    optional = text.index('-c "import pytest"')
    assert text.index("Could not install the dependencies") > optional


def test_launcher_explains_a_missing_pip():
    assert "pip is not available for this Python installation" in _text()


def test_launcher_explains_a_missing_python():
    assert "Python 3.11 or newer was not found" in _text()
