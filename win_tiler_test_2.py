#!/usr/bin/env python3
import os
import json
import time
import threading
import numbers
import numpy as np
from pynput import mouse, keyboard
import win32gui, win32con, win32api

from PyQt6 import QtCore, QtGui, QtWidgets

# ——— Configuration ———
GESTURE_TIMEOUT = 1.0
MIN_STROKE = 80
SCREEN_W = win32api.GetSystemMetrics(0)
SCREEN_H = win32api.GetSystemMetrics(1)
MAPPINGS_FILE = 'mappings.json'
EDGE_MARGIN = 10        # pixels for edge/corner resize hit test
MIN_WIDTH = 40
MIN_HEIGHT = 30

# ——— Gesture Recording (unchanged) ———
class Recorder:
    def __init__(self):
        self.pts = []
        self.lock = threading.Lock()
        self.mouse = mouse.Listener(on_move=self.on_move)
        self.mouse.daemon = True
        self.mouse.start()

    def on_move(self, x, y):
        with self.lock:
            self.pts.append((x, y))

    def clear(self):
        with self.lock:
            self.pts.clear()

    def fetch(self):
        with self.lock:
            arr = np.array(self.pts)
            self.pts.clear()
        return arr

# ——— Gesture Detectors (unchanged) ———
def make_L_detector(dy_sign, dx_sign):
    def detect(pts):
        if len(pts) < 6: return False
        m = len(pts)//2
        v1 = pts[m-1] - pts[0]
        v2 = pts[-1] - pts[m]
        return (abs(v1[1]) > abs(v1[0]) and v1[1]*dy_sign > MIN_STROKE and
                abs(v2[0]) > abs(v2[1]) and v2[0]*dx_sign > MIN_STROKE)
    return detect

def detect_V(pts):
    if len(pts) < 8: return False
    t = len(pts)//3
    v1 = pts[t]    - pts[0]
    v2 = pts[2*t] - pts[t]
    return (v1[1] > MIN_STROKE and v1[0] > MIN_STROKE and
            v2[1] < -MIN_STROKE and v2[0] > MIN_STROKE)

def get_monitor_rect_from_point(x, y):
    """
    Return (left, top, right, bottom) for the monitor containing (x,y).
    """
    mon = win32api.MonitorFromPoint((int(x), int(y)), win32con.MONITOR_DEFAULTTONEAREST)
    info = win32api.GetMonitorInfo(mon)
    return info['Monitor']  # tuple (left, top, right, bottom)

def get_monitor_rect_for_window(hwnd):
    """
    Return (left, top, right, bottom) for the monitor containing hwnd.
    """
    mon = win32api.MonitorFromWindow(hwnd, win32con.MONITOR_DEFAULTTONEAREST)
    info = win32api.GetMonitorInfo(mon)
    return info['Monitor']


GESTURES = {
    'L_down_right': make_L_detector(+1, +1),
    'L_up_right':   make_L_detector(-1, +1),
    'L_down_left':  make_L_detector(+1, -1),
    'L_up_left':    make_L_detector(-1, -1),
    'V_shape':      detect_V,
}
def enum_tilable_windows():
    """
    Return a list of candidate top-level HWNDs (Z-order top->bottom) that are
    visible, have non-empty title, and are not tool-windows.
    """
    wins = []
    def _cb(hwnd, lparam):
        try:
            if not win32gui.IsWindowVisible(hwnd):
                return True
            title = win32gui.GetWindowText(hwnd) or ""
            if not title.strip():
                return True
            ex = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
            # skip tool windows (like floating palette windows)
            if ex & win32con.WS_EX_TOOLWINDOW:
                return True
        except Exception:
            return True
        wins.append(hwnd)
        return True

    win32gui.EnumWindows(_cb, None)
    return wins

