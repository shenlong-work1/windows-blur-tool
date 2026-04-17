# Windows Blur Tool

Real-time screen blur overlay for Windows. Draw a region on your screen and keep it blurred—useful for privacy (e.g. blurring content in emulators or specific windows).

**Repository:** [github.com/shenlong-work1/windows-blur-tool](https://github.com/shenlong-work1/windows-blur-tool)

## Requirements

- **OS:** Windows (uses Win32 APIs for topmost z-order, click-through, and capture exclusion)
- **Python:** 3.10 or newer
- **Dependencies:** `pillow`, `mss`, `tkinter` (usually bundled with Python on Windows)

## Quick start

```powershell
cd path\to\windows-blur-tool
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install pillow mss
python app.py
```

## Features

- **Blur region** — Live Gaussian blur over a rectangular area of the screen
- **Mouse selection** — “Select area with mouse” to drag a rectangle instead of typing X/Y/W/H
- **Manual position/size** — Optional numeric fields for exact placement
- **Always on top** — Keeps the control panel and overlay above other windows (Tk + Win32 `SetWindowPos`)
- **Click-through** — Lets mouse events pass through the blur window to apps underneath while the blur stays visible (requires always-on-top behavior)
- **Adjustable blur strength and FPS** — Sliders in the control panel
- **Movable overlay** — Drag and resize the blur window after it starts

## Build a standalone EXE

From the project folder:

```powershell
.\build.bat
```

Output: `dist\ScreenBlurOverlay.exe`

The script installs PyInstaller plus runtime deps and runs PyInstaller. You can also use `ScreenBlurOverlay.spec` if you customize the build.

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
