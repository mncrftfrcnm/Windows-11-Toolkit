# ai_cursor_designer_gui_v2.py
# Windows 10/11 • Python 3.10+ • PyQt6 + Pillow; optional SD-Turbo (DirectML) for textures
# Key upgrades:
#  - Reliable "Install & Apply (Current User)" using HKCU scheme + SPI_SETCURSORS with broadcast
#  - True .cur frames (hotspots) -> .ani
#  - Animated live preview
#  - Randomize: color, path shape, tail len, frames, fps, seed
#
# Run: python ai_cursor_designer_gui_v2.py

import os, sys, math, struct, time, random
from dataclasses import dataclass
from typing import Optional, List, Tuple
from io import BytesIO

from PIL import Image, ImageDraw, ImageFilter
from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt

# ------------------------ CUR / ANI writers ------------------------

def cur_bytes_from_image(img: Image.Image, hotspot=(0,0)) -> bytes:
    """Encode a single-image .cur (PNG payload) with hotspot stored in entry."""
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    png = BytesIO(); img.save(png, "PNG"); png = png.getvalue()
    icondir = struct.pack("<HHH", 0, 2, 1)  # reserved=0, type=2(CUR), count=1
    w = img.width if img.width < 256 else 0
    h = img.height if img.height < 256 else 0
    hsx, hsy = max(0, hotspot[0]), max(0, hotspot[1])  # HOTSPOT (CUR-specific)
    entry = struct.pack("<BBBBHHII", w, h, 0, 0, hsx, hsy, len(png), 6+16)
    return icondir + entry + png

def write_ani_from_cur_frames(cur_frames: List[bytes], fps: int, out_path: str):
    """Minimal RIFF ACON with CUR frames as 'icon' chunks."""
    jif_rate = 60
    ticks = max(1, int(jif_rate / max(1, fps)))
    c = len(cur_frames)
    anih = struct.pack("<IIIIIIII", 36, c, c, 0, 0, 32, 1, jif_rate) + struct.pack("<I", 1)
    chunks = [
        b"anih"+struct.pack("<I", len(anih))+anih,
        b"rate"+struct.pack("<I", 4*c)+b"".join(struct.pack("<I", ticks) for _ in range(c)),
        b"seq "+struct.pack("<I", 4*c)+b"".join(struct.pack("<I", i) for i in range(c)),
    ]
    fram_payload = b""
    for curb in cur_frames:
        fram_payload += b"icon"+struct.pack("<I", len(curb))+curb
        if len(curb) & 1: fram_payload += b"\x00"
    fram = b"LIST"+struct.pack("<I", len(b"fram")+len(fram_payload))+b"fram"+fram_payload
    payload = b"".join(chunks)+fram
    riff = b"RIFF"+struct.pack("<I", len(b"ACON")+len(payload))+b"ACON"+payload
    with open(out_path, "wb") as f: f.write(riff)

# ------------------------ Optional AI texture ------------------------

def try_make_ai_texture(prompt: str, model_dir: str, size=256) -> Optional[Image.Image]:
    try:
        import torch, torch_directml                    # type: ignore
        from diffusers import AutoPipelineForText2Image  # type: ignore
        device = torch_directml.device()
        pipe = AutoPipelineForText2Image.from_pretrained(model_dir, torch_dtype=torch.float16).to(device)
        img = pipe(prompt, num_inference_steps=1, guidance_scale=0.0, width=size, height=size).images[0]
        return img.convert("RGBA")
    except Exception as e:
        print("AI texture generation failed:", e)
        return None

# ------------------------ Cursor synthesis ------------------------

@dataclass
class CursorParams:
    size: int = 64
    frames: int = 16
    fps: int = 24
    hotspot: Tuple[int,int] = (2,2)
    glow_color: Tuple[int,int,int] = (200,230,255)
    tail_len: int = 12
    path_kind: str = "comet"   # comet | orbit | zigzag | swirl
    seed: int = 42
    use_ai: bool = False
    ai_prompt: str = "glassy neon texture, soft glow"
    model_dir: str = r"C:\models\sd_turbo"

def _path_xy(t: float, S: int, kind: str) -> Tuple[int,int]:
    """Normalized parametric paths for the head."""
    if kind == "orbit":
        x = 0.5 + 0.28*math.cos(2*math.pi*t)
        y = 0.5 + 0.18*math.sin(2*math.pi*t*1.2)
    elif kind == "zigzag":
        # triangle wave horizontally, gentle sine vertically
        tri = 2*abs(2*(t - math.floor(t+0.5)))  # 0..1..0
        x = 0.2 + 0.6*tri
        y = 0.5 + 0.1*math.sin(2*math.pi*t*3.0)
    elif kind == "swirl":
        r = 0.05 + 0.30*t
        ang = 2*math.pi*1.75*t
        x = 0.5 + r*math.cos(ang)
        y = 0.5 + r*math.sin(ang)
    else:  # comet (default): left->right gentle sine
        x = 0.25 + 0.5*t
        y = 0.5 + 0.06*math.sin(2*math.pi*t)
    return int(x*S), int(y*S)

