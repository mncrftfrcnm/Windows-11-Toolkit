
import sys, os, json, math, ctypes, atexit, platform, time
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
import ctypes.wintypes  # needed for native event filter / MSG
from typing import Tuple  # if not already imported

def _split_rgb_opacity(style_dict: dict) -> Tuple[int, int, int, int]:
    """
    Return r,g,b,a from a style dict that may store:
      - color=[r,g,b] and opacity=a   (new format), or
      - color=[r,g,b,a]               (legacy format)
    Falls back to 0,0,0,160 if missing.
    """
    col = style_dict.get("color", [0, 0, 0])
    if isinstance(col, list):
        if len(col) >= 4:
            r, g, b, a = col[0], col[1], col[2], int(col[3])
            a = int(style_dict.get("opacity", a))  # explicit opacity wins
            return int(r), int(g), int(b), int(a)
        elif len(col) >= 3:
            r, g, b = col[0], col[1], col[2]
            a = int(style_dict.get("opacity", 160))
            return int(r), int(g), int(b), int(a)
    return 0, 0, 0, 160

def _migrate_styles_inplace(settings: dict) -> None:
    """
    Normalize all styles in-place:
      - Convert color=[r,g,b,a] to color=[r,g,b] + opacity=a
      - Ensure 'blur_mode' exists (mapped from legacy 'blur' if present)
    """
    styles = settings.get("styles", {})
    for name, st in styles.items():
        if not isinstance(st, dict):
            continue
        col = st.get("color")
        if isinstance(col, list) and len(col) >= 4:
            st.setdefault("opacity", int(col[3]))
            st["color"] = col[:3]
        if "blur_mode" not in st and "blur" in st:
            bm = st.get("blur", "none")
            st["blur_mode"] = bm if bm in ("blur", "acrylic", "transparent", "none") else "none"

if platform.system() != "Windows":
    print("This script runs on Windows only.")
    sys.exit(1)

import ctypes.wintypes

# ------------------ Win32: taskbar, blur/acrylic, windows, hotkeys -----------------
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
dwmapi = ctypes.windll.dwmapi if hasattr(ctypes.windll, "dwmapi") else None
shell32 = ctypes.windll.shell32
ole32 = ctypes.windll.ole32

SW_HIDE = 0
SW_SHOW = 5
SW_RESTORE = 9

MOD_ALT     = 0x0001
MOD_CONTROL = 0x0002
WM_HOTKEY   = 0x0312
HOTKEY_ID_TOGGLE_TASKBAR = 1  # Ctrl+Alt+T
HOTKEY_ID_OPEN_SETTINGS  = 2  # Ctrl+,

GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

def _find_window(cls: str) -> Optional[int]:
    hwnd = user32.FindWindowW(cls, None)
    return hwnd or None

def hide_taskbar():
    for cls in ("Shell_TrayWnd", "Shell_SecondaryTrayWnd"):
        hwnd = _find_window(cls)
        if hwnd:
            user32.ShowWindow(hwnd, SW_HIDE)

def show_taskbar():
    for cls in ("Shell_TrayWnd", "Shell_SecondaryTrayWnd"):
        hwnd = _find_window(cls)
        if hwnd:
            user32.ShowWindow(hwnd, SW_SHOW)

# Accent policy (blur/acrylic) via SetWindowCompositionAttribute
class ACCENT_POLICY(ctypes.Structure):
    _fields_ = [("AccentState", ctypes.c_int),
                ("AccentFlags", ctypes.c_int),
                ("GradientColor", ctypes.c_int),
                ("AnimationId", ctypes.c_int)]

class WINDOWCOMPOSITIONATTRIBDATA(ctypes.Structure):
    _fields_ = [("Attribute", ctypes.c_int),
                ("Data", ctypes.c_void_p),
                ("SizeOfData", ctypes.c_size_t)]

WCA_ACCENT_POLICY = 19
ACCENT_DISABLED = 0
ACCENT_ENABLE_GRADIENT = 1
ACCENT_ENABLE_TRANSPARENTGRADIENT = 2
ACCENT_ENABLE_BLURBEHIND = 3
ACCENT_ENABLE_ACRYLICBLURBEHIND = 4

def _rgba_to_abgr_dword(r, g, b, a):  # 0xAABBGGRR
    return (a << 24) | (b << 16) | (g << 8) | r

def set_window_accent(hwnd: int, mode: str, r: int, g: int, b: int, a: int, flags: int = 0x20):
    """mode: 'none' | 'blur' | 'acrylic' | 'liquid' | 'glass' | 'xp_gloss' | 'neon' | 'transparent'"""
    if not hwnd:
        return
    accent = ACCENT_POLICY()
    if mode in ("blur", "glass"):
        accent.AccentState = ACCENT_ENABLE_BLURBEHIND
    elif mode in ("acrylic", "liquid", "neon"):
        accent.AccentState = ACCENT_ENABLE_ACRYLICBLURBEHIND
    elif mode == "transparent":
        accent.AccentState = ACCENT_ENABLE_TRANSPARENTGRADIENT
    else:
        accent.AccentState = ACCENT_DISABLED
    accent.AccentFlags = flags  # 0x20 = left border; tweak adds better edge
    accent.GradientColor = _rgba_to_abgr_dword(r, g, b, a)
    data = WINDOWCOMPOSITIONATTRIBDATA()
    data.Attribute = WCA_ACCENT_POLICY
    data.SizeOfData = ctypes.sizeof(accent)
    data.Data = ctypes.cast(ctypes.pointer(accent), ctypes.c_void_p)
    try:
        ctypes.windll.user32.SetWindowCompositionAttribute(int(hwnd), ctypes.byref(data))
    except Exception:
        pass

# Best-effort Mica (Win11 22H2+), silently no-op otherwise.
def set_window_mica(hwnd: int, enabled: bool):
    if not (hwnd and dwmapi):
        return
    DWMWA_SYSTEMBACKDROP_TYPE = 38
    value = ctypes.c_int(2 if enabled else 0)  # 2=Mica
    try:
        dwmapi.DwmSetWindowAttribute(ctypes.c_void_p(hwnd), ctypes.c_int(DWMWA_SYSTEMBACKDROP_TYPE),
                                     ctypes.byref(value), ctypes.sizeof(value))
    except Exception:
        pass

def register_hotkeys(hwnd: int):
    # Ctrl+Alt+T: toggle taskbar visibility
    user32.RegisterHotKey(hwnd, HOTKEY_ID_TOGGLE_TASKBAR, MOD_CONTROL | MOD_ALT, ord('T'))
    # Ctrl+, : open settings
    user32.RegisterHotKey(hwnd, HOTKEY_ID_OPEN_SETTINGS, MOD_CONTROL, 0xBC)  # VK_OEM_COMMA

def unregister_hotkeys(hwnd: int):
    user32.UnregisterHotKey(hwnd, HOTKEY_ID_TOGGLE_TASKBAR)
    user32.UnregisterHotKey(hwnd, HOTKEY_ID_OPEN_SETTINGS)

