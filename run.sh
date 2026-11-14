#!/bin/sh
# ============================================================================
#  Vector Drift - one-click launcher for Linux and macOS
#
#  Run this file to start the game (on macOS double-click run.command).
#
#  1. Finds a Python 3.11+ interpreter (python3, python, python3.13, ...)
#  2. Uses it right away when the dependencies are already installed
#  3. Otherwise creates a private .venv and installs what is missing
#  4. Starts main.py and keeps this terminal open when something fails
#
#  Every failure is handled explicitly, so "set -e" can be added safely.
# ============================================================================
set -u

export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8
export PIP_DISABLE_PIP_VERSION_CHECK=1

# Filled in below: the interpreter that runs the game, the one that was
# found first, and whether it lives in the private .venv.
PY_RUN=""
PY_EXE=""
PY_READY=""
IN_VENV=""

# --- keep the terminal open when something fails -----------------------------
# Only when the script owns the terminal: a piped or automated run must not
# wait for a key press.
pause() {
    if [ -t 0 ]; then
        printf "\nPress Enter to close this window..."
        read -r _ignored || true
        printf "\n"
    fi
}

# --- pip install, with a --user retry when the environment is not writable --
# $@ = arguments for pip install
pip_install() {
    "$PY_RUN" -m pip install "$@" && return 0
    if [ -n "$IN_VENV" ]; then
        return 1
    fi
    "$PY_RUN" -m pip install --user "$@"
}

# --- Install a package unless its module already imports --------------------
# $1 = module name, $2 = package name on PyPI
# A wheel is tried first because it is fast; the source build is the
# fallback for the Pythons that have no prebuilt wheel.
need_package() {
    "$PY_RUN" -c "import $1" >/dev/null 2>&1 && return 0
    echo "[setup] Installing $2 ..."
    pip_install --only-binary=:all: "$2" && return 0
    pip_install "$2"
    return 0
}

# --- pygame needs its own rule: the official package has no wheels for the
# --- newest Python releases, so fall back to its maintained drop-in fork ---
need_pygame() {
    "$PY_RUN" -c "import pygame" >/dev/null 2>&1 && return 0
    echo "[setup] Installing pygame ..."
    pip_install --only-binary=:all: pygame && return 0
    echo "[setup] Trying pygame-ce instead ..."
    pip_install --only-binary=:all: pygame-ce && return 0
    echo "[setup] Trying pygame-ce without a prebuilt wheel ..."
    pip_install pygame-ce
    return 0
}

# --- Accept a candidate interpreter only if it is a real Python 3.11+ -------
# $@ = the candidate command, for example "python3" or "python3.12".
# The Microsoft Store stub and Python 2 both fail this test.
# Always returns 0: a rejected candidate is a normal outcome, not an error.
try_python() {
    "$@" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >/dev/null 2>&1 || return 0
    found_exe=$("$@" -c "import sys; print(sys.executable)" 2>/dev/null) || return 0
    [ -n "$found_exe" ] || return 0
    if [ -z "$PY_EXE" ]; then
        PY_EXE=$found_exe
    fi
    "$@" -c "import pygame, numpy, supabase, dotenv" >/dev/null 2>&1 || return 0
    if [ -z "$PY_READY" ]; then
        PY_READY=$found_exe
    fi
    return 0
}

# --- remove the private environment ------------------------------------------
# Only ever the .venv inside this folder: the path is checked before the
# directory is deleted, so a wrong $SCRIPT_DIR cannot wipe something else.
# $1 = the .venv directory
remove_venv() {
    if [ "$1" = "$SCRIPT_DIR/.venv" ]; then
        rm -rf "$1"
    else
        echo "[setup] Refusing to remove $1 - keeping it."
    fi
}

# --- always work inside the folder of this file (spaces in the path are OK) ---
SCRIPT_DIR=$(CDPATH= cd "$(dirname "$0")" && pwd -P)
if [ -z "$SCRIPT_DIR" ] || ! cd "$SCRIPT_DIR"; then
    echo ""
    echo "[ERROR] Cannot open the VectorDrift folder."
    pause
    exit 1
fi

if [ ! -f main.py ] || [ ! -f requirements.txt ]; then
    echo ""
    echo "[ERROR] main.py or requirements.txt is missing."
    echo "        Keep this file inside the VectorDrift folder."
    pause
    exit 1
fi

echo "=============================================="
echo " Vector Drift"
echo "=============================================="
echo ""