def make_frame(t: float, p: CursorParams, ai_tex: Optional[Image.Image], rng: random.Random) -> Image.Image:
    S = p.size
    img = Image.new("RGBA", (S, S), (0,0,0,0))
    d = ImageDraw.Draw(img)

    cx, cy = _path_xy(t, S, p.path_kind)

    # jitter for "alive" feel
    j = 0.4 + 0.6*rng.random()
    tail_jit = int(1 + 1.8*rng.random())
    hue_shift = rng.randint(-8, 8)

    # tail dots (with slight wander)
    for i in range(p.tail_len, 0, -1):
        alpha = int(10 + 12*i*j)
        r = max(1, int(i*0.8))
        ox = int((i*3) + rng.uniform(-tail_jit, tail_jit))
        oy = int(rng.uniform(-tail_jit, tail_jit))
        col = (
            max(0, min(255, p.glow_color[0] + hue_shift)),
            max(0, min(255, p.glow_color[1] + hue_shift)),
            max(0, min(255, p.glow_color[2] + hue_shift)),
        )
        d.ellipse((cx-ox-r, cy-oy-r, cx-ox+r, cy-oy+r), fill=(col[0],col[1],col[2],alpha))

    # head: AI patch or plain glow
    head_r = 6
    if ai_tex and p.use_ai:
        patch = ai_tex.resize((head_r*4, head_r*4), Image.LANCZOS)
        mask = Image.new("L", patch.size, 0)
        ImageDraw.Draw(mask).ellipse((0,0,patch.width-1,patch.height-1), fill=255)
        img.paste(patch, (cx-head_r*2, cy-head_r*2), mask)

    # core + rim
    d.ellipse((cx-4, cy-4, cx+4, cy+4), fill=(255,255,255,220))
    d.ellipse((cx-head_r, cy-head_r, cx+head_r, cy+head_r),
              outline=(p.glow_color[0],p.glow_color[1],p.glow_color[2],160), width=2)

    # soft glow
    img = Image.alpha_composite(img.filter(ImageFilter.GaussianBlur(2)), img)
    return img

def build_frames(p: CursorParams, ai_tex: Optional[Image.Image]) -> List[Image.Image]:
    rng = random.Random(p.seed)
    return [make_frame(i/p.frames, p, ai_tex, rng) for i in range(p.frames)]

# ------------------------ GUI ------------------------

CURSOR_ROLES = [
    ("Arrow",       "Normal Select"),
    ("Hand",        "Link Select"),
    ("IBeam",       "Text Select"),
    ("AppStarting", "Working In Background"),
    ("Wait",        "Busy"),
]