# Enumerate application windows (rough heuristic similar to taskbar behavior)
def _get_window_text(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(hwnd, buf, 512)
    return buf.value

def _is_app_window(hwnd: int) -> bool:
    if not user32.IsWindowVisible(hwnd):
        return False
    if user32.GetWindow(hwnd, 4):  # GW_OWNER = 4
        return False
    ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    if ex & WS_EX_TOOLWINDOW:
        return False
    title = _get_window_text(hwnd)
    return bool(title.strip())

def _get_process_path_from_pid(pid: int) -> Optional[str]:
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return None
    try:
        size = ctypes.wintypes.DWORD(260)
        buf = ctypes.create_unicode_buffer(260)
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return buf.value
    finally:
        kernel32.CloseHandle(h)
    return None

EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

def enumerate_app_windows() -> List[Tuple[int, int, str, str]]:
    """Return list of (hwnd, pid, exe_path, title) for visible app-like windows."""
    windows = []
    def _cb(hwnd, lParam):
        if _is_app_window(hwnd):
            pid = ctypes.wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            path = _get_process_path_from_pid(pid.value) or ""
            windows.append((hwnd, pid.value, path, _get_window_text(hwnd)))
        return True
    user32.EnumWindows(EnumWindowsProc(_cb), 0)
    return windows

def focus_window(hwnd: int):
    try:
        user32.ShowWindow(hwnd, SW_RESTORE)
        user32.SetForegroundWindow(hwnd)
    except Exception:
        pass

# Resolve .lnk (ShellLink) to target exe if possible, otherwise return original
CLSID_ShellLink = ctypes.c_char * 16
IID_IShellLinkW = ctypes.c_char * 16
IID_IPersistFile = ctypes.c_char * 16

def _guid_from_text(txt: str):
    from uuid import UUID
    u = UUID(txt)
    b = (ctypes.c_ubyte * 16).from_buffer_copy(u.bytes_le)
    return b

CLSID_ShellLink_guid = _guid_from_text("{00021401-0000-0000-C000-000000000046}")
IID_IShellLinkW_guid = _guid_from_text("{000214F9-0000-0000-C000-000000000046}")
IID_IPersistFile_guid = _guid_from_text("{0000010b-0000-0000-C000-000000000046}")

class IShellLinkW(ctypes.Structure):
    pass
class IPersistFile(ctypes.Structure):
    pass

LPVOID = ctypes.c_void_p
LPWSTR = ctypes.c_wchar_p
WCHAR  = ctypes.c_wchar
WORD   = ctypes.c_ushort

IShellLinkW._fields_ = []
IPersistFile._fields_ = []

def resolve_lnk(path: str) -> str:
    if not path.lower().endswith(".lnk"):
        return path
    try:
        ole32.CoInitialize(None)
        psl = LPVOID()
        hr = ctypes.windll.ole32.CoCreateInstance(CLSID_ShellLink_guid, None, 1, IID_IShellLinkW_guid, ctypes.byref(psl))
        if hr != 0:
            return path
        sl = ctypes.cast(psl, ctypes.c_void_p)

        get_iface = ctypes.WINFUNCTYPE(ctypes.c_long, LPVOID, ctypes.c_char_p, ctypes.POINTER(LPVOID))(ctypes.cast(ctypes.cast(sl, ctypes.POINTER(ctypes.c_void_p))[0], ctypes.c_void_p).value)
        # Query IPersistFile
        ipf = LPVOID()
        ctypes.oledll.ole32.IIDFromString("0000010b-0000-0000-C000-000000000046", ctypes.byref(ctypes.c_byte * 16)())  # keep linker happy

        # Safer: use QueryInterface vtable 0, but here we’ll just use shell32 helpers:
        pf = ctypes.POINTER(ctypes.c_void_p)()
        # Using COM properly is lengthy; instead, call shell32 helpers: IShellLinkW via ctypes is enough for GetPath through vtable index.
        # vtable[20] = GetPath (commonly). We'll attempt a pragmatic approach:
        class SLVT(ctypes.Structure):
            _fields_ = [("vtable", ctypes.POINTER(ctypes.c_void_p))]
        slvt = SLVT.from_address(sl.value)
        vtbl = slvt.vtable
        GetPath = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_int)(vtbl[20])
        Load = None
        # Use IPersistFile via QueryInterface (vtbl[0] = QueryInterface)
        QueryInterface = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))(vtbl[0])
        pfv = ctypes.c_void_p()
        hr = QueryInterface(sl, IID_IPersistFile_guid, ctypes.byref(pfv))
        if hr == 0 and pfv:
            # IPersistFile vtable: [0]=QueryInterface,[1]=AddRef,[2]=Release,[3]=GetClassID,[4]=IsDirty,[5]=Load,...
            class PFVT(ctypes.Structure):
                _fields_ = [("vtable", ctypes.POINTER(ctypes.c_void_p))]
            pfi = PFVT.from_address(pfv.value)
            Load = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int)(pfi.vtable[5])
            if Load:
                Load(pfv, path, 0)
                buf = ctypes.create_unicode_buffer(520)
                GetPath(sl, buf, 520, None, 0)
                target = buf.value or path
                return target
    except Exception:
        return path
    finally:
        try: ole32.CoUninitialize()
        except Exception: pass
    return path

def app_key_from_path(p: str) -> str:
    try:
        if p.lower().endswith(".lnk"):
            p = resolve_lnk(p)
        base = os.path.basename(p)
        return os.path.splitext(base)[0].lower()
    except Exception:
        return os.path.splitext(os.path.basename(p))[0].lower()

def exe_key_from_fullpath(p: str) -> str:
    if not p: return ""
    base = os.path.basename(p)
    return os.path.splitext(base)[0].lower()

def windows_by_exe_key() -> Dict[str, List[int]]:
    """Map exe base name -> list of hwnds."""
    m: Dict[str, List[int]] = {}
    for hwnd, pid, path, title in enumerate_app_windows():
        k = exe_key_from_fullpath(path)
        if not k: continue
        m.setdefault(k, []).append(hwnd)
    return m

# ------------------ Qt UI ----------------------------------------------------------
from PySide6 import QtCore, QtGui, QtWidgets

APP_DIR = Path(os.getenv("APPDATA", str(Path.home()))) / "CustomTaskbar"
APP_DIR.mkdir(parents=True, exist_ok=True)
SETTINGS_FILE = APP_DIR / "settings.json"
WIDGETS_DIR = APP_DIR / "widgets"
PINNED_DIR = Path(os.path.expandvars(r"%APPDATA%\Microsoft\Internet Explorer\Quick Launch\User Pinned\TaskBar"))
WIDGETS_DIR.mkdir(parents=True, exist_ok=True)

def load_json(path: Path, default: dict) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default

def save_json(path: Path, data: dict):
    try:
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        pass

