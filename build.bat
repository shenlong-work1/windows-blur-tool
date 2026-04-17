@echo off
setlocal

echo [1/3] Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo Python is not installed or not in PATH.
    echo Install Python 3 and try again.
    exit /b 1
)

echo [2/3] Installing build and runtime dependencies...
python -m pip install --upgrade pip
python -m pip install pyinstaller pillow mss pytesseract
if errorlevel 1 (
    echo Failed to install dependencies.
    exit /b 1
)

echo [3/3] Building EXE...
python -m PyInstaller --onefile --windowed --name ScreenBlurOverlay --hidden-import=pytesseract app.py
if errorlevel 1 (
    echo Build failed.
    exit /b 1
)

echo.
echo Build complete: dist\ScreenBlurOverlay.exe
echo.
echo Note: Keep-text mode needs Tesseract OCR on the machine ^(see README.md^).
pause