# ---------------------------------------------------------------------------
# 1. Locate a Python interpreter (3.11 or newer)
#    PY_EXE   = first usable interpreter
#    PY_READY = first usable interpreter that already has every dependency
# ---------------------------------------------------------------------------
for cmd in python3 python python3.13 python3.12 python3.11; do
    try_python "$cmd"
    if [ -n "$PY_READY" ]; then
        break
    fi
done

if [ -n "$PY_READY" ]; then
    PY_RUN="$PY_READY"
    echo "[setup] Using the system Python: $PY_RUN"
else
    if [ -z "$PY_EXE" ]; then
        echo ""
        echo "[ERROR] Python 3.11 or newer was not found on this system."
        echo ""
        echo "  1. Install Python from https://www.python.org/downloads/"
        echo "     (Debian/Ubuntu: sudo apt install python3 python3-venv)"
        echo "     (Fedora: sudo dnf install python3 python3-pip)"
        echo "  2. Run this file again."
        echo ""
        pause
        exit 1
    fi

    # -----------------------------------------------------------------------
    # 2. Private environment (.venv): reuse it, rebuild it, or create it
    #    --system-site-packages reuses the packages the system already has.
    # -----------------------------------------------------------------------
    VENV_DIR="$SCRIPT_DIR/.venv"
    VENV_PY="$VENV_DIR/bin/python"

    if [ -x "$VENV_PY" ]; then
        if ! "$VENV_PY" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >/dev/null 2>&1; then
            echo "[setup] The existing .venv cannot be used - rebuilding it ..."
            remove_venv "$VENV_DIR"
        fi
    fi

    if [ ! -x "$VENV_PY" ]; then
        echo "[setup] Creating a private environment in .venv ..."
        if ! "$PY_EXE" -m venv --system-site-packages "$VENV_DIR"; then
            echo "[setup] Could not create .venv - falling back to the system Python."
            remove_venv "$VENV_DIR"
        fi
    fi

    if [ -x "$VENV_PY" ]; then
        IN_VENV=1
        PY_RUN="$VENV_PY"
        echo "[setup] Using the private environment: $PY_RUN"
    else
        PY_RUN="$PY_EXE"
        echo "[setup] Using the system Python: $PY_RUN"
    fi
fi

# ---------------------------------------------------------------------------
# 3. Dependencies
# ---------------------------------------------------------------------------
if "$PY_RUN" -c "import pygame, numpy, supabase, dotenv" >/dev/null 2>&1; then
    echo "[setup] All dependencies are already installed."
else
    if ! "$PY_RUN" -m pip --version >/dev/null 2>&1; then
        echo "[setup] pip is missing - bootstrapping it with ensurepip ..."
        if ! "$PY_RUN" -m ensurepip --upgrade >/dev/null 2>&1; then
            echo ""
            echo "[ERROR] pip is not available for this Python installation."
            echo "        Reinstall Python with the \"pip\" option ticked, or install pip"
            echo "        manually, then run this file again."
            pause
            exit 1
        fi
    fi

    echo "[setup] Installing the dependencies from requirements.txt ..."
    # Wheels only: building pygame from source takes minutes and fails on the
    # newest Pythons, so the packages are installed one by one further down.
    pip_install --only-binary=:all: -r requirements.txt
    # The pinned set can fail when one package has no wheel, so every module
    # that is still missing is installed on its own.
    need_pygame
    need_package numpy numpy
    need_package supabase supabase
    need_package dotenv python-dotenv
    # pytest is only needed for the test suite - never block the game on it,
    # and never install it into the user's own Python.
    if [ -n "$IN_VENV" ] && ! "$PY_RUN" -c "import pytest" >/dev/null 2>&1; then
        pip_install --only-binary=:all: pytest
    fi

    if ! "$PY_RUN" -c "import pygame, numpy, supabase, dotenv" >/dev/null 2>&1; then
        echo ""
        echo "[ERROR] Could not install the dependencies."
        echo "        Check the internet connection and run this file again."
        echo "        If your Python is managed by the system (Debian and Ubuntu"
        echo "        mark it EXTERNALLY-MANAGED), install the packages by hand"
        echo "        with 'pip install --user -r requirements.txt', or remove that"
        echo "        marker, then run this file again."
        pause
        exit 1
    fi
fi

# ---------------------------------------------------------------------------
# 4. Start the game
# ---------------------------------------------------------------------------
echo ""
echo "[run] Starting Vector Drift ..."
echo ""
"$PY_RUN" main.py "$@"
EXIT_CODE=$?
if [ "$EXIT_CODE" -eq 0 ]; then
    exit 0
fi
echo ""
echo "[ERROR] The game stopped with exit code $EXIT_CODE."
pause
exit "$EXIT_CODE"