# ------------------ Styles ---------------------------------------------------------
DEFAULT_STYLES: Dict[str, Dict[str, Any]] = {
    "macOS Dock": {
        "position": "bottom", "alignment": "center",
        "height": 78, "width": 78, "radius": 22,
        "effect": "liquid", "blur_mode": "acrylic", "opacity": 150,
        "color": [20,20,20], "bg_image": None,
        "auto_hide": False, "magnify": True, "magnify_factor": 1.75, "magnify_sigma": 70.0,
        "icon_size": 40, "spacing": 12,
        "outline": False, "glow": True, "shelf_highlight": True,
        "anim_ms": 180, "anim_ease": "OutCubic"
    },
    "Windows 7": {
        "position": "bottom", "alignment": "left",
        "height": 48, "width": 48, "radius": 10,
        "effect": "blur", "blur_mode": "blur", "opacity": 170,
        "color": [32,120,200], "bg_image": None,
        "auto_hide": False, "magnify": False, "magnify_factor": 1.2, "magnify_sigma": 60.0,
        "icon_size": 28, "spacing": 8,
        "outline": True, "glow": True, "shelf_highlight": False,
        "anim_ms": 160, "anim_ease": "OutCubic"
    },
    "Windows XP": {
        "position": "bottom", "alignment": "left",
        "height": 40, "width": 40, "radius": 0,
        "effect": "xp_gloss", "blur_mode": "none", "opacity": 235,
        "color": [30,90,200], "bg_image": None,
        "auto_hide": False, "magnify": False, "magnify_factor": 1.15, "magnify_sigma": 60.0,
        "icon_size": 24, "spacing": 6,
        "outline": True, "glow": False, "shelf_highlight": False,
        "anim_ms": 140, "anim_ease": "OutCubic"
    },
    "Fluent (Mica)": {
        "position": "bottom", "alignment": "center",
        "height": 56, "width": 56, "radius": 16,
        "effect": "mica", "blur_mode": "none", "opacity": 150,
        "color": [32,32,32], "bg_image": None,
        "auto_hide": False, "magnify": False, "magnify_factor": 1.3, "magnify_sigma": 60.0,
        "icon_size": 30, "spacing": 10,
        "outline": False, "glow": True, "shelf_highlight": False,
        "anim_ms": 160, "anim_ease": "OutCubic"
    },
    "Transparent": {
        "position": "bottom", "alignment": "center",
        "height": 52, "width": 52, "radius": 18,
        "effect": "transparent", "blur_mode": "transparent", "opacity": 0,
        "color": [0,0,0], "bg_image": None,
        "auto_hide": True, "magnify": True, "magnify_factor": 1.6, "magnify_sigma": 60.0,
        "icon_size": 34, "spacing": 10,
        "outline": False, "glow": True, "shelf_highlight": False,
        "anim_ms": 180, "anim_ease": "OutBack"
    },
    "Obsidian": {
        "position": "bottom", "alignment": "center",
        "height": 60, "width": 60, "radius": 20,
        "effect": "neon", "blur_mode": "acrylic", "opacity": 180,
        "color": [10,10,12], "bg_image": None,
        "auto_hide": False, "magnify": True, "magnify_factor": 1.85, "magnify_sigma": 65.0,
        "icon_size": 36, "spacing": 12,
        "outline": False, "glow": True, "shelf_highlight": False,
        "anim_ms": 170, "anim_ease": "OutCubic"
    },
    "Frosted Blue": {
        "position": "top", "alignment": "center",
        "height": 46, "width": 46, "radius": 14,
        "effect": "glass", "blur_mode": "blur", "opacity": 135,
        "color": [30,70,160], "bg_image": None,
        "auto_hide": True, "magnify": False, "magnify_factor": 1.2, "magnify_sigma": 60.0,
        "icon_size": 24, "spacing": 8,
        "outline": False, "glow": True, "shelf_highlight": False,
        "anim_ms": 160, "anim_ease": "OutCubic"
    },
    "Candy Glass": {
        "position": "bottom", "alignment": "center",
        "height": 64, "width": 64, "radius": 22,
        "effect": "liquid", "blur_mode": "acrylic", "opacity": 160,
        "color": [255, 80, 150], "bg_image": None,
        "auto_hide": False, "magnify": True, "magnify_factor": 1.7, "magnify_sigma": 70.0,
        "icon_size": 38, "spacing": 12,
        "outline": False, "glow": True, "shelf_highlight": False,
        "anim_ms": 180, "anim_ease": "OutBack"
    },
}

DEFAULT_SETTINGS = {
    "current_style": "macOS Dock",
    "styles": DEFAULT_STYLES,
    "apps": [],                  # import pinned or add manually
    "widgets": ["ClockWidget"],  # optional: CPUWidget
}

# ------------------ Widgets --------------------------------------------------------
class ClockWidget(QtWidgets.QLabel):
    def __init__(self):
        super().__init__()
        self.setAlignment(QtCore.Qt.AlignCenter)
        t = QtCore.QTimer(self); t.timeout.connect(self._tick); t.start(1000)
        self._timer = t; self._tick()
    def _tick(self):
        self.setText(time.strftime("%H:%M\n%d %b"))

class CPUWidget(QtWidgets.QLabel):
    def __init__(self):
        super().__init__()
        try:
            import psutil
            self._psutil = psutil
        except Exception:
            self._psutil = None
        self.setAlignment(QtCore.Qt.AlignCenter)
        t = QtCore.QTimer(self); t.timeout.connect(self._tick); t.start(1000); self._timer=t; self._tick()
    def _tick(self):
        if self._psutil: self.setText(f"CPU\n{int(self._psutil.cpu_percent())}%")
        else: self.setText("CPU\n—")

BUILTIN_WIDGETS = {"ClockWidget": ClockWidget, "CPUWidget": CPUWidget}

def load_user_widgets() -> Dict[str, type]:
    widgets = {}
    sys.path.insert(0, str(WIDGETS_DIR))
    for py in WIDGETS_DIR.glob("*.py"):
        try:
            mod = __import__(py.stem)
            for name in dir(mod):
                obj = getattr(mod, name)
                if isinstance(obj, type) and issubclass(obj, QtWidgets.QWidget) and obj is not QtWidgets.QWidget:
                    widgets[name] = obj
        except Exception:
            continue
    return widgets

# ------------------ Dock Button with window indicators -----------------------------
class BadgeLabel(QtWidgets.QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("QLabel { background: rgba(0,0,0,190); color: white; border-radius: 9px; padding: 0 6px; font: 11px 'Segoe UI'; }")
        self.setVisible(False)

class DockButton(QtWidgets.QToolButton):
    def __init__(self, label: str, icon: QtGui.QIcon, exec_path: str, base_size: int):
        super().__init__()
        self.exec_path = exec_path
        self.app_key = app_key_from_path(exec_path)
        self.base = base_size
        self.cur = base_size
        self.setToolButtonStyle(QtCore.Qt.ToolButtonIconOnly)
        self.setIcon(icon if not icon.isNull() else QtGui.QIcon())
        self.setIconSize(QtCore.QSize(self.base, self.base))
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setToolTip(label)
        self.setAutoRaise(True)
        self.badge = BadgeLabel(self)
        self.badge.raise_()

        self._hwnds: List[int] = []
        self._cycle_index = 0

        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._context_menu)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        # position badge bottom-right
        s = self.iconSize()
        bx = self.width() - 18
        by = self.height() - 18
        self.badge.move(bx, by)

    def set_scaled(self, size: int):
        if size != self.cur:
            self.cur = size
            self.setIconSize(QtCore.QSize(size, size))

    def update_windows(self, hwnds: List[int]):
        self._hwnds = hwnds
        count = len(hwnds)
        if count > 0:
            self.badge.setText(str(count))
            self.badge.adjustSize()
            self.badge.setVisible(True)
        else:
            self.badge.setVisible(False)

    def mouseReleaseEvent(self, e: QtGui.QMouseEvent):
        if e.button() == QtCore.Qt.LeftButton:
            # Launch or focus/cycle
            if self._hwnds:
                # Cycle through windows
                self._cycle_index = (self._cycle_index + 1) % len(self._hwnds)
                focus_window(self._hwnds[self._cycle_index])
            else:
                try: os.startfile(self.exec_path)
                except Exception as ex:
                    QtWidgets.QMessageBox.warning(self, "Launch failed", str(ex))
        elif e.button() == QtCore.Qt.MiddleButton:
            # Middle click: launch new instance if possible
            try: os.startfile(self.exec_path)
            except Exception: pass
        super().mouseReleaseEvent(e)

    def _context_menu(self, pos):
        m = QtWidgets.QMenu(self)
        if self._hwnds:
            sub = m.addMenu("Windows")
            for hwnd in self._hwnds:
                title = _get_window_text(hwnd) or "(untitled)"
                act = sub.addAction(title[:60])
                act.triggered.connect(lambda chk=False, h=hwnd: focus_window(h))
        else:
            m.addAction("No windows")
        m.addSeparator()
        m.addAction("Open new instance", lambda: os.startfile(self.exec_path))
        m.exec(self.mapToGlobal(pos))

