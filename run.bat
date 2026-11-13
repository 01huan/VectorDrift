@echo off
rem ===========================================================================
rem  Vector Drift - one-click launcher for Windows
rem
rem  Double-click this file to start the game.
rem
rem  1. Finds a Python 3.11+ interpreter (py launcher, python, python3, ...)
rem  2. Uses it right away when the dependencies are already installed
rem  3. Otherwise creates a private .venv and installs what is missing
rem  4. Starts main.py and keeps this window open when something fails
rem ===========================================================================
setlocal EnableExtensions

chcp 65001 >nul 2>&1
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "PIP_DISABLE_PIP_VERSION_CHECK=1"
title Vector Drift

rem --- always work inside the folder of this file (spaces in the path are OK) ---
pushd "%~dp0"
if errorlevel 1 goto :folder_error

if not exist "main.py" goto :missing_files
if not exist "requirements.txt" goto :missing_files

echo ==============================================
echo  Vector Drift
echo ==============================================
echo.

rem ---------------------------------------------------------------------------
rem  1. Locate a Python interpreter (3.11 or newer)
rem     PY_EXE   = first usable interpreter
rem     PY_READY = first usable interpreter that already has every dependency
rem ---------------------------------------------------------------------------
set "PY_EXE="
set "PY_READY="
call :try_python py -3
if not defined PY_READY call :try_python python
if not defined PY_READY call :try_python python3
if not defined PY_READY call :try_python python3.13
if not defined PY_READY call :try_python python3.12
if not defined PY_READY call :try_python python3.11
if not defined PY_READY call :try_python py -3.13
if not defined PY_READY call :try_python py -3.12
if not defined PY_READY call :try_python py -3.11

if defined PY_READY goto :use_system
if not defined PY_EXE goto :no_python

rem ---------------------------------------------------------------------------
rem  2. Private environment (.venv): reuse it, rebuild it, or create it
rem     --system-site-packages reuses the packages the system already has.
rem ---------------------------------------------------------------------------
set "VENV_DIR=%CD%\.venv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"

if exist "%VENV_PY%" (
    "%VENV_PY%" -c "import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)" >nul 2>&1
    if errorlevel 1 (
        echo [setup] The existing .venv cannot be used - rebuilding it ...
        rmdir /s /q "%VENV_DIR%" >nul 2>&1
    )
)

if exist "%VENV_PY%" goto :use_venv

echo [setup] Creating a private environment in .venv ...
"%PY_EXE%" -m venv --system-site-packages "%VENV_DIR%"
if errorlevel 1 (
    echo [setup] Could not create .venv - falling back to the system Python.
    set "PY_RUN=%PY_EXE%"
    goto :deps
)

:use_venv
set "IN_VENV=1"
set "PY_RUN=%VENV_PY%"
echo [setup] Using the private environment: %PY_RUN%
goto :deps

:use_system
set "PY_RUN=%PY_READY%"
echo [setup] Using the system Python: %PY_RUN%
echo [setup] All dependencies are already installed.

rem ---------------------------------------------------------------------------
rem  3. Dependencies
rem ---------------------------------------------------------------------------
:deps
"%PY_RUN%" -m pip --version >nul 2>&1
if not errorlevel 1 goto :deps_install
echo [setup] pip is missing - bootstrapping it with ensurepip ...
"%PY_RUN%" -m ensurepip --upgrade >nul 2>&1
if errorlevel 1 goto :no_pip

:deps_install
"%PY_RUN%" -c "import pygame, numpy, supabase, dotenv" >nul 2>&1
if not errorlevel 1 goto :run
echo [setup] Installing the dependencies from requirements.txt ...
rem Wheels only: building pygame from source takes minutes and fails on the
rem newest Pythons, so the packages are installed one by one further down.
call :pip_install --only-binary=:all: -r requirements.txt
rem The pinned set can fail when one package has no wheel, so every module
rem that is still missing is installed on its own.
call :need_pygame
call :need_package numpy numpy
call :need_package supabase supabase
call :need_package dotenv python-dotenv
rem pytest is only needed for the test suite - never block the game on it.
"%PY_RUN%" -c "import pytest" >nul 2>&1
if errorlevel 1 call :pip_install --only-binary=:all: pytest
"%PY_RUN%" -c "import pygame, numpy, supabase, dotenv" >nul 2>&1
if errorlevel 1 goto :deps_failed