class CursorGUI(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AI Cursor Designer (v2)")
        self.p = CursorParams()
        self.ai_tex: Optional[Image.Image] = None
        self.frames: List[Image.Image] = []
        self.frame_index = 0

        self._ui()
        self._regen_frames()
        self.animTimer = QtCore.QTimer(self, interval=int(1000/max(1,self.p.fps)), timeout=self._tick)
        self.animTimer.start()

    # ---------- UI ----------
    def _ui(self):
        lay = QtWidgets.QVBoxLayout(self)

        # row: size/frames/fps
        g = QtWidgets.QGridLayout()
        self.sizeSpin = QtWidgets.QSpinBox(minimum=16, maximum=256, value=self.p.size)
        self.framesSpin= QtWidgets.QSpinBox(minimum=4, maximum=64, value=self.p.frames)
        self.fpsSpin  = QtWidgets.QSpinBox(minimum=1, maximum=60, value=self.p.fps)
        self.hotxSpin = QtWidgets.QSpinBox(minimum=0, maximum=255, value=self.p.hotspot[0])
        self.hotySpin = QtWidgets.QSpinBox(minimum=0, maximum=255, value=self.p.hotspot[1])
        self.tailSpin = QtWidgets.QSpinBox(minimum=4, maximum=30, value=self.p.tail_len)
        self.seedSpin = QtWidgets.QSpinBox(minimum=0, maximum=2**31-1, value=self.p.seed)

        self.pathBox  = QtWidgets.QComboBox(); self.pathBox.addItems(["comet","orbit","zigzag","swirl"])
        self.pathBox.setCurrentText(self.p.path_kind)

        self.colorBtn = QtWidgets.QPushButton("Glow Color")

        g.addWidget(QtWidgets.QLabel("Size"),0,0); g.addWidget(self.sizeSpin,0,1)
        g.addWidget(QtWidgets.QLabel("Frames"),0,2); g.addWidget(self.framesSpin,0,3)
        g.addWidget(QtWidgets.QLabel("FPS"),0,4); g.addWidget(self.fpsSpin,0,5)
        g.addWidget(QtWidgets.QLabel("Hotspot X"),1,0); g.addWidget(self.hotxSpin,1,1)
        g.addWidget(QtWidgets.QLabel("Hotspot Y"),1,2); g.addWidget(self.hotySpin,1,3)
        g.addWidget(QtWidgets.QLabel("Tail len"),1,4); g.addWidget(self.tailSpin,1,5)
        g.addWidget(QtWidgets.QLabel("Path"),2,0); g.addWidget(self.pathBox,2,1)
        g.addWidget(QtWidgets.QLabel("Seed"),2,2); g.addWidget(self.seedSpin,2,3)
        g.addWidget(self.colorBtn,2,4,1,2)
        lay.addLayout(g)

        # AI controls
        aiRow = QtWidgets.QHBoxLayout()
        self.useAI = QtWidgets.QCheckBox("Use AI texture")
        self.modelEdit = QtWidgets.QLineEdit(self.p.model_dir)
        self.aiPrompt = QtWidgets.QLineEdit(self.p.ai_prompt)
        self.aiBtn = QtWidgets.QPushButton("Generate AI Texture")
        aiRow.addWidget(self.useAI)
        aiRow.addWidget(QtWidgets.QLabel("Model dir:")); aiRow.addWidget(self.modelEdit,1)
        aiRow.addWidget(self.aiBtn)
        lay.addLayout(aiRow)
        lay.addWidget(self.aiPrompt)

        # Preview
        self.preview = QtWidgets.QLabel(alignment=QtCore.Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumHeight(220)
        self.preview.setStyleSheet("QLabel{background:#111;border:1px solid #333;}")
        lay.addWidget(self.preview, 1)

        # Buttons
        row = QtWidgets.QHBoxLayout()
        self.randBtn = QtWidgets.QPushButton("Randomize")
        self.regenBtn = QtWidgets.QPushButton("Regenerate")
        self.exportBtn = QtWidgets.QPushButton("Export .ani + .cur frames")
        self.applyBtn  = QtWidgets.QPushButton("Install & Apply (Current User)")
        row.addWidget(self.randBtn); row.addWidget(self.regenBtn)
        row.addWidget(self.exportBtn); row.addWidget(self.applyBtn)
        lay.addLayout(row)

        # Apply roles
        self.rolesBox = QtWidgets.QGroupBox("Apply to these cursor roles")
        form = QtWidgets.QFormLayout(self.rolesBox)
        self.roleChecks = {}
        for key, desc in CURSOR_ROLES:
            cb = QtWidgets.QCheckBox(desc); cb.setChecked(key in ["Arrow","AppStarting","Wait"])
            self.roleChecks[key] = cb
            form.addRow(cb)
        lay.addWidget(self.rolesBox)

        # wire signals
        for w in [self.sizeSpin, self.framesSpin, self.fpsSpin, self.hotxSpin, self.hotySpin, self.tailSpin, self.seedSpin]:
            w.valueChanged.connect(self._params_changed)
        self.pathBox.currentTextChanged.connect(self._params_changed)
        self.colorBtn.clicked.connect(self._pick_color)
        self.aiBtn.clicked.connect(self._gen_ai)
        self.randBtn.clicked.connect(self._randomize)
        self.regenBtn.clicked.connect(self._regen_frames)
        self.exportBtn.clicked.connect(self._export_dialog)
        self.applyBtn.clicked.connect(self._install_and_apply)

    # ---------- logic ----------
    def _params_changed(self, *_):
        self.p.size = self.sizeSpin.value()
        self.p.frames = self.framesSpin.value()
        self.p.fps = self.fpsSpin.value()
        self.p.hotspot = (self.hotxSpin.value(), self.hotySpin.value())
        self.p.tail_len = self.tailSpin.value()
        self.p.seed = self.seedSpin.value()
        self.p.path_kind = self.pathBox.currentText()
        self.animTimer.setInterval(int(1000/max(1,self.p.fps)))
        self._regen_frames()

    def _pick_color(self):
        c = QtWidgets.QColorDialog.getColor(QtGui.QColor(*self.p.glow_color), self, "Glow color")
        if c.isValid():
            self.p.glow_color = (c.red(), c.green(), c.blue())
            self._regen_frames()

    def _gen_ai(self):
        self.p.use_ai = self.useAI.isChecked()
        if not self.p.use_ai:
            QtWidgets.QMessageBox.information(self, "AI off", "Enable 'Use AI texture' first."); return
        tex = try_make_ai_texture(self.aiPrompt.text().strip(), self.modelEdit.text().strip(), size=256)
        if tex is None:
            QtWidgets.QMessageBox.warning(self, "AI failed", "Check model dir and dependencies.")
            return
        self.ai_tex = tex
        tex.save("cursor_ai_texture_preview.png")
        self._regen_frames()

    def _randomize(self):
        self.sizeSpin.setValue(random.choice([48,64,72,96]))
        self.framesSpin.setValue(random.choice([12,16,20,24]))
        self.fpsSpin.setValue(random.choice([18,24,30]))
        self.tailSpin.setValue(random.randint(8,18))
        self.seedSpin.setValue(random.randint(0, 2**31-1))
        self.pathBox.setCurrentText(random.choice(["comet","orbit","zigzag","swirl"]))
        # bright-ish pastel
        base = random.randint(170,255)
        off  = random.randint(-40,40)
        col = (max(0,min(255,base)),
               max(0,min(255,base+off)),
               max(0,min(255,base-abs(off))))
        self.p.glow_color = col
        self._regen_frames()

    def _regen_frames(self):
        self.frames = build_frames(self.p, self.ai_tex if (self.p.use_ai and self.ai_tex) else None)
        self.frame_index = 0
        self._paint_preview()

    def _tick(self):
        self.frame_index = (self.frame_index + 1) % max(1,len(self.frames))
        self._paint_preview()

    def _paint_preview(self):
        if not self.frames:
            return
        from PIL.ImageQt import ImageQt
        im = self.frames[self.frame_index]
        qimg = ImageQt(im).copy()
        pix = QtGui.QPixmap.fromImage(qimg)
        self.preview.setPixmap(pix.scaled(self.preview.size(), QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                                          QtCore.Qt.TransformationMode.SmoothTransformation))

    # ---------- export/apply ----------
    def _export_dialog(self):
        d = QtWidgets.QFileDialog.getExistingDirectory(self, "Select export folder")
        if not d: return
        ani = self._write_export(d)
        QtWidgets.QMessageBox.information(self, "Exported", f"Wrote {ani}")

    def _install_and_apply(self):
        # Export into a stable per-user location so the paths don't break
        base = os.path.join(os.environ.get("LOCALAPPDATA", os.getcwd()), "AI_Cursors")
        os.makedirs(base, exist_ok=True)
        scheme = time.strftime("AICursor_%Y%m%d_%H%M%S")
        out_dir = os.path.join(base, scheme)
        os.makedirs(out_dir, exist_ok=True)
        ani_path = self._write_export(out_dir)

        # Write HKCU cursor scheme values for selected roles, then broadcast
        try:
            import winreg, ctypes
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\Cursors", 0, winreg.KEY_SET_VALUE) as k:
                for role, _desc in CURSOR_ROLES:
                    if self.roleChecks[role].isChecked():
                        winreg.SetValueEx(k, role, 0, winreg.REG_SZ, ani_path)
                # optional: set scheme name so Windows shows it
                winreg.SetValueEx(k, "Scheme Source", 0, winreg.REG_SZ, "AICursorDesigner")
            SPIF_UPDATEINIFILE = 0x01
            SPIF_SENDCHANGE    = 0x02
            # SPI_SETCURSORS = 0x0057 -> reload user cursors from registry
            ctypes.windll.user32.SystemParametersInfoW(0x0057, 0, None, SPIF_UPDATEINIFILE|SPIF_SENDCHANGE)
            QtWidgets.QMessageBox.information(self, "Applied",
                f"Installed to:\n{ani_path}\n\nIf you don't see it, open Settings > Bluetooth & devices > Mouse > Additional mouse settings > Pointers and confirm the scheme.")
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Apply failed", str(e))

    def _write_export(self, out_dir: str) -> str:
        os.makedirs(out_dir, exist_ok=True)
        cur_bytes_list = []
        for i, im in enumerate(self.frames):
            curb = cur_bytes_from_image(im, hotspot=self.p.hotspot)
            cur_bytes_list.append(curb)
            with open(os.path.join(out_dir, f"frame_{i:02d}.cur"), "wb") as f: f.write(curb)
        ani_path = os.path.join(out_dir, "cursor_ai.ani")
        write_ani_from_cur_frames(cur_bytes_list, self.p.fps, ani_path)
        return ani_path

if __name__ == "__main__":
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    app = QtWidgets.QApplication(sys.argv)
    g = CursorGUI(); g.show()
    sys.exit(app.exec())
