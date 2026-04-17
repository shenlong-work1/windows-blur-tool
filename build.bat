@echo off
setlocal

echo [1/3] Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo Python is not installed or not in PATH.
    echo Install Python 3 and try again.
    exit /b 1
)

echo [2/3] Installing build dependencies...
python -m pip install --upgrade pip
python -m pip install pyinstaller pillow mss
if errorlevel 1 (
    echo Failed to install dependencies.
    exit /b 1
)

echo [3/3] Building EXE...
python -m PyInstaller --onefile --windowed --name ScreenBlurOverlay app.py
if errorlevel 1 (
    echo Build failed.
    exit /b 1
)

echo.
echo Build complete: dist\ScreenBlurOverlay.exe
pause
