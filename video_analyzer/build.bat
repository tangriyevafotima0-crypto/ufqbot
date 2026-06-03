@echo off
setlocal enabledelayedexpansion
title Video Analyzer - Build
color 0A

echo.
echo  ============================================================
echo  =          V I D E O   A N A L Y Z E R                    =
echo  =                  BUILD SYSTEM                            =
echo  ============================================================
echo.

:: ---------------------------------------------------------------
:: Step 1: Activate virtual environment or use system Python
:: ---------------------------------------------------------------
if exist ".venv\Scripts\activate.bat" (
    echo [1/5] Activating virtual environment...
    call .venv\Scripts\activate.bat
    echo  Virtual environment activated.
) else (
    echo [1/5] No virtual environment found, using system Python...
    python --version >nul 2>&1
    if %ERRORLEVEL% neq 0 (
        echo  ERROR: Python is not found. Please run install.bat first.
        pause
        exit /b 1
    )
)
echo.

:: ---------------------------------------------------------------
:: Step 2: Install/upgrade PyInstaller
:: ---------------------------------------------------------------
echo [2/5] Installing/upgrading PyInstaller...
pip install --upgrade pyinstaller --quiet
if %ERRORLEVEL% neq 0 (
    echo  ERROR: Failed to install PyInstaller.
    pause
    exit /b 1
)
echo  PyInstaller ready.
echo.

:: ---------------------------------------------------------------
:: Step 3: Install requirements
:: ---------------------------------------------------------------
echo [3/5] Installing requirements...
pip install -r requirements.txt --quiet
if %ERRORLEVEL% neq 0 (
    echo  ERROR: Failed to install requirements.
    pause
    exit /b 1
)
echo  Requirements installed.
echo.

:: ---------------------------------------------------------------
:: Step 4: Run PyInstaller
:: ---------------------------------------------------------------
echo [4/5] Building executable (this may take a few minutes)...
echo  Setting POLARS_SKIP_CPU_CHECK=1 to prevent AVX/AVX2 crash...
set POLARS_SKIP_CPU_CHECK=1
set YOLO_AUTOINSTALL=0
pyinstaller --onedir --windowed --name VideoAnalyzer ^
    --add-data "version.json;." ^
    --additional-hooks-dir=hooks ^
    --hidden-import mediapipe.solutions ^
    --hidden-import mediapipe.solutions.face_mesh ^
    --hidden-import mediapipe.solutions.face_detection ^
    --hidden-import mediapipe.solutions.pose ^
    --exclude-module polars ^
    --exclude-module tensorboard ^
    --exclude-module IPython ^
    --exclude-module jupyter ^
    --exclude-module notebook ^
    --exclude-module pytest ^
    --collect-all mediapipe ^
    --collect-all ultralytics ^
    main.py
if %ERRORLEVEL% neq 0 (
    echo.
    echo  ERROR: PyInstaller build failed.
    echo  Check the output above for details.
    pause
    exit /b 1
)
echo  Build successful.
echo.

:: ---------------------------------------------------------------
:: Step 5: Copy version.json to dist and show result
:: ---------------------------------------------------------------
echo [5/5] Finalizing...
copy version.json dist\VideoAnalyzer\version.json >nul 2>&1
echo  Copied version.json to dist/VideoAnalyzer/
echo.

:: Show file size
if exist "dist\VideoAnalyzer\VideoAnalyzer.exe" (
    for %%A in ("dist\VideoAnalyzer\VideoAnalyzer.exe") do (
        set SIZE=%%~zA
        set /a SIZE_MB=!SIZE! / 1048576
    )
    echo  ============================================================
    echo  =  BUILD COMPLETE                                          =
    echo  ============================================================
    echo.
    echo  Output: dist\VideoAnalyzer\VideoAnalyzer.exe
    echo  Size:   ~!SIZE_MB! MB
    echo.
    echo  NOTE: The dist\VideoAnalyzer\ folder contains all files
    echo        needed to run the application. Distribute the entire
    echo        folder, not just the .exe file.
    echo.
) else (
    echo  WARNING: Expected output file not found at dist\VideoAnalyzer\VideoAnalyzer.exe
)

pause
