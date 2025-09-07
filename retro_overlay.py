# overlay_studio_gui.py
# Windows 10/11 • Python 3.9+ • PyQt6
# Click-through, always-on-top overlay with easy presets:
# Filmic, CRT Retro, Sci-Fi HUD, Cyber Grid, Steampunk, Vaporwave, Matrix Rain (lite)
#
# Run: python overlay_studio_gui.py
#
# Notes:
# - One overlay window per monitor
# - UI: left preset list, right quick controls (speed, opacity, accent color, frame interval)
# - Click-through via WS_EX_LAYERED | WS_EX_TRANSPARENT
# - Keep frame interval >= 16–24ms on iGPU for best battery

import os, sys, math, random
from dataclasses import dataclass, field
from typing import List, Tuple
from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt

PRESETS = [
    "Filmic",
    "CRT Retro",
    "Sci-Fi HUD",
    "Cyber Grid",
    "Steampunk",
    "Vaporwave",
    "Matrix Rain",
]

@dataclass
class OverlayState:
    preset: str = "Filmic"
    accent: QtGui.QColor = field(default_factory=lambda: QtGui.QColor(0, 220, 255))
    opacity: float = 0.35
    speed: int = 3
    interval_ms: int = 16
    scan_alpha: int = 40
    crt_cell: int = 2
    matrix_density: int = 36
    matrix_alpha: int = 130

# -------------------- Overlay per monitor --------------------

