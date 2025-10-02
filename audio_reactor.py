# Audio-reactive overlay for ALL windows (Windows 10/11)
# - PyQt6 overlay windows (one per monitor), click-through + always-on-top
# - WASAPI loopback audio via 'soundcard' (fallback 'sounddevice')
# - Pulses global ambient + draws outlines around visible top-level windows
#
# pip install PyQt6 soundcard numpy
# optional fallback: pip install sounddevice
#
# Run: python audio_reactor.py

import sys, os, math, threading, time, ctypes
import numpy as np
from ctypes import wintypes
from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt

# ============================
# Audio capture (loopback)
# ============================

class AudioWorker(QtCore.QThread):
    level = QtCore.pyqtSignal(float)  # smoothed 0..1 amplitude
    spectrum = QtCore.pyqtSignal(float)  # optional spectral centroid [0..1]

    def __init__(self, samplerate=48000, blocksize=1024):
        super().__init__()
        self.samplerate = samplerate
        self.blocksize = blocksize
        self._stop = threading.Event()

    def stop(self):
        self._stop.set()

    def _run_soundcard(self):
        import soundcard as sc
        spk = sc.default_speaker()
        mic = sc.get_microphone(id=str(spk.name), include_loopback=True)
        alpha = 0.15
        smooth = 0.0
        with mic.recorder(samplerate=self.samplerate, channels=2) as rec:
            while not self._stop.is_set():
                data = rec.record(numframes=self.blocksize)  # shape (N, 2)
                if data is None or len(data)==0: continue
                mono = data.mean(axis=1).astype(np.float32)
                rms = float(np.sqrt(np.mean(mono**2)) + 1e-9)
                # compress a bit for UI
                db = min(1.0, (rms*8.0))   # tweak gain as desired
                smooth = (1-alpha)*smooth + alpha*db
                # simple spectral centroid for fun (0..1)
                spec = np.fft.rfft(mono * np.hanning(len(mono)))
                mag = np.abs(spec)
                if mag.sum() > 1e-8:
                    freqs = np.fft.rfftfreq(len(mono), d=1.0/self.samplerate)
                    centroid = (mag*freqs).sum()/(mag.sum()+1e-12)
                    norm_centroid = max(0.0, min(1.0, centroid/8000.0))
                else:
                    norm_centroid = 0.0
                self.level.emit(smooth)
                self.spectrum.emit(norm_centroid)

    def _run_sounddevice(self):
        import sounddevice as sd
        alpha = 0.15
        smooth = 0.0
        # try WASAPI loopback extra settings
        try:
            extra = sd.WasapiSettings(loopback=True)
        except Exception:
            extra = None
        with sd.InputStream(samplerate=self.samplerate, channels=2, dtype='float32',
                            blocksize=self.blocksize, extra_settings=extra) as stream:
            while not self._stop.is_set():
                data, _ = stream.read(self.blocksize)  # (N, 2)
                if data is None or len(data)==0: continue
                mono = data.mean(axis=1).astype(np.float32)
                rms = float(np.sqrt(np.mean(mono**2)) + 1e-9)
                db = min(1.0, (rms*8.0))
                smooth = (1-alpha)*smooth + alpha*db
                spec = np.fft.rfft(mono * np.hanning(len(mono)))
                mag = np.abs(spec)
                if mag.sum() > 1e-8:
                    freqs = np.fft.rfftfreq(len(mono), d=1.0/self.samplerate)
                    centroid = (mag*freqs).sum()/(mag.sum()+1e-12)
                    norm_centroid = max(0.0, min(1.0, centroid/8000.0))
                else:
                    norm_centroid = 0.0
                self.level.emit(smooth)
                self.spectrum.emit(norm_centroid)

    def run(self):
        try:
            import soundcard  # noqa
            self._run_soundcard()
        except Exception:
            # Fallback to sounddevice if available
            try:
                import sounddevice  # noqa
                self._run_sounddevice()
            except Exception as e:
                # Emit zeros, keep UI alive
                print("Audio backends failed:", e)
                while not self._stop.is_set():
                    self.level.emit(0.0)
                    self.spectrum.emit(0.0)
                    self.msleep(33)

# ============================
# Win32 helpers (window rects / DPI)
# ============================

user32 = ctypes.windll.user32
dwmapi = ctypes.windll.dwmapi
shcore = None
try:
    shcore = ctypes.windll.shcore
except Exception:
    pass

EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

DWMWA_EXTENDED_FRAME_BOUNDS = 9
DWMWA_CLOAKED = 14

class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long),
                ("top", ctypes.c_long),
                ("right", ctypes.c_long),
                ("bottom", ctypes.c_long)]
    def width(self): return self.right - self.left
    def height(self): return self.bottom - self.top