def tile_window(cfg):
    """
    Accept cfg as a single region-dict or list of region-dicts (fractions saved relative to the monitor
    on which they were created). For each region we pick a candidate top-level window and map the
    fractions to that window's monitor rectangle so placement is monitor-correct.
    """
    # normalize cfg into list of region dicts (reuse region_from_value)
    regions = []
    if isinstance(cfg, dict):
        r = region_from_value(cfg)
        if r: regions.append(r)
    elif isinstance(cfg, (list, tuple)):
        # handle both flat [x,y,w,h] and list of region-dicts
        if len(cfg) >= 4 and all(isinstance(x, numbers.Number) for x in cfg[:4]):
            r = region_from_value(cfg)
            if r: regions.append(r)
        else:
            for elem in cfg:
                r = region_from_value(elem)
                if r:
                    regions.append(r)
    else:
        r = region_from_value(cfg)
        if r: regions.append(r)

    if not regions:
        print(f"[win-tiler] ⚠️  Invalid mapping format for gesture: {cfg!r}")
        return

    # find candidate windows
    candidates = enum_tilable_windows()
    if not candidates:
        print("[win-tiler] ⚠️  No candidate top-level windows found to tile.")
        return

    focused = win32gui.GetForegroundWindow()
    if focused in candidates:
        candidates.remove(focused)
        candidates.insert(0, focused)

    n_to_tile = min(len(regions), len(candidates))
    for i in range(n_to_tile):
        region = regions[i]
        hwnd = candidates[i]

        # get monitor rect for this hwnd (physical pixels and origin)
        left, top, right, bottom = get_monitor_rect_for_window(hwnd)
        mon_w = right - left
        mon_h = bottom - top
        if mon_w <= 0 or mon_h <= 0:
            print(f"[win-tiler] ⚠️  Invalid monitor size for hwnd={hwnd}, skipping.")
            continue

        # map fractional region -> pixel region on this monitor
        x = left + int(mon_w * region.get('x_frac', 0))
        y = top  + int(mon_h * region.get('y_frac', 0))
        w = max(1, int(mon_w * region.get('w_frac', 1)))
        h = max(1, int(mon_h * region.get('h_frac', 1)))

        try:
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            win32gui.MoveWindow(hwnd, x, y, w, h, True)
            print(f"[win-tiler] ✅  Tiled hwnd={hwnd} → monitor_rect=({left},{top},{right},{bottom}) region #{i+1}: x={region.get('x_frac'):.3f}, y={region.get('y_frac'):.3f}, w={region.get('w_frac'):.3f}, h={region.get('h_frac'):.3f}")
        except Exception as e:
            print(f"[win-tiler] ⚠️  Failed to tile hwnd={hwnd}: {e}")

    if len(regions) > n_to_tile:
        print(f"[win-tiler] ℹ️  {len(regions)-n_to_tile} region(s) not used (not enough candidate windows).")
def find_qscreen_for_monitor_rect(mon_rect):
    """
    Given a Win32 monitor rect (left,top,right,bottom) in physical pixels,
    try to find the corresponding QScreen. If none matches, return primary screen.
    """
    screens = QtGui.QGuiApplication.screens()
    for screen in screens:
        dpr = screen.devicePixelRatio()
        geom = screen.geometry()  # logical geometry
        phys_left  = int(geom.x() * dpr)
        phys_top   = int(geom.y() * dpr)
        phys_right = phys_left + int(geom.width() * dpr)
        phys_bottom= phys_top  + int(geom.height() * dpr)
        # allow a small tolerance (some rounding differences)
        if abs(phys_left - mon_rect[0]) <= 4 and abs(phys_top - mon_rect[1]) <= 4:
            return screen
    return QtGui.QGuiApplication.primaryScreen()

# ——— Helpers for mapping normalization ———
def region_from_value(v):
    if isinstance(v, dict):
        return {
            'x_frac': float(v.get('x_frac', 0)),
            'y_frac': float(v.get('y_frac', 0)),
            'w_frac': float(v.get('w_frac', 1)),
            'h_frac': float(v.get('h_frac', 1)),
        }
    if isinstance(v, (list, tuple)) and len(v) >= 4 and all(isinstance(x, numbers.Number) for x in v[:4]):
        x, y, w, h = v[:4]
        return {'x_frac': float(x), 'y_frac': float(y), 'w_frac': float(w), 'h_frac': float(h)}
    return None