class Overlay(QtWidgets.QWidget):
    def __init__(self, screen: QtGui.QScreen, state: OverlayState):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
        self.state = state
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setWindowState(Qt.WindowState.WindowFullScreen)
        self.setGeometry(screen.geometry())
        self._make_clickthrough()
        self.timer = QtCore.QTimer(self, interval=self.state.interval_ms, timeout=self.update)
        self.timer.start()
        self.phase = 0.0
        self._seed = random.randint(0, 10**9)
        self._rng = random.Random(self._seed)
        # matrix columns (x, y, speed)
        self._matrix_cols: List[Tuple[int, float, float]] = []
        self._build_matrix()

    def _make_clickthrough(self):
        import ctypes
        hwnd = int(self.winId())
        GWL_EXSTYLE = -20
        WS_EX_LAYERED = 0x00080000
        WS_EX_TRANSPARENT = 0x00000020
        style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED | WS_EX_TRANSPARENT)

    def set_interval(self, ms: int):
        self.timer.setInterval(ms)

    def set_preset(self, name: str):
        self.state.preset = name
        self._build_matrix()  # refresh pattern if needed

    def _build_matrix(self):
        # prepare columns for Matrix preset
        self._matrix_cols.clear()
        W = max(1, self.width())
        cols = max(4, self.state.matrix_density)
        step = max(8, W // cols)
        rng = random.Random(self._seed ^ 0xA5A5)
        for x in range(0, W, step):
            speed = 0.15 + 0.65 * rng.random()
            y0 = rng.uniform(0, self.height())
            self._matrix_cols.append((x, y0, speed))

    # ----------- painting -----------

    def paintEvent(self, ev):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        W, H = self.width(), self.height()
        # advance phase by speed
        self.phase = (self.phase + max(0.0, self.state.speed) * 0.005) % 1.0

        # draw selected preset
        preset = self.state.preset
        if preset == "Filmic":
            self._draw_filmic(p, W, H)
        elif preset == "CRT Retro":
            self._draw_crt(p, W, H)
        elif preset == "Sci-Fi HUD":
            self._draw_scifi(p, W, H)
        elif preset == "Cyber Grid":
            self._draw_cyber_grid(p, W, H)
        elif preset == "Steampunk":
            self._draw_steampunk(p, W, H)
        elif preset == "Vaporwave":
            self._draw_vaporwave(p, W, H)
        elif preset == "Matrix Rain":
            self._draw_matrix(p, W, H)

        p.end()

    # ----------- layers -----------

    def _draw_noise(self, p: QtGui.QPainter, W: int, H: int, strength: float):
        img = QtGui.QImage(W, H, QtGui.QImage.Format.Format_Grayscale8)
        buf = img.bits(); buf.setsize(W * H)
        import os; buf[:] = os.urandom(W * H)
        p.setOpacity(max(0.0, min(1.0, strength)))
        p.drawImage(0, 0, img)
        p.setOpacity(1.0)

    def _draw_vignette(self, p: QtGui.QPainter, W: int, H: int, center_alpha: int, color=QtGui.QColor(255,255,255)):
        grad = QtGui.QRadialGradient(W/2, H/2, max(W, H)/1.15)
        c = QtGui.QColor(color); c.setAlpha(center_alpha)
        grad.setColorAt(0.0, c)
        grad.setColorAt(1.0, QtGui.QColor(0,0,0,0))
        p.setCompositionMode(QtGui.QPainter.CompositionMode.CompositionMode_Screen)
        p.fillRect(0, 0, W, H, QtGui.QBrush(grad))
        p.setCompositionMode(QtGui.QPainter.CompositionMode.CompositionMode_SourceOver)

    def _draw_scanlines(self, p: QtGui.QPainter, W: int, H: int, alpha: int, step: int = 2):
        pen = QtGui.QPen(QtGui.QColor(0, 0, 0, alpha))
        p.setPen(pen)
        y = 0
        while y < H:
            p.drawLine(0, y, W, y)
            y += step

    def _draw_crt_mask(self, p: QtGui.QPainter, W: int, H: int, cell: int, alpha: int):
        for x in range(0, W, cell * 3):
            p.fillRect(x, 0, cell, H, QtGui.QColor(255, 0, 0, alpha))
            p.fillRect(x + cell, 0, cell, H, QtGui.QColor(0, 255, 0, alpha))
            p.fillRect(x + cell * 2, 0, cell, H, QtGui.QColor(0, 0, 255, alpha))

    # ----------- preset implementations -----------

    def _draw_filmic(self, p, W, H):
        self._draw_noise(p, W, H, strength=min(0.12, 0.03 + self.state.opacity * 0.35))
        self._draw_scanlines(p, W, H, alpha=int(20 + self.state.opacity*40), step=2)
        self._draw_vignette(p, W, H, center_alpha=int(24 + self.state.opacity*60))

    def _draw_crt(self, p, W, H):
        self._draw_scanlines(p, W, H, alpha=self.state.scan_alpha, step=2)
        self._draw_crt_mask(p, W, H, cell=self.state.crt_cell, alpha=22)
        self._draw_vignette(p, W, H, center_alpha=18)

    def _draw_scifi(self, p, W, H):
        # rotating HUD rings, arcs, and blips (cyan by default)
        col = QtGui.QColor(self.state.accent)
        col.setAlpha(int(110 * self.state.opacity + 30))
        center = QtCore.QPointF(W/2, H/2)
        p.setCompositionMode(QtGui.QPainter.CompositionMode.CompositionMode_Screen)

        # rings
        for i, r in enumerate([min(W, H)/6, min(W, H)/4, min(W, H)/3]):
            a = self.phase * (50 + i*20)
            p.save()
            p.translate(center)
            p.rotate(a)
            pen = QtGui.QPen(col, 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            # partial arcs
            rect = QtCore.QRectF(-r, -r, 2*r, 2*r)
            p.drawArc(rect, 0, 80*16)
            p.drawArc(rect, 140*16, 50*16)
            p.drawArc(rect, 230*16, 35*16)
            p.restore()

        # crosshair
        pen = QtGui.QPen(col, 1.5)
        p.setPen(pen)
        p.drawLine(W/2 - 80, H/2, W/2 + 80, H/2)
        p.drawLine(W/2, H/2 - 80, W/2, H/2 + 80)

        # blips
        rng = self._rng
        rng.seed(int(self.phase*1000) ^ self._seed)
        for _ in range(8):
            a = rng.uniform(0, math.tau)
            r = rng.uniform(40, min(W, H)/3)
            x = W/2 + math.cos(a)*r
            y = H/2 + math.sin(a)*r
            g = QtGui.QRadialGradient(x, y, 16)
            cc = QtGui.QColor(col); cc.setAlpha(160)
            g.setColorAt(0.0, cc); cc2 = QtGui.QColor(col); cc2.setAlpha(0); g.setColorAt(1.0, cc2)
            p.fillRect(x-16, y-16, 32, 32, QtGui.QBrush(g))

        p.setCompositionMode(QtGui.QPainter.CompositionMode.CompositionMode_SourceOver)

    def _draw_cyber_grid(self, p, W, H):
        # scrolling neon grid (simple planar)
        col = QtGui.QColor(self.state.accent)
        alpha = int(80 + 150 * self.state.opacity)
        col.setAlpha(alpha)
        p.setCompositionMode(QtGui.QPainter.CompositionMode.CompositionMode_Screen)
        p.setPen(QtGui.QPen(col, 1.2))
        # scroll
        off = int(self.phase * 40) % 40
        # vertical lines
        step = max(20, W // 32)
        for x in range(-off, W+off, step):
            p.drawLine(x, 0, x, H)
        # horizontal lines
        for y in range(-off, H+off, step):
            p.drawLine(0, y, W, y)
        # subtle center bloom
        self._draw_vignette(p, W, H, center_alpha=20, color=self.state.accent)
        p.setCompositionMode(QtGui.QPainter.CompositionMode.CompositionMode_SourceOver)

    def _gear_path(self, cx, cy, r, teeth=10, inner=0.65) -> QtGui.QPainterPath:
        path = QtGui.QPainterPath()
        for i in range(teeth*2):
            ang = (i / (teeth*2.0)) * math.tau
            rr = r if (i % 2 == 0) else r*inner
            x, y = cx + rr*math.cos(ang), cy + rr*math.sin(ang)
            if i == 0: path.moveTo(x, y)
            else: path.lineTo(x, y)
        path.closeSubpath()
        return path

    def _draw_steampunk(self, p, W, H):
        # brass tint + spinning gears + vignette
        p.save()
        tint = QtGui.QColor(180, 120, 40, int(60 * self.state.opacity + 30))
        p.fillRect(0, 0, W, H, tint)

        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        p.setPen(QtGui.QPen(QtGui.QColor(20, 12, 4, 160), 1.2))
        br = QtGui.QColor(220, 170, 90, 160)
        p.setBrush(br)

        rng = self._rng
        rng.seed(self._seed)
        gears = [
            (W*0.25, H*0.3, min(W, H)*0.08, 12,  +80),
            (W*0.55, H*0.55, min(W, H)*0.12, 10, -60),
            (W*0.78, H*0.35, min(W, H)*0.07,  8, +100),
        ]
        for cx, cy, r, teeth, rpm in gears:
            path = self._gear_path(cx, cy, r, teeth=teeth, inner=0.68)
            p.save()
            p.translate(cx, cy)
            p.rotate(self.phase * rpm * 360)
            p.translate(-cx, -cy)
            p.drawPath(path)
            p.restore()

        p.restore()
        # slight vignette
        self._draw_vignette(p, W, H, center_alpha=int(24 + self.state.opacity*40))

    def _draw_vaporwave(self, p, W, H):
        # sunset stripes + diagonal neon strokes
        p.setCompositionMode(QtGui.QPainter.CompositionMode.CompositionMode_Screen)
        # horizon gradient
        grad = QtGui.QLinearGradient(0, 0, 0, H)
        grad.setColorAt(0.0, QtGui.QColor(255, 100, 150, 80))
        grad.setColorAt(0.5, QtGui.QColor(255, 180, 80, 80))
        grad.setColorAt(1.0, QtGui.QColor(60, 80, 170, 80))
        p.fillRect(0, 0, W, H, QtGui.QBrush(grad))

        # sun stripes
        sunR = min(W, H)/6
        y0 = H*0.35
        for i in range(16):
            yy = y0 + (i - 8) * 6
            alpha = max(0, 140 - i*10)
            col = QtGui.QColor(255, 180, 90, alpha)
            p.fillRect(W/2 - sunR, yy, sunR*2, 3, col)

        # diagonal strokes
        col = QtGui.QColor(self.state.accent); col.setAlpha(120)
        pen = QtGui.QPen(col, 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        off = int(self.phase * 80) % 80
        for y in range(-H, H, 40):
            p.drawLine(-off, y, W-off, y+W*0.25)

        p.setCompositionMode(QtGui.QPainter.CompositionMode.CompositionMode_SourceOver)
        self._draw_vignette(p, W, H, center_alpha=18)

    def _draw_matrix(self, p, W, H):
        # lightweight falling “glyphs” (just soft dots for perf)
        p.setCompositionMode(QtGui.QPainter.CompositionMode.CompositionMode_Screen)
        base = QtGui.QColor(80, 255, 120, self.state.matrix_alpha)
        trail = QtGui.QColor(80, 255, 120, int(self.state.matrix_alpha*0.35))
        for ix, (x, y, spd) in enumerate(self._matrix_cols):
            # advance
            y2 = (y + (self.state.speed + 1) * spd * 6) % (H + 60)
            self._matrix_cols[ix] = (x, y2, spd)
            # head glow
            g = QtGui.QRadialGradient(x, y2, 10)
            g.setColorAt(0.0, base); g.setColorAt(1.0, QtGui.QColor(base.red(), base.green(), base.blue(), 0))
            p.fillRect(x-12, y2-12, 24, 24, QtGui.QBrush(g))
            # short trail
            p.fillRect(x-1, int(y2-18), 2, 18, trail)
        p.setCompositionMode(QtGui.QPainter.CompositionMode.CompositionMode_SourceOver)

# -------------------- Controller GUI --------------------

class Studio(QtWidgets.QWidget):
    def __init__(self, app: QtWidgets.QApplication):
        super().__init__()
        self.setWindowTitle("Overlay Studio — Retro, Sci-Fi, Steampunk, more")
        self.state = OverlayState()
        self._build_ui()
        # overlays per screen
        self.overlays: List[Overlay] = [Overlay(s, self.state) for s in app.screens()]
        for ov in self.overlays: ov.show()

    def _build_ui(self):
        layout = QtWidgets.QHBoxLayout(self)

        # Preset list (big, easy to hit)
        self.list = QtWidgets.QListWidget()
        self.list.setIconSize(QtCore.QSize(16,16))
        for name in PRESETS:
            it = QtWidgets.QListWidgetItem(name)
            it.setSizeHint(QtCore.QSize(160, 34))
            self.list.addItem(it)
        self.list.setCurrentRow(0)
        self.list.currentTextChanged.connect(self._preset_changed)
        layout.addWidget(self.list, 0)

        # Right panel: quick controls
        right = QtWidgets.QVBoxLayout()

        # Top row: Start/Stop, preset title
        row = QtWidgets.QHBoxLayout()
        self.toggleBtn = QtWidgets.QPushButton("Stop Overlays")
        self.title = QtWidgets.QLabel("Filmic")
        self.title.setStyleSheet("QLabel{font-weight:600;font-size:16px;}")
        row.addWidget(self.toggleBtn); row.addStretch(1); row.addWidget(self.title)
        right.addLayout(row)

        grid = QtWidgets.QGridLayout()
        # Accent color
        self.colorBtn = QtWidgets.QPushButton("Accent Color")
        # Opacity
        self.opacity = QtWidgets.QDoubleSpinBox(); self.opacity.setRange(0.05, 1.0); self.opacity.setSingleStep(0.05); self.opacity.setValue(self.state.opacity)
        # Speed
        self.speed = QtWidgets.QSpinBox(); self.speed.setRange(0, 10); self.speed.setValue(self.state.speed)
        # Frame interval
        self.interval = QtWidgets.QSpinBox(); self.interval.setRange(8, 100); self.interval.setValue(self.state.interval_ms)

        grid.addWidget(QtWidgets.QLabel("Opacity"), 0, 0); grid.addWidget(self.opacity, 0, 1)
        grid.addWidget(QtWidgets.QLabel("Speed"),   1, 0); grid.addWidget(self.speed,   1, 1)
        grid.addWidget(QtWidgets.QLabel("Frame interval (ms)"), 2, 0); grid.addWidget(self.interval, 2, 1)
        grid.addWidget(self.colorBtn, 3, 0, 1, 2)
        right.addLayout(grid)

        # Contextual knobs (show for CRT/Matrix)
        self.crtAlpha = QtWidgets.QSpinBox(); self.crtAlpha.setRange(0, 255); self.crtAlpha.setValue(self.state.scan_alpha)
        self.crtCell  = QtWidgets.QSpinBox(); self.crtCell.setRange(1, 10);   self.crtCell.setValue(self.state.crt_cell)
        self.mxCols   = QtWidgets.QSpinBox(); self.mxCols.setRange(8, 120);   self.mxCols.setValue(self.state.matrix_density)
        self.mxAlpha  = QtWidgets.QSpinBox(); self.mxAlpha.setRange(20, 255); self.mxAlpha.setValue(self.state.matrix_alpha)

        self.advBox = QtWidgets.QGroupBox("Preset options")
        form = QtWidgets.QFormLayout(self.advBox)
        form.addRow("Scanlines α (CRT/Filmic)", self.crtAlpha)
        form.addRow("CRT cell size", self.crtCell)
        form.addRow("Matrix columns", self.mxCols)
        form.addRow("Matrix α", self.mxAlpha)
        right.addWidget(self.advBox)

        right.addStretch(1)
        layout.addLayout(right, 1)

        # wiring
        self.toggleBtn.clicked.connect(self._toggle_overlays)
        self.colorBtn.clicked.connect(self._pick_color)
        self.opacity.valueChanged.connect(self._update_values)
        self.speed.valueChanged.connect(self._update_values)
        self.interval.valueChanged.connect(self._update_values)
        self.crtAlpha.valueChanged.connect(self._update_values)
        self.crtCell.valueChanged.connect(self._update_values)
        self.mxCols.valueChanged.connect(self._update_values)
        self.mxAlpha.valueChanged.connect(self._update_values)

    # ---- handlers ----

    def _preset_changed(self, name: str):
        self.state.preset = name
        self.title.setText(name)
        for ov in self.overlays:
            ov.set_preset(name)
            ov.update()

    def _toggle_overlays(self):
        any_visible = any(ov.isVisible() for ov in self.overlays)
        for ov in self.overlays: ov.setVisible(not any_visible)
        self.toggleBtn.setText("Start Overlays" if any_visible else "Stop Overlays")

    def _pick_color(self):
        c = QtWidgets.QColorDialog.getColor(self.state.accent, self, "Accent color")
        if c.isValid():
            self.state.accent = c
            for ov in self.overlays: ov.update()

    def _update_values(self, *_):
        self.state.opacity = self.opacity.value()
        self.state.speed = self.speed.value()
        self.state.interval_ms = self.interval.value()
        self.state.scan_alpha = self.crtAlpha.value()
        self.state.crt_cell = self.crtCell.value()
        self.state.matrix_density = self.mxCols.value()
        self.state.matrix_alpha = self.mxAlpha.value()
        for ov in self.overlays:
            ov.set_interval(self.state.interval_ms)
            if self.state.preset == "Matrix Rain":
                ov._build_matrix()
            ov.update()

# -------------------- main --------------------

if __name__ == "__main__":
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    app = QtWidgets.QApplication(sys.argv)
    studio = Studio(app); studio.resize(800, 420); studio.show()
    sys.exit(app.exec())
