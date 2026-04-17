"""
Screen Blur Overlay Tool
========================
Applies a real-time blur over any region of your screen.
Perfect for blurring LinkedIn images/videos inside LDPlayer.

Requirements:
    pip install pillow mss

Usage:
    python blur_overlay.py
"""

import os
import shutil
import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
import ctypes
import ctypes.wintypes
from PIL import Image, ImageDraw, ImageFilter, ImageTk
import mss

try:
    import pytesseract

    HAS_PYTESSERACT = True
except ImportError:
    pytesseract = None  # type: ignore
    HAS_PYTESSERACT = False

try:
    _LANCZOS = Image.Resampling.LANCZOS
except AttributeError:
    _LANCZOS = Image.LANCZOS

_TESSERACT_RUNTIME_OK: bool | None = None


def tesseract_runtime_available() -> bool:
    """
    True if pytesseract is installed and the Tesseract OCR engine is callable.
    Caches the result after first successful check.
    """
    global _TESSERACT_RUNTIME_OK
    if _TESSERACT_RUNTIME_OK is not None:
        return _TESSERACT_RUNTIME_OK
    if not HAS_PYTESSERACT or pytesseract is None:
        _TESSERACT_RUNTIME_OK = False
        return False
    if shutil.which("tesseract"):
        try:
            pytesseract.get_tesseract_version()
            _TESSERACT_RUNTIME_OK = True
            return True
        except Exception:
            pass
    for base in (
        os.environ.get("ProgramFiles", r"C:\Program Files"),
        os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
    ):
        exe = os.path.join(base, "Tesseract-OCR", "tesseract.exe")
        if os.path.isfile(exe):
            pytesseract.pytesseract.tesseract_cmd = exe
            try:
                pytesseract.get_tesseract_version()
                _TESSERACT_RUNTIME_OK = True
                return True
            except Exception:
                break
    _TESSERACT_RUNTIME_OK = False
    return False


def ocr_word_boxes(img: Image.Image, max_width: int = 960) -> list[tuple[int, int, int, int]]:
    """
    Return bounding boxes (left, top, width, height) in *img* pixel coordinates
    for detected text. Uses a downscaled copy for speed, then scales boxes back.
    """
    if not HAS_PYTESSERACT or pytesseract is None:
        return []
    ow, oh = img.size
    if ow <= 0 or oh <= 0:
        return []
    small = img.convert("RGB")
    if ow > max_width:
        ratio = max_width / ow
        nh = max(1, int(oh * ratio))
        small = small.resize((max_width, nh), _LANCZOS)
    sx = ow / small.width
    sy = oh / small.height

    data = pytesseract.image_to_data(small, output_type=pytesseract.Output.DICT)
    n = len(data.get("text", []))
    out: list[tuple[int, int, int, int]] = []
    for i in range(n):
        t = (data["text"][i] or "").strip()
        if not t:
            continue
        conf = data["conf"][i]
        try:
            c = float(conf)
        except (TypeError, ValueError):
            continue
        if c < 0 or c < 30:
            continue
        left = int(data["left"][i] * sx)
        top = int(data["top"][i] * sy)
        w = max(1, int(data["width"][i] * sx))
        h = max(1, int(data["height"][i] * sy))
        out.append((left, top, w, h))
    return out


def build_text_keep_mask(
    size: tuple[int, int],
    boxes: list[tuple[int, int, int, int]],
    pad: int = 6,
) -> Image.Image:
    """Grayscale mask: 255 = keep sharp (text), 0 = blur."""
    w, h = size
    mask = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(mask)
    for bx, by, bw, bh in boxes:
        x1 = max(0, bx - pad)
        y1 = max(0, by - pad)
        x2 = min(w - 1, bx + bw + pad)
        y2 = min(h - 1, by + bh + pad)
        if x2 > x1 and y2 > y1:
            draw.rectangle([x1, y1, x2, y2], fill=255)
    return mask


# ─── Windows API helpers ───────────────────────────────────────────────────────

