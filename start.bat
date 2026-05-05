@echo off
title Arcane Redux Dashboard
cd /d "%~dp0"

echo.
echo  ============================================================
echo   Arcane Redux Dashboard  ^|  AI YouTube Channel Operator
echo   http://localhost:7842
echo  ============================================================
echo.

:: Check Python 3.10+
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found in PATH.
    echo         Install Python 3.10+ from https://python.org
    echo         Make sure to check "Add Python to PATH" during install.
    pause
    exit /b 1
)

:: Create virtual environment if it doesn't exist
if not exist ".venv\Scripts\python.exe" (
    echo [SETUP] Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo [SETUP] Virtual environment created.
)

:: Activate virtual environment
call .venv\Scripts\activate.bat

:: Install / update requirements (silent, only shows errors)
echo [SETUP] Checking Python dependencies...
pip install -r requirements.txt -q --disable-pip-version-check
if errorlevel 1 (
    echo [WARN] Some packages may have failed to install.
    echo        Check requirements.txt and retry.
)

:: Create agent/.env from template if missing
if not exist "agent\.env" (
    if exist ".env.template" (
        echo [SETUP] Creating agent\.env from .env.template...
        copy ".env.template" "agent\.env" >nul
        echo [SETUP] IMPORTANT: Edit agent\.env and fill in your API keys!
    ) else (
        echo [WARN] No agent\.env found. Create it from .env.template.
    )
)

:: Create output directories
if not exist "agent\output\audio"      mkdir "agent\output\audio"
if not exist "agent\output\videos"     mkdir "agent\output\videos"
if not exist "agent\output\thumbnails" mkdir "agent\output\thumbnails"
if not exist "agent\output\scripts"    mkdir "agent\output\scripts"
if not exist "agent\assets\avatar"     mkdir "agent\assets\avatar"

echo.
echo [START] Launching dashboard...
echo [START] Browser will open automatically at http://localhost:7842
echo [START] Press Ctrl+C to stop the server
echo.

python app.py

echo.
echo [STOP] Dashboard stopped.
pause