# ------------------ Settings Dialog ------------------------------------------------
class ColorButton(QtWidgets.QPushButton):
    colorChanged = QtCore.Signal(QtGui.QColor)
    def __init__(self, c: QtGui.QColor):
        super().__init__("Pick…"); self._color=c; self._apply()
        self.clicked.connect(self._pick)
    def _pick(self):
        dlg = QtWidgets.QColorDialog(self._color, self); dlg.setOption(QtWidgets.QColorDialog.ShowAlphaChannel, True)
        if dlg.exec():
            self._color = dlg.selectedColor(); self._apply(); self.colorChanged.emit(self._color)
    def _apply(self):
        c = self._color
        self.setStyleSheet(f"background-color: rgba({c.red()},{c.green()},{c.blue()},{c.alpha()}); border:1px solid #0002;")

class SettingsDialog(QtWidgets.QDialog):
    def __init__(self, win: "TaskbarWindow"):
        super().__init__(win)
        self.setWindowTitle("Customize Taskbar")
        self.setModal(False)
        self.setMinimumWidth(560)
        tabs = QtWidgets.QTabWidget(self); v = QtWidgets.QVBoxLayout(self); v.addWidget(tabs)

        self.win = win
        s = win.current_style

        # ALWAYS get a consistent r,g,b,a (works with old or new settings)
        r, g, b, a = _split_rgb_opacity(s)

        # Appearance tab widgets...
        self.effect_combo = QtWidgets.QComboBox()
        self.effect_combo.addItems(["none","transparent","blur","acrylic","liquid","mica","glass","xp_gloss","neon"])
        self.effect_combo.setCurrentText(s.get("effect","none"))

        # Build the color with alpha from _split_rgb_opacity
        base_color = QtGui.QColor(r, g, b, a)
        self.color_btn = ColorButton(base_color)
        # Appearance
        ap = QtWidgets.QWidget(); tabs.addTab(ap, "Appearance")
        f1 = QtWidgets.QFormLayout(ap)
        self.style_combo = QtWidgets.QComboBox(); self.style_combo.addItems(sorted(win.styles.keys()))

        self.bg_btn = QtWidgets.QPushButton("Set Image…"); self.bg_clear = QtWidgets.QPushButton("Clear")
        f1.addRow("Style", self.style_combo)
        f1.addRow("Effect", self.effect_combo)
        f1.addRow("Color/Opacity", self.color_btn)
        row = QtWidgets.QHBoxLayout(); row.addWidget(self.bg_btn); row.addWidget(self.bg_clear); f1.addRow("Background", row)

        # Layout
        ly = QtWidgets.QWidget(); tabs.addTab(ly, "Layout")
        f2 = QtWidgets.QFormLayout(ly)
        self.pos_combo = QtWidgets.QComboBox(); self.pos_combo.addItems(["top","bottom","left","right"]); self.pos_combo.setCurrentText(s["position"])
        self.align_combo = QtWidgets.QComboBox(); self.align_combo.addItems(["left","center","right"]); self.align_combo.setCurrentText(s["alignment"])
        self.thick = QtWidgets.QSlider(QtCore.Qt.Horizontal); self.thick.setRange(24,160); self.thick.setValue(s["height"])
        self.icon = QtWidgets.QSlider(QtCore.Qt.Horizontal); self.icon.setRange(16,128); self.icon.setValue(s["icon_size"])
        self.radius = QtWidgets.QSlider(QtCore.Qt.Horizontal); self.radius.setRange(0,36); self.radius.setValue(s["radius"])
        self.spacing = QtWidgets.QSlider(QtCore.Qt.Horizontal); self.spacing.setRange(2,26); self.spacing.setValue(s["spacing"])
        f2.addRow("Position", self.pos_combo)
        f2.addRow("Alignment", self.align_combo)
        f2.addRow("Thickness", self.thick)
        f2.addRow("Icon size", self.icon)
        f2.addRow("Corner radius", self.radius)
        f2.addRow("Spacing", self.spacing)

        # Behavior
        be = QtWidgets.QWidget(); tabs.addTab(be, "Behavior")
        f3 = QtWidgets.QFormLayout(be)
        self.autohide = QtWidgets.QCheckBox(); self.autohide.setChecked(s.get("auto_hide",False))
        self.magnify = QtWidgets.QCheckBox(); self.magnify.setChecked(s.get("magnify",True))
        self.mag_power = QtWidgets.QSlider(QtCore.Qt.Horizontal); self.mag_power.setRange(50,300); self.mag_power.setValue(int(s.get("magnify_factor",1.6)*100))
        self.mag_sigma = QtWidgets.QSlider(QtCore.Qt.Horizontal); self.mag_sigma.setRange(30,200); self.mag_sigma.setValue(int(s.get("magnify_sigma",70)))
        self.anim_ms = QtWidgets.QSlider(QtCore.Qt.Horizontal); self.anim_ms.setRange(60,500); self.anim_ms.setValue(s.get("anim_ms",160))
        self.anim_ease = QtWidgets.QComboBox(); self.anim_ease.addItems(["Linear","OutCubic","OutBack","OutBounce"]); self.anim_ease.setCurrentText(s.get("anim_ease","OutCubic"))
        f3.addRow("Auto-hide", self.autohide)
        f3.addRow("Magnify on hover", self.magnify)
        f3.addRow("Magnify power (%)", self.mag_power)
        f3.addRow("Magnify radius (px)", self.mag_sigma)
        f3.addRow("Animation speed (ms)", self.anim_ms)
        f3.addRow("Animation easing", self.anim_ease)

        # Apps & Widgets
        aw = QtWidgets.QWidget(); tabs.addTab(aw, "Apps & Widgets")
        l5 = QtWidgets.QVBoxLayout(aw)
        add_app = QtWidgets.QPushButton("Add App…")
        rm_app  = QtWidgets.QPushButton("Remove App…")
        imp_pin = QtWidgets.QPushButton("Import Windows pinned apps")
        add_clock = QtWidgets.QPushButton("Add Clock")
        add_cpu   = QtWidgets.QPushButton("Add CPU")
        add_user  = QtWidgets.QPushButton("Add user widget…")
        rm_wid    = QtWidgets.QPushButton("Remove widget…")
        grid = QtWidgets.QGridLayout()
        grid.addWidget(add_app,0,0); grid.addWidget(rm_app,0,1); grid.addWidget(imp_pin,0,2)
        grid.addWidget(add_clock,1,0); grid.addWidget(add_cpu,1,1); grid.addWidget(add_user,1,2); grid.addWidget(rm_wid,1,3)
        l5.addLayout(grid)

        # Safety
        sf = QtWidgets.QWidget(); tabs.addTab(sf, "Safety")
        l6 = QtWidgets.QVBoxLayout(sf)
        restore_btn = QtWidgets.QPushButton("Restore Windows Taskbar (Show)")
        hide_btn    = QtWidgets.QPushButton("Hide Windows Taskbar")
        info = QtWidgets.QLabel("Hotkeys: Ctrl+Alt+T toggle stock taskbar, Ctrl+, open this dialog.")
        info.setWordWrap(True)
        l6.addWidget(restore_btn); l6.addWidget(hide_btn); l6.addWidget(info)

        # buttons
        btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Save | QtWidgets.QDialogButtonBox.Close)
        v.addWidget(btns)

        # Wire
        self.style_combo.currentTextChanged.connect(lambda n: self.win.apply_style(n))
        self.effect_combo.currentTextChanged.connect(self._apply_effect)
        self.color_btn.colorChanged.connect(self._apply_color)
        self.bg_btn.clicked.connect(self._set_bg)
        self.bg_clear.clicked.connect(self._clear_bg)
        self.pos_combo.currentTextChanged.connect(self._set_pos)
        self.align_combo.currentTextChanged.connect(self._set_align)
        self.thick.valueChanged.connect(self._set_thickness)
        self.icon.valueChanged.connect(self._set_icon)
        self.radius.valueChanged.connect(self._set_radius)
        self.spacing.valueChanged.connect(self._set_spacing)
        self.autohide.toggled.connect(self._toggle_autohide)
        self.magnify.toggled.connect(self._toggle_magnify)
        self.mag_power.valueChanged.connect(self._set_mag_power)
        self.mag_sigma.valueChanged.connect(self._set_mag_sigma)
        self.anim_ms.valueChanged.connect(self._set_anim_ms)
        self.anim_ease.currentTextChanged.connect(self._set_anim_ease)

        add_app.clicked.connect(self.win._add_app)
        rm_app.clicked.connect(self.win._remove_app)
        imp_pin.clicked.connect(self.win.import_pinned_apps)
        add_clock.clicked.connect(lambda: self.win._add_widget("ClockWidget"))
        add_cpu.clicked.connect(lambda: self.win._add_widget("CPUWidget"))
        add_user.clicked.connect(self.win._add_user_widget)
        rm_wid.clicked.connect(self.win._remove_widget)
        restore_btn.clicked.connect(self.win._restore_taskbar)
        hide_btn.clicked.connect(hide_taskbar)

        btns.accepted.connect(self._save)
        btns.rejected.connect(self.close)

    # Apply handlers
    def _apply_effect(self, e):
        self.win.current_style["effect"] = e
        # Map effect to blur mode for accent API
        self.win.current_style["blur_mode"] = "acrylic" if e in ("acrylic","liquid","neon") else ("blur" if e in ("blur","glass") else ("transparent" if e=="transparent" else "none"))
        self.win.styles[self.win.current_style_name] = dict(self.win.current_style)
        self.win.apply_style(self.win.current_style_name)
    def _apply_color(self, c: QtGui.QColor):
        self.win.current_style["color"] = [c.red(), c.green(), c.blue()]
        self.win.current_style["opacity"] = c.alpha()
        self.win.styles[self.win.current_style_name] = dict(self.win.current_style)
        self.win._apply_effects(); self.win.update(); self.win._save_settings()
    def _set_bg(self):
        fn,_=QtWidgets.QFileDialog.getOpenFileName(self,"Choose image",str(Path.home()),"Images (*.png *.jpg *.jpeg *.bmp)")
        if fn:
            self.win.current_style["bg_image"]=fn; self.win.styles[self.win.current_style_name]=dict(self.win.current_style)
            self.win.apply_style(self.win.current_style_name); self.win._save_settings()
    def _clear_bg(self):
        self.win.current_style["bg_image"]=None; self.win.styles[self.win.current_style_name]=dict(self.win.current_style)
        self.win.apply_style(self.win.current_style_name); self.win._save_settings()
    def _set_pos(self, p): self.win._set_position(p)
    def _set_align(self, a): self.win._set_alignment(a)
    def _set_thickness(self, v): self.win._set_thickness(v)
    def _set_icon(self, v): self.win._set_icon_size(v)
    def _set_radius(self, v): self.win._set_radius(v)
    def _set_spacing(self, v): self.win._set_spacing(v)
    def _toggle_autohide(self, b): self.win._toggle_autohide(b)
    def _toggle_magnify(self, b): self.win._toggle_magnify(b)
    def _set_mag_power(self, v): self.win._set_magnify_power(v/100.0)
    def _set_mag_sigma(self, v): self.win._set_magnify_sigma(float(v))
    def _set_anim_ms(self, v): self.win._set_anim_ms(int(v))
    def _set_anim_ease(self, t): self.win._set_anim_ease(t)
    def _save(self): self.win._save_settings(); self.close()