def is_window_visible_top(hwnd):
    if not user32.IsWindowVisible(hwnd): return False
    if user32.IsIconic(hwnd): return False
    # skip cloaked (hidden by OS like UWP background)
    cloaked = ctypes.c_int(0)
    dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED,
                                 ctypes.byref(cloaked),
                                 ctypes.sizeof(cloaked))
    if cloaked.value != 0: return False
    # skip tool windows (like tooltips)
    GWL_EXSTYLE = -20
    exstyle = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    WS_EX_TOOLWINDOW = 0x00000080
    if exstyle & WS_EX_TOOLWINDOW: return False
    # has a title or app window style?
    WS_EX_APPWINDOW = 0x00040000
    if not (exstyle & WS_EX_APPWINDOW) and user32.GetWindowTextLengthW(hwnd)==0:
        # still allow if it's active/foreground
        if hwnd != user32.GetForegroundWindow():
            return False
    # non-empty rect
    r = RECT()
    if dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_EXTENDED_FRAME_BOUNDS,
                                    ctypes.byref(r), ctypes.sizeof(r)) != 0:
        user32.GetWindowRect(hwnd, ctypes.byref(r))
    if r.width() <= 5 or r.height() <= 5: return False
    return True

def get_window_rect(hwnd):
    r = RECT()
    if dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_EXTENDED_FRAME_BOUNDS,
                                    ctypes.byref(r), ctypes.sizeof(r)) != 0:
        user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r

def dpi_scale_for_rect(rect):
    # map a rect to its monitor and get effective DPI (96=1.0)
    MONITOR_DEFAULTTONEAREST = 2
    MONITORINFOEXW = 0
    hmon = user32.MonitorFromRect(ctypes.byref(rect), MONITOR_DEFAULTTONEAREST)
    if shcore:
        MDT_EFFECTIVE_DPI = 0
        dpiX = ctypes.c_uint(); dpiY = ctypes.c_uint()
        if shcore.GetDpiForMonitor(hmon, MDT_EFFECTIVE_DPI,
                                   ctypes.byref(dpiX), ctypes.byref(dpiY)) == 0:
            return dpiX.value / 96.0
    # fallback
    return 1.0

def enumerate_windows():
    result = []

    @EnumWindowsProc
    def cb(hwnd, lParam):
        try:
            if is_window_visible_top(hwnd):
                r = get_window_rect(hwnd)
                result.append((hwnd, r))
        except Exception:
            pass
        return True

    user32.EnumWindows(cb, 0)
    return result

# ============================
# Overlay windows (one per screen)
# ============================

class Overlay(QtWidgets.QWidget):
    def __init__(self, screen: QtGui.QScreen, controller):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
        self.ctrl = controller
        # geometry per monitor
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setWindowState(Qt.WindowState.WindowFullScreen)
        self.setGeometry(screen.geometry())  # logical coords
        # click-through
        self._make_clickthrough()
        # timers
        self.repaintTimer = QtCore.QTimer(self, interval=16, timeout=self.update)  # ~60fps
        self.repaintTimer.start()
        self.scanTimer = QtCore.QTimer(self, interval=300, timeout=self._scan_windows)
        self.scanTimer.start()
        self._rects = []  # logical rects on this screen

    def _make_clickthrough(self):
        hwnd = int(self.winId())
        GWL_EXSTYLE = -20
        WS_EX_LAYERED = 0x00080000
        WS_EX_TRANSPARENT = 0x00000020
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED | WS_EX_TRANSPARENT)

    def _scan_windows(self):
        # collect rects that intersect this overlay's screen
        screen_geo = self.geometry()
        sx, sy, sw, sh = screen_geo.x(), screen_geo.y(), screen_geo.width(), screen_geo.height()
        screen_rect = (sx, sy, sx+sw, sy+sh)
        rects = []
        for hwnd, r in enumerate_windows():
            # map physical px -> logical (divide by DPI scale for that monitor)
            scale = dpi_scale_for_rect(r)
            L, T = int(r.left/scale), int(r.top/scale)
            R, B = int(r.right/scale), int(r.bottom/scale)
            # keep ones that intersect our screen
            if (R > sx and L < sx+sw and B > sy and T < sy+sh):
                rects.append((hwnd, QtCore.QRect(L, T, R-L, B-T)))
        self._rects = rects

    def paintEvent(self, e):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)

        W, H = self.width(), self.height()
        amp = self.ctrl.current_amp  # 0..1
        spc = self.ctrl.current_spec  # 0..1

        # ==== 1) Global ambient (subtle) ====
        # opacity tied to amplitude; hue shift with centroid
        hue = int(200 + 100*spc) % 360
        col = QtGui.QColor.fromHsv(hue, 80, 255, int(80 * min(1.0, 0.2 + amp*0.8)))
        grad = QtGui.QRadialGradient(W/2, H/2, max(W,H)/1.1)
        grad.setColorAt(0.0, col)
        grad.setColorAt(1.0, QtGui.QColor(0,0,0,0))
        p.setCompositionMode(QtGui.QPainter.CompositionMode.CompositionMode_Screen)
        p.fillRect(self.rect(), QtGui.QBrush(grad))

        # ==== 2) Window outlines ====
        # base alpha scales with amp; foreground window gets boost
        fg = user32.GetForegroundWindow()

        base_alpha = int(20 + 140*amp)          # 20..160
        thick = max(1.0, 2.0 + 6.0*amp)         # pen width
        glow_alpha = int(10 + 110*amp)          # outer soft pass

        for hwnd, r in self._rects:
            rr = r.adjusted(2,2,-2,-2)          # shrink slightly inside edges
            path = QtGui.QPainterPath()
            radius = 12.0
            path.addRoundedRect(rr, radius, radius)

            # soft outer glow pass
            p.setCompositionMode(QtGui.QPainter.CompositionMode.CompositionMode_Screen)
            p.setPen(QtGui.QPen(QtGui.QColor(hue, 120, 255, glow_alpha), thick*2.0))
            p.drawPath(path)

            # crisp inner stroke
            alpha = base_alpha + (70 if hwnd == fg else 0)
            p.setPen(QtGui.QPen(QtGui.QColor(hue, 60, 255, min(alpha, 255)), thick))
            p.drawPath(path)

        p.end()