def set_window_exclude_from_capture(hwnd: int):
    """
    Mark a window as invisible to screen-capture tools (Windows 10 v2004+).
    This prevents the blur overlay from capturing itself (no feedback loop).
    WDA_EXCLUDEFROMCAPTURE = 0x00000011
    """
    try:
        ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, 0x00000011)
    except Exception:
        pass  # Silently ignore on older Windows versions


def set_window_topmost(hwnd: int, enabled: bool):
    """
    Force a window into topmost/non-topmost z-order using Win32 API.
    This is stronger than relying only on Tk's -topmost flag.
    """
    if not hwnd:
        return
    try:
        HWND_TOPMOST = -1
        HWND_NOTOPMOST = -2
        SWP_NOMOVE = 0x0002
        SWP_NOSIZE = 0x0001
        SWP_NOACTIVATE = 0x0010
        SWP_SHOWWINDOW = 0x0040
        insert_after = HWND_TOPMOST if enabled else HWND_NOTOPMOST
        flags = SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW
        ctypes.windll.user32.SetWindowPos(hwnd, insert_after, 0, 0, 0, 0, flags)
    except Exception:
        pass


def set_window_click_through(hwnd: int, enabled: bool):
    """
    Toggle click-through for a window so mouse events pass to windows below.
    """
    if not hwnd:
        return
    try:
        GWL_EXSTYLE = -20
        WS_EX_LAYERED = 0x00080000
        WS_EX_TRANSPARENT = 0x00000020
        style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        style |= WS_EX_LAYERED
        if enabled:
            style |= WS_EX_TRANSPARENT
        else:
            style &= ~WS_EX_TRANSPARENT
        ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
    except Exception:
        pass


def get_hwnd_by_title(title: str) -> int:
    """Return window handle for a window whose title contains `title`."""
    result = ctypes.c_int(0)

    def enum_cb(hwnd, _):
        buf = ctypes.create_unicode_buffer(256)
        ctypes.windll.user32.GetWindowTextW(hwnd, buf, 256)
        if title in buf.value:
            result.value = hwnd
            return False
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
    ctypes.windll.user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
    return result.value


# ─── Blur Overlay Window ───────────────────────────────────────────────────────