rem ---------------------------------------------------------------------------
rem  4. Start the game
rem ---------------------------------------------------------------------------
:run
echo.
echo [run] Starting Vector Drift ...
echo.
"%PY_RUN%" main.py %*
set "EXIT_CODE=%ERRORLEVEL%"
if "%EXIT_CODE%"=="0" goto :done
echo.
echo [ERROR] The game stopped with exit code %EXIT_CODE%.
pause
:done
popd
exit /b %EXIT_CODE%


rem ===========================================================================
rem  Subroutines
rem ===========================================================================

rem --- Accept a candidate interpreter only if it is a real Python 3.11+ ------
rem  %* = the candidate command, for example "py -3" or "python".
rem  The Microsoft Store stub and Python 2 both fail this test.
rem  "call" keeps a batch wrapper (some setups ship a python.bat) from
rem  ending this script when it returns.
:try_python
call %* -c "import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)" >nul 2>&1
if errorlevel 1 goto :eof
if defined PY_EXE goto :try_python_deps
for /f "delims=" %%P in ('call %* -c "import sys; print(sys.executable)" 2^>nul') do set "PY_EXE=%%P"
:try_python_deps
call %* -c "import pygame, numpy, supabase, dotenv" >nul 2>&1
if errorlevel 1 goto :eof
if defined PY_READY goto :eof
for /f "delims=" %%P in ('call %* -c "import sys; print(sys.executable)" 2^>nul') do set "PY_READY=%%P"
goto :eof

rem --- Install a package unless its module already imports -------------------
rem  %1 = module name, %2 = package name on PyPI
rem  A wheel is tried first because it is fast; the source build is the
rem  fallback for the Pythons that have no prebuilt wheel.
:need_package
"%PY_RUN%" -c "import %~1" >nul 2>&1
if not errorlevel 1 goto :eof
echo [setup] Installing %~2 ...
call :pip_install --only-binary=:all: %~2
if not errorlevel 1 goto :eof
call :pip_install %~2
goto :eof

rem --- pygame needs its own rule: the official package has no wheels for the
rem  newest Python releases, so fall back to its maintained drop-in fork -----
:need_pygame
"%PY_RUN%" -c "import pygame" >nul 2>&1
if not errorlevel 1 goto :eof
echo [setup] Installing pygame ...
call :pip_install --only-binary=:all: pygame
if not errorlevel 1 goto :eof
echo [setup] Trying pygame-ce instead ...
call :pip_install --only-binary=:all: pygame-ce
if not errorlevel 1 goto :eof
echo [setup] Trying pygame-ce without a prebuilt wheel ...
call :pip_install pygame-ce
goto :eof

rem --- pip install, with a --user retry when the environment is not writable -
rem  %* = arguments for pip install
:pip_install
"%PY_RUN%" -m pip install %*
if not errorlevel 1 goto :eof
if defined IN_VENV goto :eof
"%PY_RUN%" -m pip install --user %*
goto :eof

:folder_error
echo.
echo [ERROR] Cannot open the VectorDrift folder.
pause
exit /b 1

:missing_files
echo.
echo [ERROR] main.py or requirements.txt is missing.
echo         Keep this file inside the VectorDrift folder.
pause
popd
exit /b 1

:no_python
echo.
echo [ERROR] Python 3.11 or newer was not found on this system.
echo.
echo   1. Install Python from https://www.python.org/downloads/
echo      and tick "Add python.exe to PATH" in the installer.
echo   2. Run this file again.
echo.
pause
popd
exit /b 1

:no_pip
echo.
echo [ERROR] pip is not available for this Python installation.
echo         Reinstall Python with the "pip" option ticked, or install pip
echo         manually, then run this file again.
pause
popd
exit /b 1

:deps_failed
echo.
echo [ERROR] Could not install the dependencies.
echo         Check the internet connection and run this file again.
pause
popd
exit /b 1
