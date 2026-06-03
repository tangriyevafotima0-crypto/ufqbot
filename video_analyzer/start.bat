@echo off
setlocal enabledelayedexpansion
title Video Analyzer
cd /d "%~dp0"

echo.
echo  ============================================================
echo  =          V I D E O   A N A L Y Z E R                    =
echo  ============================================================
echo.

IF NOT EXIST ".venv\Scripts\python.exe" GOTO :install
GOTO :run

:: ---------------------------------------------------------------
:: First time setup - full installation
:: ---------------------------------------------------------------
:install
echo  First time setup detected - installing dependencies...
echo  This will take a few minutes. Please wait...
echo.

:: ---------------------------------------------------------------
:: Step 1: Check Python installation
:: ---------------------------------------------------------------
echo [1/7] Checking Python installation...
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
echo [2/7] Creating virtual environment...
python -m venv .venv
if %ERRORLEVEL% neq 0 (
    echo  ERROR: Failed to create virtual environment.
    pause
    exit /b 1
)
echo  Virtual environment created.
echo.

:: ---------------------------------------------------------------
:: Step 3: Activate virtual environment
:: ---------------------------------------------------------------
echo [3/7] Activating virtual environment...
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
echo [4/7] Upgrading pip...
python -m pip install --upgrade pip --quiet
if %ERRORLEVEL% neq 0 (
    echo  WARNING: pip upgrade failed, continuing with existing version.
)
echo  pip upgraded.
echo.

:: ---------------------------------------------------------------
:: Step 5: Install requirements
:: ---------------------------------------------------------------
echo [5/7] Installing dependencies (this may take several minutes)...
echo  Please be patient - downloading AI models and libraries...
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
echo [6/7] Downloading YOLO object detection model...
python -c "from ultralytics import YOLO; YOLO('yolov8n.pt'); print('  YOLO model ready.')"
if %ERRORLEVEL% neq 0 (
    echo  WARNING: YOLO model download failed. It will be downloaded on first run.
)
echo.

:: ---------------------------------------------------------------
:: Step 7: Pre-download DeepFace model
:: ---------------------------------------------------------------
echo [7/7] Downloading emotion detection model...
python -c "from deepface import DeepFace; DeepFace.build_model('Emotion'); print('  Emotion model ready.')"
echo  Emotion model download attempted.
echo.

:: ---------------------------------------------------------------
:: Write install_info.json
:: ---------------------------------------------------------------
python check_update.py --force

echo.
echo  ============================================================
echo  =          INSTALLATION COMPLETE!                          =
echo  ============================================================
echo.
echo  Starting Video Analyzer...
echo.
GOTO :run

:: ---------------------------------------------------------------
:: Run the application
:: ---------------------------------------------------------------
:run
echo  Starting application...
call .venv\Scripts\activate.bat
python check_update.py
set YOLO_AUTOINSTALL=0
python main.py
GOTO :end

:end
echo.
echo  Video Analyzer has closed.
pause
