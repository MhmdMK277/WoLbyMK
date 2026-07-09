@echo off
REM One-click build script for WoLmk.exe
setlocal

echo === WoLmk build ===

where python >nul 2>nul
if errorlevel 1 (
    echo ERROR: Python not found on PATH.
    exit /b 1
)

echo Installing PyInstaller if needed...
python -m pip install --quiet pyinstaller
if errorlevel 1 (
    echo ERROR: failed to install PyInstaller.
    exit /b 1
)

set ICON_ARG=
if exist assets\wolmk.ico set ICON_ARG=--icon assets\wolmk.ico --add-data "assets\wolmk.ico;assets"

echo Building single-file exe...
python -m PyInstaller --noconfirm --onefile --windowed --name WoLmk %ICON_ARG% wolmk.py
if errorlevel 1 (
    echo ERROR: build failed.
    exit /b 1
)

echo.
echo Done! Your exe is at: dist\WoLmk.exe
endlocal
