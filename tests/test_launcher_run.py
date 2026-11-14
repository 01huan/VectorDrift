"""The launchers are executed for real: they must start the game with its
arguments and report a folder that is not the project.

The checks in test_launcher.py / test_launcher_unix.py only read the source.
These tests run the scripts with an interpreter that already has the game
dependencies, so the fast path is taken and nothing is ever downloaded or
installed.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

STUB_MAIN = (
    "import json, sys, pathlib\n"
    "pathlib.Path('argv.json').write_text(json.dumps(sys.argv[1:]))\n"
)


def _shell():
    """A POSIX shell that can run run.sh, or None when there is none."""
    if os.name == "nt":
        for path in (r"C:\Program Files\Git\bin\bash.exe",
                     r"C:\Program Files\Git\usr\bin\bash.exe"):
            if Path(path).is_file():
                return path
        return None
    return shutil.which("sh")


def _interpreter():
    """A Python 3.11+ that already has the game dependencies, or None.

    The launcher only downloads something when no interpreter has them, so
    the tests skip themselves instead of hitting the network.
    """
    for name in ("python3", "python", "python3.13", "python3.12", "python3.11"):
        exe = shutil.which(name)
        if not exe:
            continue
        try:
            probe = subprocess.run(
                [exe, "-c", "import sys; print(sys.version_info >= (3, 11))"],
                capture_output=True, text=True, timeout=60,
                stdin=subprocess.DEVNULL)
            if probe.stdout.strip() != "True":
                continue
            deps = subprocess.run(
                [exe, "-c", "import pygame, numpy, supabase, dotenv"],
                capture_output=True, timeout=120,
                stdin=subprocess.DEVNULL)
        except (OSError, subprocess.SubprocessError):
            continue
        if deps.returncode == 0:
            return exe
    return None


@pytest.fixture
def project(tmp_path):
    """A folder with the launcher, a stub main.py and a requirements.txt."""
    (tmp_path / "main.py").write_text(STUB_MAIN, encoding="utf-8")
    (tmp_path / "requirements.txt").write_text("pygame>=2.5\n", encoding="utf-8")
    return tmp_path


def _argv(folder):
    """The arguments the stub main.py was started with."""
    return json.loads((folder / "argv.json").read_text(encoding="utf-8"))


@pytest.mark.skipif(_shell() is None, reason="no POSIX shell available")
@pytest.mark.skipif(_interpreter() is None, reason="no Python with the game dependencies")
def test_run_sh_starts_the_game_with_its_arguments(project):
    shutil.copy(ROOT / "run.sh", project / "run.sh")

    result = subprocess.run(
        [_shell(), "./run.sh", "--demo", "arg"],
        cwd=project, capture_output=True, text=True, timeout=300,
        stdin=subprocess.DEVNULL,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert _argv(project) == ["--demo", "arg"]
    assert not (project / ".venv").exists(), "a private environment was not needed"


@pytest.mark.skipif(_shell() is None, reason="no POSIX shell available")
def test_run_sh_reports_a_folder_that_is_not_the_project(project):
    (project / "main.py").unlink()
    shutil.copy(ROOT / "run.sh", project / "run.sh")

    result = subprocess.run(
        [_shell(), "./run.sh"],
        cwd=project, capture_output=True, text=True, timeout=120,
        stdin=subprocess.DEVNULL,
    )

    assert result.returncode == 1
    assert "main.py or requirements.txt is missing" in result.stdout


@pytest.mark.skipif(os.name != "nt", reason="run.bat is the Windows launcher")
@pytest.mark.skipif(_interpreter() is None, reason="no Python with the game dependencies")
def test_run_bat_starts_the_game_with_its_arguments(project):
    shutil.copy(ROOT / "run.bat", project / "run.bat")

    result = subprocess.run(
        ["cmd", "/c", "run.bat", "--demo", "arg"],
        cwd=project, capture_output=True, text=True, timeout=300,
        stdin=subprocess.DEVNULL,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert _argv(project) == ["--demo", "arg"]
    assert not (project / ".venv").exists(), "a private environment was not needed"


@pytest.mark.skipif(os.name != "nt", reason="run.bat is the Windows launcher")
def test_run_bat_reports_a_folder_that_is_not_the_project(project):
    (project / "main.py").unlink()
    shutil.copy(ROOT / "run.bat", project / "run.bat")

    result = subprocess.run(
        ["cmd", "/c", "run.bat"],
        cwd=project, capture_output=True, text=True, timeout=120,
        stdin=subprocess.DEVNULL,
    )

    assert result.returncode == 1
    assert "main.py or requirements.txt is missing" in result.stdout


@pytest.mark.skipif(os.name != "nt", reason="run.bat is the Windows launcher")
def test_run_bat_restores_the_console_code_page(project):
    # The launcher switches the console to UTF-8 for the output of the game;
    # a shared console has to be left as it was found.
    shutil.copy(ROOT / "run.bat", project / "run.bat")
    before = subprocess.run(["cmd", "/c", "chcp"], capture_output=True, text=True,
                            stdin=subprocess.DEVNULL)

    subprocess.run(
        ["cmd", "/c", "run.bat"],
        cwd=project, capture_output=True, text=True, timeout=300,
        stdin=subprocess.DEVNULL,
    )

    after = subprocess.run(["cmd", "/c", "chcp"], capture_output=True, text=True,
                           stdin=subprocess.DEVNULL)
    assert after.stdout.strip() == before.stdout.strip()