class BlurWindow:
    """
    A transparent, always-on-top overlay window that continuously captures
    the screen region beneath it and re-draws a blurred version.
    The window itself is excluded from screen capture so mss never sees it.
    """

    BORDER       = 6    # px — resize-handle thickness
    MIN_SIZE     = 80   # minimum width/height in px
    MAX_FPS      = 144  # UI slider cap; capture loop has no 50 FPS floor anymore

    def __init__(
        self,
        parent,
        x,
        y,
        w,
        h,
        blur_radius_var,
        fps_var,
        preserve_text_var,
        on_close,
    ):
        self.parent         = parent
        self.blur_radius_var = blur_radius_var
        self.fps_var        = fps_var
        self.preserve_text_var = preserve_text_var
        self.on_close       = on_close
        self.running        = False
        self._photo         = None          # keep ImageTk reference alive
        self._ocr_boxes_lock = threading.Lock()
        self._ocr_boxes: list[tuple[int, int, int, int]] = []

        # ── build the toplevel window ──────────────────────────────────────
        self.win = tk.Toplevel(parent)
        self.win.overrideredirect(True)     # no title bar
        self.win.attributes("-topmost", True)
        self.win.attributes("-alpha", 0.97)
        self.win.geometry(f"{w}x{h}+{x}+{y}")
        self.win.protocol("WM_DELETE_WINDOW", self.close)

        self.canvas = tk.Canvas(
            self.win,
            highlightthickness=0,
            cursor="fleur",
            bg="black",
        )
        self.canvas.pack(fill="both", expand=True)

        # ── drag / resize state ────────────────────────────────────────────
        self._drag_start_x  = 0
        self._drag_start_y  = 0
        self._drag_win_x    = 0
        self._drag_win_y    = 0
        self._resize_mode   = None      # 'se' | 'sw' | 'ne' | 'nw' | 's' | 'e' …
        self._click_through = False

        self.canvas.bind("<ButtonPress-1>",   self._on_press)
        self.canvas.bind("<B1-Motion>",       self._on_motion)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Motion>",          self._update_cursor)

        # close button (×) in top-right corner
        self._close_btn = tk.Label(
            self.canvas, text="×", font=("Arial", 14, "bold"),
            fg="white", bg="#cc3333", cursor="hand2", padx=4,
        )
        self._close_btn.place(relx=1.0, y=0, anchor="ne")
        self._close_btn.bind("<Button-1>", lambda _: self.close())

        # resize handle indicator (bottom-right)
        self.canvas.create_text(
            w - 4, h - 4,
            text="◢", fill="white", anchor="se",
            font=("Arial", 10), tags="resize_hint",
        )

        # ── exclude from screen capture (Windows 10 v2004+) ───────────────
        self.win.update_idletasks()
        hwnd = get_hwnd_by_title("BlurOverlay__internal__")
        if not hwnd:
            # fallback: enumerate by partial match
            hwnd = ctypes.windll.user32.GetForegroundWindow()
        # The reliable way: get hwnd directly from tkinter widget id
        hwnd = int(self.win.wm_frame(), 16) if self.win.wm_frame() else hwnd
        set_window_exclude_from_capture(hwnd)

        # ── start capture loop ─────────────────────────────────────────────
        self.running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()
        self._ocr_thread = threading.Thread(target=self._ocr_refresh_loop, daemon=True)
        self._ocr_thread.start()

    def set_click_through(self, enabled: bool):
        self._click_through = enabled
        try:
            hwnd = int(self.win.wm_frame(), 16) if self.win.wm_frame() else 0
            set_window_click_through(hwnd, enabled)
            # When pass-through is enabled, keep overlay fully on top.
            set_window_topmost(hwnd, True)
            self.canvas.config(cursor="arrow" if enabled else "fleur")
            if enabled:
                self._close_btn.place_forget()
            else:
                self._close_btn.place(relx=1.0, y=0, anchor="ne")
        except Exception:
            pass

    # ── cursor / resize hit-testing ───────────────────────────────────────────

    def _resize_mode_at(self, x, y):
        w = self.win.winfo_width()
        h = self.win.winfo_height()
        b = self.BORDER
        on_right  = x >= w - b
        on_bottom = y >= h - b
        on_left   = x <= b
        on_top    = y <= b
        if on_bottom and on_right:  return "se"
        if on_bottom and on_left:   return "sw"
        if on_top    and on_right:  return "ne"
        if on_top    and on_left:   return "nw"
        if on_right:                return "e"
        if on_bottom:               return "s"
        if on_left:                 return "w"
        if on_top:                  return "n"
        return None

    def _update_cursor(self, event):
        mode = self._resize_mode_at(event.x, event.y)
        cursors = {
            "se": "size_nw_se", "nw": "size_nw_se",
            "sw": "size_ne_sw", "ne": "size_ne_sw",
            "e": "size_we",     "w": "size_we",
            "s": "size_ns",     "n": "size_ns",
        }
        self.canvas.config(cursor=cursors.get(mode, "fleur"))

    # ── drag & resize ─────────────────────────────────────────────────────────

    def _on_press(self, event):
        self._resize_mode  = self._resize_mode_at(event.x, event.y)
        self._drag_start_x = event.x_root
        self._drag_start_y = event.y_root
        self._drag_win_x   = self.win.winfo_x()
        self._drag_win_y   = self.win.winfo_y()
        self._drag_win_w   = self.win.winfo_width()
        self._drag_win_h   = self.win.winfo_height()

    def _on_motion(self, event):
        dx = event.x_root - self._drag_start_x
        dy = event.y_root - self._drag_start_y
        mode = self._resize_mode
        x, y = self._drag_win_x, self._drag_win_y
        w, h = self._drag_win_w, self._drag_win_h

        if mode is None:                        # move
            self.win.geometry(f"+{x+dx}+{y+dy}")
        else:                                   # resize
            new_x, new_y, new_w, new_h = x, y, w, h
            if "e" in mode:  new_w = max(self.MIN_SIZE, w + dx)
            if "s" in mode:  new_h = max(self.MIN_SIZE, h + dy)
            if "w" in mode:
                new_w = max(self.MIN_SIZE, w - dx)
                new_x = x + (w - new_w)
            if "n" in mode:
                new_h = max(self.MIN_SIZE, h - dy)
                new_y = y + (h - new_h)
            self.win.geometry(f"{new_w}x{new_h}+{new_x}+{new_y}")
            # move resize hint
            self.canvas.coords("resize_hint", new_w - 4, new_h - 4)

    def _on_release(self, event):
        self._resize_mode = None

    # ── capture / blur loop ───────────────────────────────────────────────────

    def _ocr_refresh_loop(self):
        """Updates text bounding boxes a few times per second when preserve-text is on."""
        while self.running:
            try:
                if not self.preserve_text_var.get() or not tesseract_runtime_available():
                    time.sleep(0.35)
                    continue
                x = self.win.winfo_x()
                y = self.win.winfo_y()
                w = self.win.winfo_width()
                h = self.win.winfo_height()
                if w < 8 or h < 8:
                    time.sleep(0.2)
                    continue
                region = {"top": y, "left": x, "width": w, "height": h}
                with mss.mss() as sct:
                    shot = sct.grab(region)
                img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
                boxes = ocr_word_boxes(img)
                with self._ocr_boxes_lock:
                    self._ocr_boxes = boxes
            except Exception:
                pass
            time.sleep(0.35)

    def _capture_loop(self):
        with mss.mss() as sct:
            while self.running:
                try:
                    fps = max(1, self.fps_var.get())
                    # No 20ms floor here — that capped effective FPS at ~50 regardless of slider.
                    delay = max(1.0 / 1000.0, 1.0 / fps)
                    x = self.win.winfo_x()
                    y = self.win.winfo_y()
                    w = self.win.winfo_width()
                    h = self.win.winfo_height()

                    region = {"top": y, "left": x, "width": w, "height": h}
                    shot   = sct.grab(region)
                    img    = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")

                    radius  = self.blur_radius_var.get()
                    blurred = img.filter(ImageFilter.GaussianBlur(radius=radius))

                    out = blurred
                    if (
                        self.preserve_text_var.get()
                        and tesseract_runtime_available()
                        and img.size == blurred.size
                    ):
                        with self._ocr_boxes_lock:
                            boxes = list(self._ocr_boxes)
                        if boxes:
                            mask = build_text_keep_mask(img.size, boxes)
                            out = Image.composite(img, blurred, mask)

                    photo = ImageTk.PhotoImage(out)
                    self.canvas.after(0, self._draw, photo)
                    time.sleep(delay)
                except Exception:
                    time.sleep(0.1)

    def _draw(self, photo):
        if not self.running:
            return
        self.canvas.delete("blur_img")
        self.canvas.create_image(0, 0, anchor="nw", image=photo, tags="blur_img")
        self.canvas.tag_lower("blur_img")        # keep close btn on top
        self._photo = photo                      # prevent GC

    # ── teardown ──────────────────────────────────────────────────────────────

    def close(self):
        self.running = False
        try:
            self.win.destroy()
        except Exception:
            pass
        if self.on_close:
            self.on_close()