def normalize_loaded(raw):
    """
    Convert saved JSON into canonical: mapping -> list of region dicts.
    If mapping file absent or gesture missing, we do NOT add defaults (empty list).
    """
    normalized = {}
    if not isinstance(raw, dict):
        return normalized
    for name, val in raw.items():
        items = []
        # single dict
        if isinstance(val, dict):
            r = region_from_value(val)
            if r: items.append(r)
        elif isinstance(val, list):
            # if list is "flat four numbers" treat as a single region
            if len(val) >=4 and all(isinstance(x, numbers.Number) for x in val[:4]):
                r = region_from_value(val)
                if r: items.append(r)
            else:
                for elem in val:
                    r = region_from_value(elem)
                    if r:
                        items.append(r)
        # else ignore bad types
        normalized[name] = items
    return normalized

def load_mappings():
    if os.path.exists(MAPPINGS_FILE):
        with open(MAPPINGS_FILE,'r', encoding='utf-8') as f:
            raw = json.load(f)
        return normalize_loaded(raw)
    # IMPORTANT: no defaults — return empty mapping so gestures start with zero regions
    return {}

def save_mappings(m):
    with open(MAPPINGS_FILE,'w', encoding='utf-8') as f:
        json.dump(m, f, indent=2)

# ——— Resizable Frame (manual resize & move) ———
class ResizableFrame(QtWidgets.QFrame):
    """
    Movable + resizable overlay rectangle. Manual resizing supported (edges & corners).
    Use integer pixel coords and global mouse positions (PyQt6 compatible).
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: rgba(100,150,250,0.45); border:2px dashed #6496FA;")
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setMouseTracking(True)

        # state for interactions:
        self._dragging = False
        self._resizing = False
        self._resize_edges = {'left':False, 'right':False, 'top':False, 'bottom':False}
        self._start_geom = None       # QRect at mouse press
        self._start_mouse = None      # QPoint global at mouse press

    def _to_point(self, qp):
        # qp may be QPointF (PyQt6) or QPoint
        try:
            return QtCore.QPoint(int(qp.x()), int(qp.y()))
        except Exception:
            return qp.toPoint()

    def mousePressEvent(self, ev):
        # Get local pos and global pos in integers
        if hasattr(ev, "position"):
            local = ev.position()
            local_pt = QtCore.QPoint(int(local.x()), int(local.y()))
        else:
            local_pt = ev.pos()
        # global pos
        if hasattr(ev, "globalPosition"):
            gp = ev.globalPosition().toPoint()
        elif hasattr(ev, "globalPos"):
            gp = ev.globalPos()
        else:
            gp = self.mapToGlobal(local_pt)

        rect = self.rect()
        x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()
        lx, ly = local_pt.x(), local_pt.y()

        # decide if edge/corner hit
        left_hit = lx <= EDGE_MARGIN
        right_hit = lx >= (w - EDGE_MARGIN)
        top_hit = ly <= EDGE_MARGIN
        bottom_hit = ly >= (h - EDGE_MARGIN)

        if left_hit or right_hit or top_hit or bottom_hit:
            # start resizing
            self._resizing = True
            self._resize_edges = {'left':left_hit, 'right':right_hit, 'top':top_hit, 'bottom':bottom_hit}
            self._start_geom = self.frameGeometry()
            self._start_mouse = gp
            self.setCursor(self._cursor_for_edges())
            ev.accept()
            return

        # else start dragging (move)
        if ev.button() == QtCore.Qt.MouseButton.LeftButton:
            self._dragging = True
            self._start_geom = self.frameGeometry()
            self._start_mouse = gp
            self.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.ClosedHandCursor))
            ev.accept()
            return

        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev):
        # update cursor when hovering edges
        if hasattr(ev, "position"):
            local = ev.position()
            local_pt = QtCore.QPoint(int(local.x()), int(local.y()))
        else:
            local_pt = ev.pos()
        rect = self.rect()
        w, h = rect.width(), rect.height()
        lx, ly = local_pt.x(), local_pt.y()

        # if not interacting, set appropriate hover cursor
        if not self._dragging and not self._resizing:
            left_hit = lx <= EDGE_MARGIN
            right_hit = lx >= (w - EDGE_MARGIN)
            top_hit = ly <= EDGE_MARGIN
            bottom_hit = ly >= (h - EDGE_MARGIN)
            edges = {'left':left_hit, 'right':right_hit, 'top':top_hit, 'bottom':bottom_hit}
            if any(edges.values()):
                # set cursor for edge(s)
                cur = self._cursor_for_edges_static(edges)
                self.setCursor(cur)
            else:
                self.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.SizeAllCursor))

        # handle drag / resize operations
        if (self._dragging or self._resizing) and self._start_mouse is not None:
            if hasattr(ev, "globalPosition"):
                gp = ev.globalPosition().toPoint()
            elif hasattr(ev, "globalPos"):
                gp = ev.globalPos()
            else:
                gp = self.mapToGlobal(local_pt)

            dx = gp.x() - self._start_mouse.x()
            dy = gp.y() - self._start_mouse.y()
            geom = self._start_geom

            if self._dragging:
                new_tl = QtCore.QPoint(geom.topLeft().x() + dx, geom.topLeft().y() + dy)
                self.move(new_tl)
            elif self._resizing:
                left = geom.left()
                top = geom.top()
                right = geom.right()
                bottom = geom.bottom()

                if self._resize_edges['left']:
                    left = geom.left() + dx
                if self._resize_edges['right']:
                    right = geom.right() + dx
                if self._resize_edges['top']:
                    top = geom.top() + dy
                if self._resize_edges['bottom']:
                    bottom = geom.bottom() + dy

                # compute new width/height and constrain by min sizes
                new_left = min(left, right)
                new_top  = min(top, bottom)
                new_right = max(left, right)
                new_bottom = max(top, bottom)
                new_w = max(MIN_WIDTH, new_right - new_left + 1)
                new_h = max(MIN_HEIGHT, new_bottom - new_top + 1)

                # apply geometry
                self.setGeometry(new_left, new_top, new_w, new_h)

            ev.accept()
            return

        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev):
        self._dragging = False
        self._resizing = False
        self._resize_edges = {'left':False, 'right':False, 'top':False, 'bottom':False}
        self._start_geom = None
        self._start_mouse = None
        self.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.SizeAllCursor))
        super().mouseReleaseEvent(ev)

    def _cursor_for_edges(self):
        return self._cursor_for_edges_static(self._resize_edges)

    @staticmethod
    def _cursor_for_edges_static(edges):
        # edges is dict with booleans left,right,top,bottom
        l = edges.get('left', False)
        r = edges.get('right', False)
        t = edges.get('top', False)
        b = edges.get('bottom', False)
        # corner cases
        if (l and t) or (r and b):
            return QtGui.QCursor(QtCore.Qt.CursorShape.SizeFDiagCursor)
        if (r and t) or (l and b):
            return QtGui.QCursor(QtCore.Qt.CursorShape.SizeBDiagCursor)
        if l or r:
            return QtGui.QCursor(QtCore.Qt.CursorShape.SizeHorCursor)
        if t or b:
            return QtGui.QCursor(QtCore.Qt.CursorShape.SizeVerCursor)
        return QtGui.QCursor(QtCore.Qt.CursorShape.ArrowCursor)

# ——— RegionSelector: show all regions for a gesture and let them be edited ———
class RegionSelector(QtWidgets.QWidget):
    """
    When opened for a gesture, show all regions (blue frames).
    They persist until removed. 'Add Region' creates a new one. Save writes changes.
    """
    def __init__(self, gesture_name, mappings):
        super().__init__(None,
            QtCore.Qt.WindowType.Window
            | QtCore.Qt.WindowType.FramelessWindowHint
            | QtCore.Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle(f"Edit regions for: {gesture_name}")
        self.gesture = gesture_name
        self.mappings = mappings
        self.handles = []   # list of ResizableFrame
        self.initUI()

    def initUI(self):
        self.screen_rect = QtWidgets.QApplication.primaryScreen().geometry()
        self.setGeometry(self.screen_rect)

        # Create UI controls: Add, Remove selected (last), Save, Cancel
        btn_add = QtWidgets.QPushButton("Add Region", self)
        btn_add.move(10, 10)
        btn_add.clicked.connect(self.add_region_default)

        btn_remove = QtWidgets.QPushButton("Remove Last", self)
        btn_remove.move(110, 10)
        btn_remove.clicked.connect(self.remove_last)

        btn_save = QtWidgets.QPushButton("Save", self)
        btn_save.move(250, 10)
        btn_save.clicked.connect(self.onSave)

        btn_cancel = QtWidgets.QPushButton("Cancel", self)
        btn_cancel.move(320, 10)
        btn_cancel.clicked.connect(self.close)

        # create handles for existing regions in mappings
        regs = self.mappings.get(self.gesture, [])
        for r in regs:
            self._create_handle_from_region(r)

    def _create_handle_from_region(self, region):
        # region contains fractions and monitor rect in physical pixels
        mon = region.get('monitor')
        if isinstance(mon, (list, tuple)) and len(mon) == 4:
            left, top, right, bottom = mon
            mon_w = right - left
            mon_h = bottom - top
            if mon_w <= 0 or mon_h <= 0:
                # fallback to primary physical monitor
                left, top, right, bottom = 0, 0, SCREEN_W, SCREEN_H
                mon_w = SCREEN_W
                mon_h = SCREEN_H
        else:
            left, top, right, bottom = 0, 0, SCREEN_W, SCREEN_H
            mon_w = SCREEN_W
            mon_h = SCREEN_H

        # compute physical pixel coords for the stored fractions
        phys_x = left + int(round(region.get('x_frac', 0.0) * mon_w))
        phys_y = top  + int(round(region.get('y_frac', 0.0) * mon_h))
        phys_w = max(MIN_WIDTH, int(round(region.get('w_frac', 1.0) * mon_w)))
        phys_h = max(MIN_HEIGHT, int(round(region.get('h_frac', 1.0) * mon_h)))

        # find QScreen that corresponds to this monitor rect (to get its DPR)
        screen = find_qscreen_for_monitor_rect((left, top, right, bottom))
        dpr = screen.devicePixelRatio()

        # convert physical -> logical for Qt positions/sizes
        logical_x = int(round(phys_x / dpr))
        logical_y = int(round(phys_y / dpr))
        logical_w = int(round(phys_w / dpr))
        logical_h = int(round(phys_h / dpr))

        handle = ResizableFrame(self)
        handle.setGeometry(logical_x, logical_y, max(logical_w, MIN_WIDTH), max(logical_h, MIN_HEIGHT))
        handle.show()
        self.handles.append(handle)
        return handle


    def add_region_default(self):
        # create centered small region
        w = SCREEN_W // 4
        h = SCREEN_H // 4
        x = (SCREEN_W - w) // 2
        y = (SCREEN_H - h) // 2
        handle = ResizableFrame(self)
        handle.setGeometry(x, y, w, h)
        handle.show()
        self.handles.append(handle)

    def remove_last(self):
        if not self.handles:
            QtWidgets.QMessageBox.information(self, "Nothing", "No regions to remove.")
            return
        h = self.handles.pop()
        h.setParent(None)
        h.deleteLater()

    def onSave(self):
        """
        Save all current handles as monitor-relative regions for this gesture,
        storing monitor rect (physical pixels) and fractions computed in that monitor.
        """
        regs = []
        for h in self.handles:
            # logical top-left (Qt coordinates)
            top_left_global = h.mapToGlobal(QtCore.QPoint(0, 0))
            gx_logical, gy_logical = top_left_global.x(), top_left_global.y()

            # find the QScreen at that logical point (fallback to primary)
            screen = QtGui.QGuiApplication.screenAt(top_left_global) or QtGui.QGuiApplication.primaryScreen()
            dpr = screen.devicePixelRatio()

            # convert logical -> physical
            phys_gx = int(round(gx_logical * dpr))
            phys_gy = int(round(gy_logical * dpr))

            # handle geometry in logical coords -> convert to physical size
            geom = h.geometry()
            phys_w = int(round(geom.width() * dpr))
            phys_h = int(round(geom.height() * dpr))

            # get monitor rectangle that contains the handle's top-left (physical pixels)
            left, top, right, bottom = get_monitor_rect_from_point(phys_gx, phys_gy)
            mon_w = right - left
            mon_h = bottom - top

            # compute fractions relative to that monitor (physical fractions)
            x_frac = (phys_gx - left) / mon_w if mon_w > 0 else 0.0
            y_frac = (phys_gy - top)  / mon_h if mon_h > 0 else 0.0
            w_frac = phys_w / mon_w if mon_w > 0 else 1.0
            h_frac = phys_h / mon_h if mon_h > 0 else 1.0

            regs.append({
                'x_frac': float(x_frac),
                'y_frac': float(y_frac),
                'w_frac': float(w_frac),
                'h_frac': float(h_frac),
                'monitor': [int(left), int(top), int(right), int(bottom)]
            })

        # Replace mapping for this gesture
        self.mappings[self.gesture] = regs

        save_mappings(self.mappings)
        QtWidgets.QMessageBox.information(self, "Saved", f"Saved {len(regs)} region(s) for '{self.gesture}'")
        self.close()




# ——— ConfigWindow: open RegionSelector per-gesture ———
class ConfigWindow(QtWidgets.QWidget):
    def __init__(self, mappings):
        super().__init__()
        self.mappings = mappings
        self.setWindowTitle("Gesture → Tiling Configurator")
        self.layout = QtWidgets.QVBoxLayout(self)
        self.buttons = {}
        for name in GESTURES:
            row = QtWidgets.QHBoxLayout()
            lbl = QtWidgets.QLabel(name)
            count = len(self.mappings.get(name, []))
            self.buttons[name] = QtWidgets.QPushButton(f"Edit… ({count})")
            self.buttons[name].clicked.connect(lambda _, g=name: self.openSelector(g))
            row.addWidget(lbl)
            row.addWidget(self.buttons[name])
            self.layout.addLayout(row)
        save_btn = QtWidgets.QPushButton("Save & Exit")
        save_btn.clicked.connect(self.onSave)
        self.layout.addWidget(save_btn)

    def openSelector(self, gesture_name):
        # open selector which shows all regions and lets you edit them; existing regions NOT removed automatically
        self.selector = RegionSelector(gesture_name, self.mappings)
        self.selector.showFullScreen()
        # after selector closes, update button label counts (we watch child's close event)
        self.selector.destroyed.connect(lambda *_: self._refresh_counts())

    def _refresh_counts(self):
        for name, btn in self.buttons.items():
            btn.setText(f"Edit… ({len(self.mappings.get(name, []))})")

    def onSave(self):
        # Persist current mappings and exit the configurator.
        save_mappings(self.mappings)
        QtWidgets.QApplication.quit()


def enum_tilable_windows():
    """
    Return a list of candidate top-level HWNDs (Z-order top->bottom) that are
    visible, have non-empty title, and are not tool-windows.
    """
    wins = []
    def _cb(hwnd, lparam):
        try:
            if not win32gui.IsWindowVisible(hwnd):
                return True
            title = win32gui.GetWindowText(hwnd) or ""
            if not title.strip():
                return True
            ex = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
            # skip tool windows (like floating palette windows)
            if ex & win32con.WS_EX_TOOLWINDOW:
                return True
        except Exception:
            return True
        wins.append(hwnd)
        return True

    win32gui.EnumWindows(_cb, None)
    return wins


def tile_window(cfg):
    """
    Accepts cfg as (1) a single region dict, (2) a list-of-region-dicts,
    (3) legacy [x,y,w,h], or (4) a list containing such items.

    If multiple regions exist, attempt to tile multiple top-level windows.
    """
    # normalize cfg -> list of region dicts
    regions = []
    if isinstance(cfg, dict):
        r = region_from_value(cfg)
        if r: regions.append(r)
    elif isinstance(cfg, (list, tuple)):
        # If it's a flat numeric list [x,y,w,h], region_from_value will accept it
        # If it's a list of region-dicts, region_from_value will convert each.
        # If it's [{"x_frac":...}, {...}] those will be converted too.
        # Try to coerce each element; also allow top-level numeric list
        # handled by region_from_value below.
        # First check top-level flat numeric list:
        if len(cfg) >= 4 and all(isinstance(x, numbers.Number) for x in cfg[:4]):
            r = region_from_value(cfg)
            if r: regions.append(r)
        else:
            for elem in cfg:
                r = region_from_value(elem)
                if r:
                    regions.append(r)
    else:
        # try a last-ditch coercion
        r = region_from_value(cfg)
        if r:
            regions.append(r)

    if not regions:
        print(f"[win-tiler] ⚠️  Invalid mapping format for gesture: {cfg!r}")
        return

    # get candidate windows
    candidates = enum_tilable_windows()
    if not candidates:
        print("[win-tiler] ⚠️  No candidate top-level windows found to tile.")
        return

    focused = win32gui.GetForegroundWindow()
    # place focused window first if present in candidates
    if focused in candidates:
        candidates.remove(focused)
        candidates.insert(0, focused)

    # iterate over regions and candidate windows
    n_to_tile = min(len(regions), len(candidates))
    for i in range(n_to_tile):
        region = regions[i]
        hwnd = candidates[i]
        x_frac = region.get('x_frac', 0)
        y_frac = region.get('y_frac', 0)
        w_frac = region.get('w_frac', 1)
        h_frac = region.get('h_frac', 1)

        x = int(SCREEN_W * x_frac)
        y = int(SCREEN_H * y_frac)
        w = int(SCREEN_W * w_frac)
        h = int(SCREEN_H * h_frac)

        try:
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            win32gui.MoveWindow(hwnd, x, y, w, h, True)
            print(f"[win-tiler] ✅  Tiled hwnd={hwnd} → region #{i+1}: x={x_frac:.2f}, y={y_frac:.2f}, w={w_frac:.2f}, h={h_frac:.2f}")
        except Exception as e:
            print(f"[win-tiler] ⚠️  Failed to tile hwnd={hwnd}: {e}")

    if len(regions) > n_to_tile:
        print(f"[win-tiler]   {len(regions)-n_to_tile} region(s) not used (not enough candidate windows).")
    if len(candidates) > n_to_tile:
        print(f"[win-tiler]   {len(candidates)-n_to_tile} window(s) left untiled.")

# ——— record_and_action and hotkey (unchanged) ———
def record_and_action():
    print(f"[win-tiler] 🎬  Recording gesture for {GESTURE_TIMEOUT:.1f}s…")
    recorder.clear()
    time.sleep(GESTURE_TIMEOUT)
    pts = recorder.fetch()

    for name, fn in GESTURES.items():
        if fn(pts):
            print(f"[win-tiler] 🎯  Detected gesture: '{name}'")
            cfg = mappings.get(name)
            if cfg is None:
                print(f"[win-tiler] ⚠️  No mapping for '{name}'")
            else:
                tile_window(cfg)
            break
    else:
        print("[win-tiler] ❌  No matching gesture detected.")

def on_hotkey():
    print("[win-tiler] ⌨️   Hotkey Ctrl+Alt+G pressed.")
    threading.Thread(target=record_and_action, daemon=True).start()

# ——— Main ———
if __name__ == "__main__":
    mappings = load_mappings()

    recorder = Recorder()
    hotk = keyboard.GlobalHotKeys({'<ctrl>+<alt>+g': on_hotkey})
    hotk.start()

    app = QtWidgets.QApplication([])
    win = ConfigWindow(mappings)
    win.show()
    app.exec()

    print("Configuration saved. Now press Ctrl+Alt+G + draw gesture to tile windows.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
