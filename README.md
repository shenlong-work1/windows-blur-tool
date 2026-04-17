# Windows Blur Tool

Real-time screen blur overlay for Windows. Draw a region on your screen and keep it blurred—useful for privacy (e.g. blurring content in emulators or specific windows).

**Repository:** [github.com/shenlong-work1/windows-blur-tool](https://github.com/shenlong-work1/windows-blur-tool)

## Requirements

- **OS:** Windows (uses Win32 APIs for topmost z-order, click-through, and capture exclusion)
- **Python:** 3.10 or newer
- **Dependencies:** `pillow`, `mss`, `tkinter` (usually bundled with Python on Windows)
- **Optional (keep-text mode):** `pytesseract` plus the [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) engine (Windows installer: [UB Mannheim builds](https://github.com/UB-Mannheim/tesseract/wiki))

## Quick start

```powershell
cd path\to\windows-blur-tool
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install pillow mss
# Optional — blur photos/video but keep text readable (see below)
python -m pip install pytesseract
python app.py
```

## Features

- **Blur region** — Live Gaussian blur over a rectangular area of the screen
- **Mouse selection** — “Select area with mouse” to drag a rectangle instead of typing X/Y/W/H
- **Manual position/size** — Optional numeric fields for exact placement
- **Always on top** — Keeps the control panel and overlay above other windows (Tk + Win32 `SetWindowPos`)
- **Click-through** — Lets mouse events pass through the blur window to apps underneath while the blur stays visible (requires always-on-top behavior)
- **Adjustable blur strength and FPS** — Sliders (FPS up to 144; real speed depends on CPU and region size)
- **Movable overlay** — Drag and resize the blur window after it starts
- **Keep text sharp** — Optional: blur non-text areas while leaving detected text readable (OCR-based; not perfect for all UIs)

### Keep text sharp (optional)

This mode uses **Tesseract** to find text in the blurred region and paste the **sharp** original back over those boxes, so **photos and video stay blurred** but **text stays readable** where OCR detects it.

1. `pip install pytesseract`
2. Install Tesseract OCR for Windows (e.g. `C:\Program Files\Tesseract-OCR\tesseract.exe` or add it to `PATH`).
3. Turn on **“Keep text sharp (blur images/video)”** in the control panel.

OCR runs about **three times per second** (to keep CPU use reasonable), so boxes can lag slightly if content scrolls quickly. Decorative text in images may still be blurred if OCR does not treat it as text.

## Build a standalone EXE

From the project folder:

```powershell
.\build.bat
```

Output: `dist\ScreenBlurOverlay.exe`

The script installs PyInstaller plus runtime deps and runs PyInstaller. You can also use `ScreenBlurOverlay.spec` if you customize the build.

If you use keep-text mode in a packaged EXE, users still need the **Tesseract engine** installed (or you must bundle `tesseract.exe` and point `pytesseract` to it); the Python wheel alone is not enough.

## Contributing / cloning

Clone this repo, then configure Git author identity if needed (`git config user.name` / `user.email`) and add the GitHub remote you use (SSH or HTTPS).

## Project layout

| File | Purpose |
|------|---------|
| `app.py` | Application entry point |
| `build.bat` | Windows script to build the EXE |
| `ScreenBlurOverlay.spec` | PyInstaller spec (optional customization) |
| `.gitignore` | Ignores `build/`, `dist/`, venvs, caches, etc. |

## Notes

- **Windows 10 (2004)+** recommended for `SetWindowDisplayAffinity` (reduces the overlay capturing itself).
- Click-through mode disables interaction with the blur window itself; use the control panel to stop or change settings.

## License

Add a `LICENSE` file in the repository if you want to specify terms for others.
