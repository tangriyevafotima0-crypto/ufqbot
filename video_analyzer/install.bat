@echo off
cd /d "%~dp0"
setlocal enabledelayedexpansion
title Video Analyzer - Installer
color 0B

echo.
echo  ============================================================
echo  =                                                          =
echo  =          V I D E O   A N A L Y Z E R                    =
echo  =                  INSTALLER v1.1.0                        =
echo  =                                                          =
echo  ============================================================
echo.
echo  Professional Video Analysis Application
echo  Powered by OpenCV, MediaPipe, YOLO, and DeepFace
echo.
echo  ============================================================
echo.

:: ---------------------------------------------------------------
:: Step 1: Check Python installation
:: ---------------------------------------------------------------
echo [1/8] Checking Python installation...
python --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo.
    echo  ERROR: Python is not installed or not in PATH.
    echo  Please install Python 3.11 or later from:
    echo  https://www.python.org/downloads/
    echo.
    echo  Make sure to check "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)

:: Check Python version is 3.11+
for /f "tokens=2 delims= " %%i in ('python --version 2^>^&1') do set PYVER=%%i
for /f "tokens=1,2 delims=." %%a in ("%PYVER%") do (
    set PYMAJOR=%%a
    set PYMINOR=%%b
)

if %PYMAJOR% lss 3 (
    echo  ERROR: Python 3.11+ is required. Found Python %PYVER%.
    pause
    exit /b 1
)
if %PYMAJOR% equ 3 if %PYMINOR% lss 11 (
    echo  ERROR: Python 3.11+ is required. Found Python %PYVER%.
    echo  Please upgrade from: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo  Found Python %PYVER% - OK
echo.

:: ---------------------------------------------------------------
:: Step 2: Create virtual environment
:: ---------------------------------------------------------------
echo [2/8] Setting up virtual environment...
if not exist ".venv" (
    python -m venv .venv
    if %ERRORLEVEL% neq 0 (
        echo  ERROR: Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo  Created new virtual environment in .venv/
) else (
    echo  Virtual environment already exists - reusing.
)
echo.

:: ---------------------------------------------------------------
:: Step 3: Activate virtual environment
:: ---------------------------------------------------------------
echo [3/8] Activating virtual environment...
call .venv\Scripts\activate.bat
if %ERRORLEVEL% neq 0 (
    echo  ERROR: Failed to activate virtual environment.
    pause
    exit /b 1
)
echo  Virtual environment activated.
echo.

:: ---------------------------------------------------------------
:: Step 4: Upgrade pip
:: ---------------------------------------------------------------
echo [4/8] Upgrading pip...
python -m pip install --upgrade pip --quiet
if %ERRORLEVEL% neq 0 (
    echo  WARNING: pip upgrade failed, continuing with existing version.
)
echo  pip upgraded.
echo.

:: ---------------------------------------------------------------
:: Step 5: Install requirements
:: ---------------------------------------------------------------
echo [5/8] Installing dependencies (this may take several minutes)...
pip install -r requirements.txt --quiet
if %ERRORLEVEL% neq 0 (
    echo.
    echo  ERROR: Failed to install dependencies.
    echo  Check your internet connection and try again.
    pause
    exit /b 1
)
echo  All dependencies installed successfully.
echo.

:: ---------------------------------------------------------------
:: Step 6: Pre-download YOLO model
:: ---------------------------------------------------------------
echo [6/8] Downloading YOLO object detection model...
python -c "from ultralytics import YOLO; YOLO('yolov8n.pt'); print('  YOLO model ready.')"
if %ERRORLEVEL% neq 0 (
    echo  WARNING: YOLO model download failed. It will be downloaded on first run.
)
echo.

:: ---------------------------------------------------------------
:: Step 7: Pre-download DeepFace model
:: ---------------------------------------------------------------
echo [7/8] Downloading emotion detection model...
python -c "from deepface import DeepFace; DeepFace.build_model('Emotion'); print('  Emotion model ready.')"
echo  Emotion model download attempted.
echo.

:: ---------------------------------------------------------------
:: Step 8: Create desktop shortcut and install info
:: ---------------------------------------------------------------
echo [8/8] Finalizing installation...

:: Create desktop shortcut
set "SCRIPT_DIR=%~dp0"
powershell -Command "$ws = New-Object -ComObject WScript.Shell; $sc = $ws.CreateShortcut([System.IO.Path]::Combine([Environment]::GetFolderPath('Desktop'), 'Video Analyzer.lnk')); $sc.TargetPath = '%SCRIPT_DIR%.venv\Scripts\python.exe'; $sc.Arguments = '%SCRIPT_DIR%main.py'; $sc.WorkingDirectory = '%SCRIPT_DIR%'; $sc.Description = 'Video Analyzer - Professional Video Analysis'; $sc.Save()" >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo  Desktop shortcut created.
) else (
    echo  Could not create desktop shortcut (non-critical).
)

:: Write install_info.json
python check_update.py --force

echo.
echo  ============================================================
echo  =                                                          =
echo  =          INSTALLATION COMPLETE!                          =
echo  =                                                          =
echo  ============================================================
echo.
echo  To run Video Analyzer:
echo.
echo    1. Double-click the "Video Analyzer" shortcut on your Desktop
echo       OR
echo    2. Open a terminal in this folder and run:
echo       .venv\Scripts\activate
echo       python main.py
echo.
echo  To update later, run: update.bat
echo.
echo  ============================================================
echo.
pause
