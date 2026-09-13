@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

echo ======================================================================
echo VARDHA VOICE CONNECT 1.0 - Django + Exotel
echo Python 3.11 / 3.12 / 3.13 isolated environment runner
echo ======================================================================
echo.

REM ----------------------------------------------------------------------
REM Find a supported system Python.
REM Priority: Python 3.13 -> 3.12 -> 3.11
REM The Python Launcher (py.exe) is preferred on Windows.
REM ----------------------------------------------------------------------
set "BASE_PY="

where py >nul 2>&1
if not errorlevel 1 (
    py -3.13 -c "import sys; print(sys.version)" >nul 2>&1
    if not errorlevel 1 set "BASE_PY=py -3.13"

    if not defined BASE_PY (
        py -3.12 -c "import sys; print(sys.version)" >nul 2>&1
        if not errorlevel 1 set "BASE_PY=py -3.12"
    )

    if not defined BASE_PY (
        py -3.11 -c "import sys; print(sys.version)" >nul 2>&1
        if not errorlevel 1 set "BASE_PY=py -3.11"
    )
)

REM Fallback: check normal python.exe if py.exe is unavailable.
if not defined BASE_PY (
    where python >nul 2>&1
    if not errorlevel 1 (
        python -c "import sys; raise SystemExit(0 if (3,11) <= sys.version_info[:2] <= (3,13) else 1)" >nul 2>&1
        if not errorlevel 1 set "BASE_PY=python"
    )
)

if not defined BASE_PY (
    echo ERROR: A supported Python installation was not found.
    echo.
    echo Required: Python 3.11, 3.12, or 3.13
    echo Detected system Python may be 3.14 or another unsupported version.
    echo.
    echo If Python 3.13 is installed, make sure the Windows Python Launcher
    echo can see it by running:
    echo     py -0p
    echo.
    echo Then run this file again.
    echo.
    echo PAUSED because the runner reported an error.
    pause
    exit /b 1
)

echo Selected base Python:
%BASE_PY% --version
echo.

REM ----------------------------------------------------------------------
REM Create the project's isolated virtual environment with the selected
REM supported Python. If .venv already exists, keep it and let run.py use it.
REM ----------------------------------------------------------------------
if not exist ".venv\Scripts\python.exe" (
    echo Creating isolated virtual environment: .venv
    echo Using:
    %BASE_PY% --version
    echo.

    %BASE_PY% -m venv ".venv"
    if errorlevel 1 (
        echo.
        echo ERROR: Failed to create the isolated virtual environment.
        echo.
        pause
        exit /b 1
    )
) else (
    echo Existing isolated environment found: .venv
    echo.
)

REM ----------------------------------------------------------------------
REM Verify the isolated environment itself is using Python 3.11-3.13.
REM This prevents an old .venv created with Python 3.14 from being reused.
REM ----------------------------------------------------------------------
".venv\Scripts\python.exe" -c "import sys; print('Virtual environment Python:', sys.version); raise SystemExit(0 if (3,11) <= sys.version_info[:2] <= (3,13) else 1)"
if errorlevel 1 (
    echo.
    echo WARNING: Existing .venv uses an unsupported Python version.
    echo Recreating .venv with the supported Python selected above...
    echo.

    rmdir /s /q ".venv"
    if errorlevel 1 (
        echo ERROR: Could not remove the old .venv.
        echo Close any process using .venv and run this file again.
        echo.
        pause
        exit /b 1
    )

    %BASE_PY% -m venv ".venv"
    if errorlevel 1 (
        echo ERROR: Failed to recreate .venv.
        echo.
        pause
        exit /b 1
    )
)

echo.
echo Starting project runner...
echo.

REM run.py performs dependency installation, migrations, collectstatic,
REM and starts Daphne using the isolated .venv Python.
".venv\Scripts\python.exe" run.py

if errorlevel 1 (
    echo.
    echo ======================================================================
    echo PAUSED because the runner reported an error.
    echo ======================================================================
    pause
)

endlocal
