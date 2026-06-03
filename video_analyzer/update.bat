@echo off
setlocal enabledelayedexpansion
title Video Analyzer - Update
cd /d "%~dp0"

echo.
echo  ============================================================
echo  =          V I D E O   A N A L Y Z E R                    =
echo  =                   UPDATE                                 =
echo  ============================================================
echo.

:: Check git is available
git --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo  ERROR: Git is not installed.
    echo  Please install Git from: https://git-scm.com/
    echo  Or download the latest ZIP from GitHub manually.
    pause
    exit /b 1
)

:: Pull latest code
echo  Pulling latest code from repository...
git pull
if %ERRORLEVEL% neq 0 (
    echo.
    echo  ERROR: Git pull failed.
    echo  You may have local changes that conflict.
    echo  Try: git stash, then run update.bat again.
    echo  Or download the latest ZIP from GitHub manually.
    pause
    exit /b 1
)
echo  Code updated successfully.
echo.

:: Update dependencies
set UPDATE_OK=1
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
    echo  Updating dependencies...
    pip install -r requirements.txt --quiet
    if %ERRORLEVEL% neq 0 (
        echo  WARNING: Dependency update had issues. The application may still work.
        set UPDATE_OK=0
    ) else (
        echo  Dependencies updated.
    )
    :: Update install_info.json
    python check_update.py --force
    if %ERRORLEVEL% neq 0 (
        set UPDATE_OK=0
    )
) else (
    echo  No virtual environment found. Run start.bat to install.
    set UPDATE_OK=0
)

echo.
if "!UPDATE_OK!"=="1" (
    echo  ============================================================
    echo  =          UPDATE COMPLETE!                                =
    echo  ============================================================
) else (
    echo  ============================================================
    echo  =      UPDATE FINISHED WITH WARNINGS                      =
    echo  ============================================================
)
echo.
pause