# ============================
# Controller window
# ============================

class Controller(QtWidgets.QWidget):
    def __init__(self, app: QtWidgets.QApplication):
        super().__init__()
        self.setWindowTitle("Audio-Reactive Overlay (All Windows)")
        self.current_amp = 0.0
        self.current_spec = 0.0
        self._build_ui()

        # audio worker
        self.audio = AudioWorker()
        self.audio.level.connect(self._on_level)
        self.audio.spectrum.connect(self._on_spec)
        self.audio.start()

        # overlays per screen
        self._overlays = []
        for s in app.screens():
            ov = Overlay(s, self)
            ov.show()
            self._overlays.append(ov)

        # perf timer (optional FPS limiter toggle)
        self.fpsLimiter = QtCore.QTimer(self, interval=1000, timeout=self._update_stats)
        self.fpsLimiter.start()
        self._frames = 0

    def closeEvent(self, e):
        # cleanly stop audio + close overlays
        try:
            self.audio.stop()
            self.audio.wait(500)
        except Exception:
            pass
        for ov in self._overlays:
            ov.close()
        e.accept()

    def _build_ui(self):
        layout = QtWidgets.QFormLayout(self)
        self.intensity = QtWidgets.QDoubleSpinBox(); self.intensity.setRange(0.1, 3.0); self.intensity.setSingleStep(0.05); self.intensity.setValue(1.0)
        self.threshold = QtWidgets.QDoubleSpinBox(); self.threshold.setRange(0.0, 1.0); self.threshold.setSingleStep(0.01); self.threshold.setValue(0.02)
        self.latency = QtWidgets.QSpinBox(); self.latency.setRange(1, 50); self.latency.setValue(16)  # ms repaint hint
        self.pauseBtn = QtWidgets.QPushButton("Pause/Resume Overlays")
        self.status = QtWidgets.QLabel("…")

        layout.addRow("Intensity", self.intensity)
        layout.addRow("Noise gate (threshold)", self.threshold)
        layout.addRow("Target frame interval (ms)", self.latency)
        layout.addRow(self.pauseBtn)
        layout.addRow("Status", self.status)

        self.pauseBtn.clicked.connect(self._toggle_overlays)
        self.latency.valueChanged.connect(self._apply_latency)

    def _on_level(self, a):
        # apply noise gate + user intensity
        thr = self.threshold.value()
        a = 0.0 if a < thr else (a - thr) / (1.0 - thr)
        self.current_amp = max(0.0, min(1.0, a * self.intensity.value()))

    def _on_spec(self, s):
        self.current_spec = s

    def _toggle_overlays(self):
        any_visible = any(ov.isVisible() for ov in self._overlays)
        for ov in self._overlays:
            ov.setVisible(not any_visible)

    def _apply_latency(self):
        iv = self.latency.value()
        for ov in self._overlays:
            ov.repaintTimer.setInterval(iv)

    def _update_stats(self):
        self.status.setText(f"Amp={self.current_amp:.2f}  Spec={self.current_spec:.2f}  Monitors={len(self._overlays)}")

# ============================
# Entrypoint
# ============================

if __name__ == "__main__":
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    app = QtWidgets.QApplication(sys.argv)
    c = Controller(app)
    c.show()  # small controller window; overlays are separate
    sys.exit(app.exec())