# ------------------ Main Window ----------------------------------------------------
def icon_for_path(path: str) -> QtGui.QIcon:
    info = QtCore.QFileInfo(path)
    return QtWidgets.QFileIconProvider().icon(info)

def easing_from_name(name: str) -> QtCore.QEasingCurve:
    mapping = {
        "Linear": QtCore.QEasingCurve.Linear,
        "OutCubic": QtCore.QEasingCurve.OutCubic,
        "OutBack": QtCore.QEasingCurve.OutBack,
        "OutBounce": QtCore.QEasingCurve.OutBounce,
    }
    return QtCore.QEasingCurve(mapping.get(name, QtCore.QEasingCurve.OutCubic))

class TaskbarWindow(QtWidgets.QWidget, QtCore.QAbstractNativeEventFilter):
    def __init__(self, settings: dict):
        super().__init__(None, QtCore.Qt.Tool)
        self.setWindowFlag(QtCore.Qt.FramelessWindowHint, True)
        self.setWindowFlag(QtCore.Qt.WindowStaysOnTopHint, True)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
        self.setObjectName("CustomTaskbar")
        self.setWindowTitle("Custom Taskbar")

        self.settings = settings
        self.styles = settings.get("styles", DEFAULT_STYLES)
        self.current_style_name = settings.get("current_style", "macOS Dock")
        self.current_style = dict(self.styles.get(self.current_style_name, DEFAULT_STYLES["macOS Dock"]))
        self.bg_image = None

        # Layout containers
        self.container = QtWidgets.QWidget(self)
        self.outer = QtWidgets.QBoxLayout(QtWidgets.QBoxLayout.LeftToRight); self.outer.setContentsMargins(0,0,0,0); self.setLayout(self.outer)
        self.outer.addWidget(self.container)
        self.inner = QtWidgets.QBoxLayout(QtWidgets.QBoxLayout.LeftToRight); self.inner.setContentsMargins(16,8,16,8); self.container.setLayout(self.inner)

        # Shadows/glow
        self._shadow = QtWidgets.QGraphicsDropShadowEffect()
        self.container.setGraphicsEffect(self._shadow)

        self.app_bar = QtWidgets.QWidget(); self.app_layout = QtWidgets.QBoxLayout(QtWidgets.QBoxLayout.LeftToRight); self.app_layout.setContentsMargins(0,0,0,0); self.app_bar.setLayout(self.app_layout)
        self.widget_bar = QtWidgets.QWidget(); self.widget_layout = QtWidgets.QBoxLayout(QtWidgets.QBoxLayout.LeftToRight); self.widget_layout.setContentsMargins(0,0,0,0); self.widget_bar.setLayout(self.widget_layout)
        self.left_spacer = QtWidgets.QSpacerItem(40,20,QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        self.right_spacer= QtWidgets.QSpacerItem(40,20,QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)

        # Magnify storage & params BEFORE _build_apps
        self._buttons: List[DockButton] = []
        self._magnify_enabled = self.current_style.get("magnify", True)
        self._magnify_factor = self.current_style.get("magnify_factor", 1.6)
        self._magnify_sigma = self.current_style.get("magnify_sigma", 70.0)

        # Build content
        self._build_apps()
        self._build_widgets()

        # Context menu + settings
        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._open_context_menu)
        self.settings_dialog: Optional[SettingsDialog] = None

        # Auto-hide & animation
        self._hover=False; self._hidden=False; self._edge_margin=2
        self._anim = QtCore.QPropertyAnimation(self, b"pos", self)
        self._autohide_timer = QtCore.QTimer(self); self._autohide_timer.timeout.connect(self._check_autohide); self._autohide_timer.start(200)

        # Dragging
        self._drag=False; self._drag_pos=QtCore.QPoint()

        # Windows enumeration/indicators
        self._win_timer = QtCore.QTimer(self)
        self._win_timer.timeout.connect(self._refresh_window_indicators)
        self._win_timer.start(1500)

        self.apply_style(self.current_style_name)

        # Hotkeys
        QtWidgets.QApplication.instance().installNativeEventFilter(self)
        register_hotkeys(int(self.winId()))

    # ----- Painting & effects -----
    def paintEvent(self, e: QtGui.QPaintEvent):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)

        rect = self.rect()
        radius = int(self.current_style.get("radius", 0))

        # Clip to rounded-rect so backgrounds/overlays match the bar shape
        p.save()
        path = QtGui.QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        p.setClipPath(path)

        # Get consistent RGBA regardless of whether settings used [r,g,b,a] or [r,g,b]+opacity
        r, g, b, a = _split_rgb_opacity(self.current_style)

        # Background image or color (fully transparent allowed when a == 0)
        img = self.bg_image
        if img and not img.isNull():
            p.drawPixmap(
                0, 0,
                img.scaled(rect.size(), QtCore.Qt.IgnoreAspectRatio, QtCore.Qt.SmoothTransformation)
            )
        else:
            if a > 0:
                p.fillRect(rect, QtGui.QColor(r, g, b, a))

        # Optional visual effects/overlays
        eff = self.current_style.get("effect", "none")

        if eff in ("liquid", "glass"):
            # Glossy highlight band (top half) for a "liquid glass" feel
            grad = QtGui.QLinearGradient(rect.topLeft(), rect.bottomLeft())
            grad.setColorAt(0.0, QtGui.QColor(255, 255, 255, 70))
            grad.setColorAt(0.25, QtGui.QColor(255, 255, 255, 30))
            grad.setColorAt(1.0, QtGui.QColor(255, 255, 255, 0))
            h = int(rect.height() * 0.55)
            p.fillRect(QtCore.QRect(rect.x(), rect.y(), rect.width(), h), QtGui.QBrush(grad))

        if eff == "xp_gloss":
            # Classic XP glossy cap
            grad = QtGui.QLinearGradient(rect.topLeft(), rect.bottomLeft())
            grad.setColorAt(0.0, QtGui.QColor(255, 255, 255, 120))
            grad.setColorAt(0.4, QtGui.QColor(255, 255, 255, 40))
            grad.setColorAt(1.0, QtGui.QColor(255, 255, 255, 0))
            p.fillRect(QtCore.QRect(rect.x(), rect.y(), rect.width(), int(rect.height() * 0.5)), QtGui.QBrush(grad))

        if eff == "neon":
            # Subtle inner glow ring
            pen = QtGui.QPen(QtGui.QColor(255, 255, 255, 36))
            pen.setWidth(2)
            p.setPen(pen)
            p.drawRoundedRect(rect.adjusted(1, 1, -2, -2), radius, radius)

        # Optional outline
        if self.current_style.get("outline", False):
            pen = QtGui.QPen(QtGui.QColor(255, 255, 255, 35))
            pen.setWidth(1)
            p.setPen(pen)
            p.drawRoundedRect(rect.adjusted(0, 0, -1, -1), radius, radius)

        # macOS-style "shelf" highlight line, when dock is at bottom
        if self.current_style.get("shelf_highlight", False) and self.current_style.get("position") == "bottom":
            y = rect.top() + 6
            shelf = QtGui.QLinearGradient(rect.left(), y, rect.right(), y)
            shelf.setColorAt(0.0, QtGui.QColor(255, 255, 255, 30))
            shelf.setColorAt(0.5, QtGui.QColor(255, 255, 255, 70))
            shelf.setColorAt(1.0, QtGui.QColor(255, 255, 255, 30))
            # a thin highlight strip across the bar
            p.fillRect(QtCore.QRect(rect.left() + 16, y, rect.width() - 32, 2), QtGui.QBrush(shelf))

        p.restore()
        super().paintEvent(e)


    def _apply_effects(self):
        # Shadow/glow as you already have...
        if self.current_style.get("glow", True):
            self._shadow.setBlurRadius(32)
            self._shadow.setColor(QtGui.QColor(0, 0, 0, 120))
            self._shadow.setOffset(0, 6)
        else:
            self._shadow.setBlurRadius(0)

        # Accent / Mica
        eff = self.current_style.get("effect", "none")
        blur_mode = self.current_style.get("blur_mode", "none")

        # Pull r,g,b,a safely
        r, g, b, a = _split_rgb_opacity(self.current_style)

        hwnd = self.winId().__int__()
        set_window_accent(hwnd, blur_mode, r, g, b, a)
        set_window_mica(hwnd, eff == "mica")

    # ----- Build content -----
    def _build_apps(self):
        while self.app_layout.count():
            it = self.app_layout.takeAt(0); w = it.widget(); w and w.deleteLater()
        self._buttons.clear()
        base = self.current_style["icon_size"]
        for app in self.settings.get("apps", []):
            btn = DockButton(app.get("name",Path(app["path"]).stem), icon_for_path(app["path"]), app["path"], base)
            self.app_layout.addWidget(btn); self._buttons.append(btn)

    def _build_widgets(self):
        while self.widget_layout.count():
            it = self.widget_layout.takeAt(0); w = it.widget(); w and w.deleteLater()
        reg = dict(BUILTIN_WIDGETS); reg.update(load_user_widgets())
        for name in self.settings.get("widgets", []):
            cls = reg.get(name)
            if not cls: continue
            try: self.widget_layout.addWidget(cls())
            except Exception: continue

    # ----- Style/layout application -----
    def apply_style(self, style_name: str):
        self.current_style_name = style_name
        self.current_style = dict(self.styles.get(style_name, DEFAULT_STYLES["macOS Dock"]))
        pos = self.current_style["position"]
        dir_main = (QtWidgets.QBoxLayout.TopToBottom if pos in ("left","right") else QtWidgets.QBoxLayout.LeftToRight)
        self.inner.setDirection(dir_main)
        self.app_layout.setDirection(dir_main)
        self.widget_layout.setDirection(dir_main)

        # rebuild inner order for alignment
        while self.inner.count():
            it = self.inner.takeAt(0); w = it.widget(); w and w.setParent(None)
        align = self.current_style.get("alignment","center")
        if align in ("left","top"):
            self.inner.addWidget(self.app_bar); self.inner.addWidget(self.widget_bar); self.inner.addItem(self.right_spacer)
        elif align in ("right","bottom"):
            self.inner.addItem(self.left_spacer); self.inner.addWidget(self.app_bar); self.inner.addWidget(self.widget_bar)
        else:
            self.inner.addItem(self.left_spacer); self.inner.addWidget(self.app_bar); self.inner.addWidget(self.widget_bar); self.inner.addItem(self.right_spacer)

        # size + snap
        screen = QtGui.QGuiApplication.primaryScreen().availableGeometry()
        thickness = self.current_style["height"] if pos in ("top","bottom") else self.current_style["width"]
        if pos in ("top","bottom"): self.resize(screen.width(), thickness)
        else: self.resize(thickness, screen.height())

        self._apply_effects()
        img = self.current_style.get("bg_image")
        self.bg_image = QtGui.QPixmap(img) if img and Path(img).exists() else None
        self._set_spacing(self.current_style["spacing"])
        self._build_apps()
        self.snap_to_edge()
        self.update()
        self._save_settings()

    def snap_to_edge(self):
        screen = QtGui.QGuiApplication.primaryScreen().availableGeometry()
        pos = self.current_style["position"]
        if pos == "top":
            self.setGeometry(screen.x(), screen.y(), screen.width(), self.height())
        elif pos == "bottom":
            self.setGeometry(screen.x(), screen.bottom()-self.height()+1, screen.width(), self.height())
        elif pos == "left":
            self.setGeometry(screen.x(), screen.y(), self.width(), screen.height())
        else:
            self.setGeometry(screen.right()-self.width()+1, screen.y(), self.width(), screen.height())

    # ----- Autohide (hover to reveal) with animation -----
    def _anim_to(self, x: int, y: int):
        dur = int(self.current_style.get("anim_ms", 160))
        ease = easing_from_name(self.current_style.get("anim_ease","OutCubic"))
        self._anim.stop()
        self._anim.setDuration(dur)
        self._anim.setEasingCurve(ease)
        self._anim.setStartValue(self.pos())
        self._anim.setEndValue(QtCore.QPoint(x,y))
        self._anim.start()

    def _check_autohide(self):
        if not self.current_style.get("auto_hide", False): return
        mouse = QtGui.QCursor.pos(); rect = self.frameGeometry(); pos = self.current_style["position"]; thr = 2
        at_edge = (mouse.y() <= rect.y()+thr if pos=="top" else
                   mouse.y() >= rect.bottom()-thr if pos=="bottom" else
                   mouse.x() <= rect.x()+thr if pos=="left" else
                   mouse.x() >= rect.right()-thr)
        if at_edge:
            self._show_bar()
        else:
            self._hide_bar()

    def _hide_bar(self):
        if self._hidden: return
        self._hidden=True; geo=self.geometry(); pos=self.current_style["position"]
        if pos=="top": self._anim_to(geo.x(), geo.y()-(self.height()-self._edge_margin))
        elif pos=="bottom": self._anim_to(geo.x(), geo.y()+(self.height()-self._edge_margin))
        elif pos=="left": self._anim_to(geo.x()-(self.width()-self._edge_margin), geo.y())
        else: self._anim_to(geo.x()+(self.width()-self._edge_margin), geo.y())

    def _show_bar(self):
        if not self._hidden: return
        self._hidden=False; self.snap_to_edge()  # snap immediately, then animate a subtle nudge to ensure visibility
        # optional: tiny bounce is covered by easing curve

    # ----- Mouse / magnify (hover only) -----
    def mousePressEvent(self,e):
        if e.button()==QtCore.Qt.LeftButton:
            self._drag=True; self._drag_pos=e.globalPosition().toPoint()-self.frameGeometry().topLeft(); e.accept()
    def mouseMoveEvent(self,e):
        if QtCore.Qt.LeftButton and self._drag:
            self.move(e.globalPosition().toPoint()-self._drag_pos); e.accept()
        # magnify on hover
        if self._magnify_enabled and self._buttons:
            self._update_magnify(e.globalPosition().toPoint())
    def mouseReleaseEvent(self,e):
        self._drag=False; self.snap_to_edge()
    def enterEvent(self,e): self._hover=True
    def leaveEvent(self,e):
        self._hover=False
        # reset sizes
        base = self.current_style["icon_size"]
        for b in self._buttons: b.set_scaled(base)

    def _update_magnify(self, cursor: QtCore.QPoint):
        pos = self.current_style["position"]; vertical = pos in ("left","right")
        sigma = self._magnify_sigma; base = self.current_style["icon_size"]; factor = self._magnify_factor
        for btn in self._buttons:
            center = btn.mapToGlobal(btn.rect().center())
            dist = abs((cursor.y()-center.y()) if vertical else (cursor.x()-center.x()))
            scale = 1.0 + (factor-1.0) * math.exp(-(dist*dist)/(2*sigma*sigma))
            btn.set_scaled(int(base*scale))

    # ----- Window indicators -----
    def _refresh_window_indicators(self):
        mapping = windows_by_exe_key()
        for btn in self._buttons:
            btn.update_windows(mapping.get(btn.app_key, []))

    # ----- Context menu / settings shortcuts -----
    def _open_context_menu(self, pos_local: QtCore.QPoint):
        m = QtWidgets.QMenu(self)
        m.addAction("Customize… (Ctrl+,)", self.open_settings)
        style_menu = m.addMenu("Style")
        for name in sorted(self.styles.keys()):
            style_menu.addAction(name, lambda chk=False,n=name: self.apply_style(n))
        m.addSeparator()
        m.addAction("Import Windows pinned apps", self.import_pinned_apps)
        m.addSeparator()
        m.addAction("Restore Windows Taskbar", self._restore_taskbar)
        m.addAction("Hide Windows Taskbar", hide_taskbar)
        m.addSeparator()
        m.addAction("Save Settings", self._save_settings)
        m.addAction("Exit", self._exit)
        m.exec(self.mapToGlobal(pos_local))

    def open_settings(self):
        if self.settings_dialog and self.settings_dialog.isVisible():
            self.settings_dialog.activateWindow(); return
        self.settings_dialog = SettingsDialog(self); self.settings_dialog.show()

    # ----- Public helpers for settings dialog -----
    def _set_position(self, pos: str): self.current_style["position"]=pos; self.styles[self.current_style_name]=dict(self.current_style); self.apply_style(self.current_style_name)
    def _set_alignment(self, a: str): self.current_style["alignment"]=a; self.styles[self.current_style_name]=dict(self.current_style); self.apply_style(self.current_style_name)
    def _set_thickness(self, v:int):
        if self.current_style["position"] in ("top","bottom"): self.current_style["height"]=v
        else: self.current_style["width"]=v
        self.styles[self.current_style_name]=dict(self.current_style); self.apply_style(self.current_style_name)
    def _set_icon_size(self, v:int):
        self.current_style["icon_size"]=v; self.styles[self.current_style_name]=dict(self.current_style); self._build_apps(); self._save_settings()
    def _set_radius(self, v:int): self.current_style["radius"]=v; self.styles[self.current_style_name]=dict(self.current_style); self.update(); self._save_settings()
    def _set_spacing(self, v:int):
        self.current_style["spacing"]=v; self.app_layout.setSpacing(v); self.widget_layout.setSpacing(v); self.inner.setSpacing(v); self._save_settings()
    def _toggle_autohide(self, b:bool): self.current_style["auto_hide"]=b; self.styles[self.current_style_name]=dict(self.current_style); self._save_settings()
    def _toggle_magnify(self, b:bool): self._magnify_enabled=b; self.current_style["magnify"]=b; self.styles[self.current_style_name]=dict(self.current_style); self._save_settings()
    def _set_magnify_power(self, f:float): self._magnify_factor=max(1.0,f); self.current_style["magnify_factor"]=self._magnify_factor; self.styles[self.current_style_name]=dict(self.current_style); self._save_settings()
    def _set_magnify_sigma(self, s:float): self._magnify_sigma=s; self.current_style["magnify_sigma"]=s; self.styles[self.current_style_name]=dict(self.current_style); self._save_settings()
    def _set_anim_ms(self, ms:int): self.current_style["anim_ms"]=ms; self.styles[self.current_style_name]=dict(self.current_style); self._save_settings()
    def _set_anim_ease(self, name:str): self.current_style["anim_ease"]=name; self.styles[self.current_style_name]=dict(self.current_style); self._save_settings()

    def import_pinned_apps(self):
        if not PINNED_DIR.exists():
            QtWidgets.QMessageBox.information(self,"Pinned not found", "Pinned Taskbar folder not found.\nYou can still add apps manually.")
            return
        new_items = []
        for lnk in PINNED_DIR.glob("*.lnk"):
            new_items.append({"name": lnk.stem, "path": str(lnk)})
        cur = self.settings.setdefault("apps", [])
        existing = {(a["name"], a["path"]) for a in cur}
        added = 0
        for it in new_items:
            key = (it["name"], it["path"])
            if key not in existing:
                cur.append(it); added += 1
        self._build_apps(); self._save_settings()
        QtWidgets.QMessageBox.information(self,"Import complete", f"Imported {added} pinned app(s).")

    def _add_app(self):
        fn,_=QtWidgets.QFileDialog.getOpenFileName(self,"Choose application (.exe/.lnk)","C:\\","Programs (*.exe *.lnk)")
        if not fn: return
        name,ok = QtWidgets.QInputDialog.getText(self,"App name","Display name:", text=Path(fn).stem)
        if not ok: return
        self.settings.setdefault("apps", []).append({"name": name, "path": fn})
        self._build_apps(); self._save_settings()
    def _remove_app(self):
        apps=self.settings.get("apps",[])
        if not apps: return
        names=[a["name"] for a in apps]
        item,ok=QtWidgets.QInputDialog.getItem(self,"Remove app","Choose:",names,0,False)
        if ok:
            idx=names.index(item); apps.pop(idx); self._build_apps(); self._save_settings()

    def _add_widget(self, name:str):
        lst=self.settings.setdefault("widgets",[])
        if name not in lst: lst.append(name)
        self._build_widgets(); self._save_settings()
    def _add_user_widget(self):
        reg = load_user_widgets()
        if not reg:
            QtWidgets.QMessageBox.information(self,"No user widgets",
                f"Drop .py files with QWidget subclasses into:\n{WIDGETS_DIR}")
            return
        names=list(reg.keys())
        item,ok=QtWidgets.QInputDialog.getItem(self,"Add user widget","Choose:",names,0,False)
        if ok and item: self._add_widget(item)
    def _remove_widget(self):
        lst=self.settings.get("widgets",[])
        if not lst: return
        item,ok=QtWidgets.QInputDialog.getItem(self,"Remove widget","Choose:",lst,0,False)
        if ok:
            lst.remove(item); self._build_widgets(); self._save_settings()

    def _save_settings(self):
        self.settings["styles"]=self.styles; self.settings["current_style"]=self.current_style_name
        save_json(SETTINGS_FILE, self.settings)

    def _restore_taskbar(self): show_taskbar()
    def _exit(self):
        self._restore_taskbar(); QtWidgets.QApplication.quit()

    # ----- Hotkeys -----
    def nativeEventFilter(self, eventType, message):
        if eventType == "windows_generic_MSG":
            msg = ctypes.wintypes.MSG.from_address(int(message))
            if msg.message == WM_HOTKEY:
                if msg.wParam == HOTKEY_ID_TOGGLE_TASKBAR:
                    hwnd = _find_window("Shell_TrayWnd"); visible = user32.IsWindowVisible(hwnd) if hwnd else False
                    hide_taskbar() if visible else show_taskbar()
                elif msg.wParam == HOTKEY_ID_OPEN_SETTINGS:
                    self.open_settings()
        return False, 0

