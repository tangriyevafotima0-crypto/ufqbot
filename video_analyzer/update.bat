@echo off
setlocal enabledelayedexpansion
title Video Analyzer - Update Checker
color 0E

echo.
echo  ============================================================
echo  =                                                          =
echo  =          V I D E O   A N A L Y Z E R                    =
echo  =                  UPDATE CHECKER                          =
echo  =                                                          =
echo  ============================================================
echo.

:: ---------------------------------------------------------------
:: Step 1: Activate virtual environment if available
:: ---------------------------------------------------------------
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
    echo  Virtual environment activated.
) else (
    echo  No virtual environment found, using system Python.
)
echo.

:: ---------------------------------------------------------------
:: Step 2: Show current version
:: ---------------------------------------------------------------
echo  Checking current version...
for /f "delims=" %%v in ('python -c "import json; print(json.load(open('version.json'))['version'])"') do set CURRENT_VER=%%v
echo  Current version: %CURRENT_VER%
echo.

:: ---------------------------------------------------------------
:: Step 3: Check for updates
:: ---------------------------------------------------------------
echo  Checking for updates...
echo.

python -c "import sys; sys.path.insert(0, '.'); from modules.updater import UpdateChecker; uc = UpdateChecker(); r = uc.check_for_update(); print('AVAILABLE=' + str(r['available'])); print('LATEST=' + str(r.get('latest_version', 'unknown'))); print('ERROR=' + str(r.get('error', 'None'))); changelog = r.get('changelog'); [print('CHANGE=' + c) for c in changelog] if changelog else None" > _update_check.tmp 2>&1

set UPDATE_AVAILABLE=False
set LATEST_VER=unknown
set UPDATE_ERROR=None

for /f "tokens=1,* delims==" %%a in (_update_check.tmp) do (
    if "%%a"=="AVAILABLE" set UPDATE_AVAILABLE=%%b
    if "%%a"=="LATEST" set LATEST_VER=%%b
    if "%%a"=="ERROR" set UPDATE_ERROR=%%b
)

if "%UPDATE_ERROR%" neq "None" (
    echo  Could not check for updates: %UPDATE_ERROR%
    echo  Please check your internet connection and try again.
    del _update_check.tmp >nul 2>&1
    echo.
    pause
    exit /b 1
)

if "%UPDATE_AVAILABLE%"=="False" (
    echo  You are running the latest version (%CURRENT_VER%).
    echo  No update needed.
    del _update_check.tmp >nul 2>&1
    echo.
    pause
    exit /b 0
)

echo  ============================================================
echo  =  UPDATE AVAILABLE: v%CURRENT_VER% -^> v%LATEST_VER%
echo  ============================================================
echo.

:: Show changelog
echo  Changes in this update:
for /f "tokens=1,* delims==" %%a in (_update_check.tmp) do (
    if "%%a"=="CHANGE" echo    - %%b
)
del _update_check.tmp >nul 2>&1
echo.

:: ---------------------------------------------------------------
:: Step 4: Apply update
:: ---------------------------------------------------------------
echo  Applying update...
echo.

:: Try git pull first
git --version >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo  Using git to fetch latest code...
    git pull origin feature/video-analyzer
    if %ERRORLEVEL% neq 0 (
        echo.
        echo  WARNING: git pull failed. You may need to resolve conflicts manually.
        echo  Alternatively, download the latest release from GitHub.
        echo.
        pause
        exit /b 1
    )
    echo  Code updated successfully.
) else (
    echo  Git is not installed. Please update manually:
    echo  1. Download latest release from GitHub
    echo  2. Extract files to this directory
    echo  3. Run install.bat again
    echo.
    pause
    exit /b 1
)
echo.

:: ---------------------------------------------------------------
:: Step 5: Update dependencies
:: ---------------------------------------------------------------
echo  Updating dependencies...
pip install -r requirements.txt --quiet
if %ERRORLEVEL% neq 0 (
    echo  WARNING: Dependency update had issues. The application may still work.
)
echo  Dependencies updated.
echo.

:: ---------------------------------------------------------------
:: Step 6: Update install info
:: ---------------------------------------------------------------
python -c "import json, datetime; info = json.load(open('install_info.json')) if __import__('os').path.exists('install_info.json') else {}; info['version'] = json.load(open('version.json'))['version']; info['last_update'] = datetime.datetime.now().isoformat(); json.dump(info, open('install_info.json', 'w'), indent=2)"

echo.
echo  ============================================================
echo  =                                                          =
echo  =          UPDATE COMPLETE!                                =
echo  =          Now running version: v%LATEST_VER%
echo  =                                                          =
echo  ============================================================
echo.
echo  You can now run the application as usual.
echo.
pause