# ─── Control Panel ─────────────────────────────────────────────────────────────

class ControlPanel:

    BG   = "#1e1e2e"
    FG   = "#cdd6f4"
    ACC  = "#89b4fa"    # blue accent
    CARD = "#2a2a3e"

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Screen Blur Overlay — Control Panel")
        self.root.configure(bg=self.BG)
        self.root.resizable(False, False)
        self.root.attributes("-topmost", True)

        # ── shared vars ────────────────────────────────────────────────────
        self.blur_radius_var = tk.IntVar(value=18)
        self.fps_var         = tk.IntVar(value=60)
        self.overlay_x_var   = tk.IntVar(value=300)
        self.overlay_y_var   = tk.IntVar(value=200)
        self.overlay_w_var   = tk.IntVar(value=420)
        self.overlay_h_var   = tk.IntVar(value=600)
        self.always_on_top_var = tk.BooleanVar(value=True)
        self.click_through_var = tk.BooleanVar(value=False)
        self.preserve_text_var = tk.BooleanVar(value=False)

        self._blur_win: BlurWindow | None = None
        self._selector_win: tk.Toplevel | None = None
        self._selector_canvas: tk.Canvas | None = None
        self._selection_rect: int | None = None
        self._sel_start_x = 0
        self._sel_start_y = 0

        self._build_ui()
        self._apply_always_on_top()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        pad = dict(padx=16, pady=6)

        # ── header ────────────────────────────────────────────────────────
        hdr = tk.Frame(self.root, bg=self.BG)
        hdr.pack(fill="x", padx=16, pady=(14, 4))
        tk.Label(hdr, text="🔵  Screen Blur Overlay",
                 font=("Segoe UI", 15, "bold"),
                 fg=self.ACC, bg=self.BG).pack(anchor="w")
        tk.Label(hdr, text="Blur any region on your screen in real-time",
                 font=("Segoe UI", 9), fg="#6c7086", bg=self.BG).pack(anchor="w")

        ttk.Separator(self.root, orient="horizontal").pack(fill="x", padx=16, pady=6)

        # ── blur strength ─────────────────────────────────────────────────
        sec = self._section("Blur strength")
        row = tk.Frame(sec, bg=self.CARD)
        row.pack(fill="x")
        self._blur_label = tk.Label(row, text=f"{self.blur_radius_var.get()}",
                                    width=3, font=("Segoe UI", 11, "bold"),
                                    fg=self.ACC, bg=self.CARD)
        self._blur_label.pack(side="right")
        slider = tk.Scale(
            row, variable=self.blur_radius_var,
            from_=1, to=60, orient="horizontal",
            bg=self.CARD, fg=self.FG, troughcolor="#414162",
            highlightthickness=0, bd=0, showvalue=False,
            command=lambda v: self._blur_label.config(text=v),
        )
        slider.pack(side="left", fill="x", expand=True)

        # ── fps ───────────────────────────────────────────────────────────
        sec2 = self._section("Refresh rate (FPS)")
        row2 = tk.Frame(sec2, bg=self.CARD)
        row2.pack(fill="x")
        self._fps_label = tk.Label(row2, text=f"{self.fps_var.get()}",
                                   width=3, font=("Segoe UI", 11, "bold"),
                                   fg=self.ACC, bg=self.CARD)
        self._fps_label.pack(side="right")
        tk.Scale(
            row2, variable=self.fps_var,
            from_=1, to=BlurWindow.MAX_FPS, orient="horizontal",
            bg=self.CARD, fg=self.FG, troughcolor="#414162",
            highlightthickness=0, bd=0, showvalue=False,
            command=lambda v: self._fps_label.config(text=v),
        ).pack(side="left", fill="x", expand=True)

        # ── initial position & size ────────────────────────────────────────
        sec3 = self._section("Initial position & size  (drag to adjust later)")
        grid = tk.Frame(sec3, bg=self.CARD)
        grid.pack(fill="x")
        fields = [
            ("X", self.overlay_x_var),  ("Y",      self.overlay_y_var),
            ("W", self.overlay_w_var),  ("H",      self.overlay_h_var),
        ]
        for i, (label, var) in enumerate(fields):
            tk.Label(grid, text=label, fg="#6c7086", bg=self.CARD,
                     font=("Segoe UI", 9)).grid(row=i // 2, column=(i % 2) * 2,
                                                 padx=(8, 2), pady=3, sticky="e")
            tk.Entry(grid, textvariable=var, width=7,
                     bg="#313147", fg=self.FG, insertbackground=self.FG,
                     relief="flat", font=("Segoe UI", 10)
                     ).grid(row=i // 2, column=(i % 2) * 2 + 1, padx=(0, 12), pady=3)

        ttk.Separator(self.root, orient="horizontal").pack(fill="x", padx=16, pady=10)

        # ── buttons ───────────────────────────────────────────────────────
        btn_row = tk.Frame(self.root, bg=self.BG)
        btn_row.pack(pady=(0, 14), padx=16, fill="x")

        self.select_btn = tk.Button(
            btn_row, text="🖱  Select area with mouse",
            command=self._select_area,
            bg="#89dceb", fg="#1e1e2e",
            font=("Segoe UI", 10, "bold"),
            relief="flat", cursor="hand2",
            padx=12, pady=6,
        )
        self.select_btn.pack(side="left", expand=True, fill="x", padx=(0, 6))

        self.start_btn = tk.Button(
            btn_row, text="▶  Start blur",
            command=self._start,
            bg="#a6e3a1", fg="#1e1e2e",
            font=("Segoe UI", 10, "bold"),
            relief="flat", cursor="hand2",
            padx=12, pady=6,
        )
        self.start_btn.pack(side="left", expand=True, fill="x", padx=6)

        self.stop_btn = tk.Button(
            btn_row, text="■  Stop",
            command=self._stop,
            bg="#f38ba8", fg="#1e1e2e",
            font=("Segoe UI", 10, "bold"),
            relief="flat", cursor="hand2",
            padx=12, pady=6,
            state="disabled",
        )
        self.stop_btn.pack(side="left", expand=True, fill="x", padx=(6, 0))

        top_row = tk.Frame(self.root, bg=self.BG)
        top_row.pack(pady=(0, 10), padx=16, fill="x")
        self.top_btn = tk.Button(
            top_row,
            text="📌 Always on top: ON",
            command=self._toggle_always_on_top,
            bg="#94e2d5",
            fg="#1e1e2e",
            font=("Segoe UI", 9, "bold"),
            relief="flat",
            cursor="hand2",
            padx=10,
            pady=5,
        )
        self.top_btn.pack(fill="x")

        click_row = tk.Frame(self.root, bg=self.BG)
        click_row.pack(pady=(0, 10), padx=16, fill="x")
        self.click_btn = tk.Button(
            click_row,
            text="🖱 Click-through: OFF",
            command=self._toggle_click_through,
            bg="#f9e2af",
            fg="#1e1e2e",
            font=("Segoe UI", 9, "bold"),
            relief="flat",
            cursor="hand2",
            padx=10,
            pady=5,
        )
        self.click_btn.pack(fill="x")

        preserve_row = tk.Frame(self.root, bg=self.BG)
        preserve_row.pack(pady=(0, 10), padx=16, fill="x")
        self.preserve_btn = tk.Button(
            preserve_row,
            text="📝 Keep text sharp (blur images/video): OFF",
            command=self._toggle_preserve_text,
            bg="#cba6f7",
            fg="#1e1e2e",
            font=("Segoe UI", 9, "bold"),
            relief="flat",
            cursor="hand2",
            padx=10,
            pady=5,
        )
        self.preserve_btn.pack(fill="x")

        # ── status bar ────────────────────────────────────────────────────
        self.status_var = tk.StringVar(value="Ready — click Start blur to begin")
        tk.Label(self.root, textvariable=self.status_var,
                 font=("Segoe UI", 8), fg="#6c7086", bg=self.BG,
                 anchor="w").pack(fill="x", padx=16, pady=(0, 10))

        # ── tip ───────────────────────────────────────────────────────────
        tip = ("Tip: 'Keep text sharp' uses OCR (pytesseract + Tesseract) to leave text readable\n"
               "while blurring photos/video in the same region. See README for install.")
        tk.Label(self.root, text=tip, font=("Segoe UI", 8), fg="#585b70",
                 bg=self.BG, justify="left", anchor="w").pack(fill="x", padx=16, pady=(0, 12))

    def _section(self, title: str) -> tk.Frame:
        tk.Label(self.root, text=title.upper(), font=("Segoe UI", 8, "bold"),
                 fg="#585b70", bg=self.BG).pack(anchor="w", padx=16, pady=(8, 2))
        card = tk.Frame(self.root, bg=self.CARD, bd=0,
                        highlightbackground="#44475a", highlightthickness=1)
        card.pack(fill="x", padx=16, pady=(0, 4))
        inner = tk.Frame(card, bg=self.CARD)
        inner.pack(fill="x", padx=10, pady=8)
        return inner

    # ── actions ───────────────────────────────────────────────────────────────

    def _start(self):
        if self._blur_win:
            self._stop()
        self._blur_win = BlurWindow(
            parent          = self.root,
            x               = self.overlay_x_var.get(),
            y               = self.overlay_y_var.get(),
            w               = self.overlay_w_var.get(),
            h               = self.overlay_h_var.get(),
            blur_radius_var = self.blur_radius_var,
            fps_var         = self.fps_var,
            preserve_text_var = self.preserve_text_var,
            on_close        = self._on_overlay_closed,
        )
        self.start_btn.config(state="disabled")
        self.select_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self._apply_always_on_top()
        self._apply_click_through()
        if self.preserve_text_var.get() and tesseract_runtime_available():
            self.status_var.set(
                "Blur active — keep-text ON: OCR updates ~3×/s; text stays sharp where detected"
            )
        else:
            self.status_var.set("✔ Blur overlay is active — drag it over LDPlayer")

    def _select_area(self):
        if self._blur_win:
            self._stop()

        self.status_var.set("Drag to select area. Press ESC to cancel.")

        win = tk.Toplevel(self.root)
        self._selector_win = win
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.attributes("-alpha", 0.25)
        win.configure(bg="black")

        screen_w = win.winfo_screenwidth()
        screen_h = win.winfo_screenheight()
        win.geometry(f"{screen_w}x{screen_h}+0+0")

        canvas = tk.Canvas(win, bg="black", highlightthickness=0, cursor="crosshair")
        canvas.pack(fill="both", expand=True)
        self._selector_canvas = canvas

        guide = (
            "Drag to select blur area\n"
            "Release to confirm, ESC to cancel"
        )
        canvas.create_text(
            20, 20, anchor="nw", text=guide,
            fill="white", font=("Segoe UI", 12, "bold"),
        )

        canvas.bind("<ButtonPress-1>", self._on_select_press)
        canvas.bind("<B1-Motion>", self._on_select_drag)
        canvas.bind("<ButtonRelease-1>", self._on_select_release)
        win.bind("<Escape>", lambda _e: self._cancel_selection())
        win.focus_force()

    def _on_select_press(self, event):
        self._sel_start_x = event.x_root
        self._sel_start_y = event.y_root
        if self._selector_canvas and self._selection_rect:
            self._selector_canvas.delete(self._selection_rect)
            self._selection_rect = None

    def _on_select_drag(self, event):
        if not self._selector_canvas:
            return
        x1, y1 = self._sel_start_x, self._sel_start_y
        x2, y2 = event.x_root, event.y_root
        if self._selection_rect is None:
            self._selection_rect = self._selector_canvas.create_rectangle(
                x1, y1, x2, y2, outline="#89b4fa", width=3
            )
        else:
            self._selector_canvas.coords(self._selection_rect, x1, y1, x2, y2)

    def _on_select_release(self, event):
        x1, y1 = self._sel_start_x, self._sel_start_y
        x2, y2 = event.x_root, event.y_root

        x = min(x1, x2)
        y = min(y1, y2)
        w = abs(x2 - x1)
        h = abs(y2 - y1)

        if w < BlurWindow.MIN_SIZE or h < BlurWindow.MIN_SIZE:
            self.status_var.set(
                f"Selection too small (min {BlurWindow.MIN_SIZE}px). Try again."
            )
            self._cancel_selection()
            return

        self.overlay_x_var.set(x)
        self.overlay_y_var.set(y)
        self.overlay_w_var.set(w)
        self.overlay_h_var.set(h)

        self._close_selection_overlay()
        self.status_var.set("Area selected. Starting blur overlay...")
        self._start()

    def _cancel_selection(self):
        self._close_selection_overlay()
        self.status_var.set("Selection canceled.")

    def _close_selection_overlay(self):
        self._selection_rect = None
        self._selector_canvas = None
        if self._selector_win:
            try:
                self._selector_win.destroy()
            except Exception:
                pass
        self._selector_win = None

    def _stop(self):
        if self._blur_win:
            self._blur_win.close()
            self._blur_win = None
        self._on_overlay_closed()

    def _on_overlay_closed(self):
        self.start_btn.config(state="normal")
        self.select_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        self.status_var.set("Stopped — click Start blur to begin again")

    def _toggle_always_on_top(self):
        self.always_on_top_var.set(not self.always_on_top_var.get())
        self._apply_always_on_top()

    def _apply_always_on_top(self):
        enabled = self.always_on_top_var.get()
        try:
            self.root.attributes("-topmost", enabled)
            root_hwnd = int(self.root.wm_frame(), 16) if self.root.wm_frame() else 0
            set_window_topmost(root_hwnd, enabled)
        except Exception:
            pass
        if self._blur_win and self._blur_win.win:
            try:
                self._blur_win.win.attributes("-topmost", enabled)
                blur_hwnd = int(self._blur_win.win.wm_frame(), 16) if self._blur_win.win.wm_frame() else 0
                set_window_topmost(blur_hwnd, enabled)
                if enabled:
                    # Brief lift helps restore z-order after other apps steal focus.
                    self._blur_win.win.lift()
            except Exception:
                pass
        if hasattr(self, "top_btn"):
            if enabled:
                self.top_btn.config(text="📌 Always on top: ON", bg="#94e2d5")
            else:
                self.top_btn.config(text="📌 Always on top: OFF", bg="#f9e2af")

    def _toggle_click_through(self):
        self.click_through_var.set(not self.click_through_var.get())
        self._apply_click_through()

    def _toggle_preserve_text(self):
        new_val = not self.preserve_text_var.get()
        if new_val:
            global _TESSERACT_RUNTIME_OK
            _TESSERACT_RUNTIME_OK = None
            if not HAS_PYTESSERACT:
                messagebox.showwarning(
                    "Text-preservation unavailable",
                    "Install the Python package:\n"
                    "  pip install pytesseract\n\n"
                    "Then install the Tesseract OCR engine for Windows:\n"
                    "https://github.com/UB-Mannheim/tesseract/wiki",
                )
                return
            if not tesseract_runtime_available():
                messagebox.showwarning(
                    "Tesseract OCR not found",
                    "Install Tesseract OCR (includes tesseract.exe).\n"
                    "Typical path: C:\\Program Files\\Tesseract-OCR\\\n"
                    "Or add the folder that contains tesseract.exe to PATH.",
                )
                return
        self.preserve_text_var.set(new_val)
        self._sync_preserve_text_btn()
        if self._blur_win:
            if new_val:
                self.status_var.set(
                    "Keep-text ON — text stays sharp; photos/video blurred (OCR ~3×/s)"
                )
            else:
                self.status_var.set("Keep-text OFF — entire blur area is blurred")

    def _sync_preserve_text_btn(self):
        if self.preserve_text_var.get():
            self.preserve_btn.config(
                text="📝 Keep text sharp (blur images/video): ON",
                bg="#a6e3a1",
            )
        else:
            self.preserve_btn.config(
                text="📝 Keep text sharp (blur images/video): OFF",
                bg="#cba6f7",
            )

    def _apply_click_through(self):
        enabled = self.click_through_var.get()
        if self._blur_win:
            self._blur_win.set_click_through(enabled)
            if enabled:
                # Click-through mode is intended to stay on top.
                if not self.always_on_top_var.get():
                    self.always_on_top_var.set(True)
                self._apply_always_on_top()
                self.status_var.set("Click-through ON — interact with app below blur area")
            else:
                self.status_var.set("Click-through OFF — blur window is interactive again")
        if hasattr(self, "click_btn"):
            if enabled:
                self.click_btn.config(text="🖱 Click-through: ON", bg="#94e2d5")
            else:
                self.click_btn.config(text="🖱 Click-through: OFF", bg="#f9e2af")

    def _enforce_topmost_loop(self):
        if self.always_on_top_var.get():
            self._apply_always_on_top()
        self.root.after(1200, self._enforce_topmost_loop)

    # ── run ───────────────────────────────────────────────────────────────────

    def run(self):
        self._enforce_topmost_loop()
        self.root.mainloop()


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = ControlPanel()
    app.run()