# ------------------ Tray icon ------------------------------------------------------
class Tray(QtWidgets.QSystemTrayIcon):
    def __init__(self, window: TaskbarWindow):
        super().__init__(QtGui.QIcon.fromTheme("applications-system"))
        self.w = window; self.setToolTip("Custom Taskbar")
        m = QtWidgets.QMenu()
        m.addAction("Show Custom Taskbar", self._show)
        m.addAction("Customize… (Ctrl+,)", self.w.open_settings)
        m.addSeparator()
        m.addAction("Import Windows pinned apps", self.w.import_pinned_apps)
        m.addSeparator()
        m.addAction("Restore Windows Taskbar", self.w._restore_taskbar)
        m.addAction("Hide Windows Taskbar", hide_taskbar)
        m.addSeparator()
        m.addAction("Exit", self.w._exit)
        self.setContextMenu(m); self.show()
    def _show(self):
        self.w.show(); self.w.raise_(); self.w.activateWindow()

# ------------------ Main -----------------------------------------------------------
def main():
    settings = load_json(SETTINGS_FILE, DEFAULT_SETTINGS)
    app = QtWidgets.QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    atexit.register(show_taskbar)
    hide_taskbar()

    win = TaskbarWindow(settings)
    win.show(); win.raise_(); win.activateWindow()
    tray = Tray(win)

    # Tip on first run
    if not settings.get("apps"):
        QtCore.QTimer.singleShot(900, lambda: QtWidgets.QToolTip.showText(QtGui.QCursor.pos(),
            "Tip: Right-click → Import Windows pinned apps"))

    ret = app.exec()
    try: unregister_hotkeys(int(win.winId()))
    except Exception: pass
    sys.exit(ret)

if __name__ == "__main__":
    main()
