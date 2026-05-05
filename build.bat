@echo off
setlocal

set "VENV_ACTIVATE=.venv\Scripts\activate.bat"
if exist "%VENV_ACTIVATE%" (
    echo [1/4] Activating virtual environment...
    call "%VENV_ACTIVATE%"
    if errorlevel 1 (
        echo Failed to activate virtual environment: %VENV_ACTIVATE%
        exit /b 1
    )
) else (
    echo [1/4] No .venv found, using system Python...
)

echo [2/4] Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo Python is not installed or not in PATH.
    echo Install Python 3 and try again.
    exit /b 1
)

echo [3/4] Installing build and runtime dependencies...
python -m pip install --upgrade pip
python -m pip install pyinstaller pillow mss pytesseract
if errorlevel 1 (
    echo Failed to install dependencies.
    exit /b 1
)

echo [4/4] Building EXE...
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
