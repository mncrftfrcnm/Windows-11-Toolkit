# ai_wallpaper_generator.py
# PyQt6 GUI for local text->image wallpapers via DirectML (diffusers + torch-directml).
# Run: python ai_wallpaper_generator.py
# pip install PyQt6
import os, sys, threading, subprocess, time
from pathlib import Path
from dataclasses import dataclass
from PyQt6 import QtCore, QtGui, QtWidgets

# lazy imports inside worker so the app opens even before deps are installed
DML_OK = None

@dataclass
class GenConfig:
    model_dir: str
    prompt: str
    width: int = 3840
    height: int = 2160
    steps: int = 1    # for SD-Turbo 1–4
    guidance: float = 0.0
    seed: int | None = None
    out_path: str = "ai_wallpaper.png"

class GenWorker(QtCore.QThread):
    progress = QtCore.pyqtSignal(str)
    done = QtCore.pyqtSignal(str)

    def __init__(self, cfg: GenConfig):
        super().__init__()
        self.cfg = cfg

    def run(self):
        self.progress.emit("loading pipeline…")
        try:
            import torch
            import torch_directml
            from diffusers import AutoPipelineForText2Image
            device = torch_directml.device()
            pipe = AutoPipelineForText2Image.from_pretrained(
                self.cfg.model_dir, torch_dtype=torch.float16
            ).to(device)
            if self.cfg.seed is not None:
                import random
                torch.manual_seed(self.cfg.seed)
                random.seed(self.cfg.seed)
            self.progress.emit("generating…")
            image = pipe(
                self.cfg.prompt,
                num_inference_steps=self.cfg.steps,
                guidance_scale=self.cfg.guidance,
                width=self.cfg.width,
                height=self.cfg.height
            ).images[0]
            image.save(self.cfg.out_path)
            self.done.emit(self.cfg.out_path)
        except Exception as e:
            self.done.emit(f"ERROR: {e}")

class WallpaperApp(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AI Wallpaper Studio (DirectML, local)")
        self.setMinimumSize(800, 600)
        self._build_ui()

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)

        # Model path + Setup
        modelRow = QtWidgets.QHBoxLayout()
        self.modelEdit = QtWidgets.QLineEdit(r"C:\models\sd_turbo")
        self.browseBtn = QtWidgets.QPushButton("Browse…")
        self.setupBtn = QtWidgets.QPushButton("Auto-setup SD")
        modelRow.addWidget(QtWidgets.QLabel("Model dir:"))
        modelRow.addWidget(self.modelEdit, 1)
        modelRow.addWidget(self.browseBtn)
        modelRow.addWidget(self.setupBtn)
        layout.addLayout(modelRow)

        # Prompt
        self.promptEdit = QtWidgets.QPlainTextEdit("minimal dusk mountains, soft gradients, clean wallpaper")
        layout.addWidget(QtWidgets.QLabel("Prompt:"))
        layout.addWidget(self.promptEdit, 1)

        # Params
        grid = QtWidgets.QGridLayout()
        self.wSpin = QtWidgets.QSpinBox(); self.wSpin.setRange(256, 8192); self.wSpin.setValue(3840)
        self.hSpin = QtWidgets.QSpinBox(); self.hSpin.setRange(256, 8192); self.hSpin.setValue(2160)
        self.stepsSpin = QtWidgets.QSpinBox(); self.stepsSpin.setRange(1, 50); self.stepsSpin.setValue(1)
        self.guidanceSpin = QtWidgets.QDoubleSpinBox(); self.guidanceSpin.setRange(0.0, 20.0); self.guidanceSpin.setSingleStep(0.1); self.guidanceSpin.setValue(0.0)
        self.seedSpin = QtWidgets.QSpinBox(); self.seedSpin.setRange(-1, 2**31-1); self.seedSpin.setValue(-1)
        grid.addWidget(QtWidgets.QLabel("Width"), 0,0); grid.addWidget(self.wSpin,0,1)
        grid.addWidget(QtWidgets.QLabel("Height"),0,2); grid.addWidget(self.hSpin,0,3)
        grid.addWidget(QtWidgets.QLabel("Steps"), 1,0); grid.addWidget(self.stepsSpin,1,1)
        grid.addWidget(QtWidgets.QLabel("Guidance"),1,2); grid.addWidget(self.guidanceSpin,1,3)
        grid.addWidget(QtWidgets.QLabel("Seed (-1=random)"),2,0); grid.addWidget(self.seedSpin,2,1)
        layout.addLayout(grid)

        # Actions
        btnRow = QtWidgets.QHBoxLayout()
        self.genBtn = QtWidgets.QPushButton("Generate")
        self.todBtn = QtWidgets.QPushButton("Generate 4× Time-of-Day Set")
        btnRow.addWidget(self.genBtn)
        btnRow.addWidget(self.todBtn)
        layout.addLayout(btnRow)

        # Preview + log
        self.preview = QtWidgets.QLabel(alignment=QtCore.Qt.AlignmentFlag.AlignCenter)
        self.preview.setStyleSheet("QLabel{background:#111; border:1px solid #333;}")
        self.preview.setMinimumHeight(240)
        layout.addWidget(self.preview, 2)
        self.log = QtWidgets.QPlainTextEdit(readOnly=True)
        layout.addWidget(self.log, 1)

        # wire up
        self.browseBtn.clicked.connect(self._browse)
        self.setupBtn.clicked.connect(self._setup)
        self.genBtn.clicked.connect(self._generate_one)
        self.todBtn.clicked.connect(self._generate_set)

    def _log(self, s): self.log.appendPlainText(s)

    def _browse(self):
        d = QtWidgets.QFileDialog.getExistingDirectory(self, "Select model folder")
        if d: self.modelEdit.setText(d)

    def _setup(self):
        # run bootstrap_sd.py in a separate console
        model_dir = self.modelEdit.text().strip()
        os.makedirs(model_dir, exist_ok=True)
        cmd = [sys.executable, "bootstrap_sd.py", "--dir", model_dir]
        self._log(f"Running: {' '.join(cmd)}")
        threading.Thread(target=lambda: subprocess.call(cmd), daemon=True).start()

    def _generate_one(self, *, prompt_suffix=""):
        cfg = GenConfig(
            model_dir=self.modelEdit.text().strip(),
            prompt=self.promptEdit.toPlainText().strip() + prompt_suffix,
            width=self.wSpin.value(), height=self.hSpin.value(),
            steps=self.stepsSpin.value(), guidance=self.guidanceSpin.value(),
            seed=None if self.seedSpin.value()<0 else self.seedSpin.value(),
            out_path="ai_wallpaper.png"
        )
        self._run_worker(cfg)

    def _generate_set(self):
        base = Path.cwd() / "wallpapers_tod"; base.mkdir(exist_ok=True)
        presets = {
            "_dawn":  " , soft pink fog, gentle light",
            "_day":   " , clear bright sky, crisp colors",
            "_sunset":", golden hour, warm rim light",
            "_night": ", starry night, deep blues, subtle glow"
        }
        def job():
            for suf, extra in presets.items():
                cfg = GenConfig(
                    model_dir=self.modelEdit.text().strip(),
                    prompt=self.promptEdit.toPlainText().strip() + extra,
                    width=self.wSpin.value(), height=self.hSpin.value(),
                    steps=self.stepsSpin.value(), guidance=self.guidanceSpin.value(),
                    seed=None if self.seedSpin.value()<0 else self.seedSpin.value(),
                    out_path=str(base / f"wp{suf}.png")
                )
                self._run_worker_blocking(cfg)
            self._log(f"Saved set to {base}")
        threading.Thread(target=job, daemon=True).start()

    def _run_worker(self, cfg: GenConfig):
        self.worker = GenWorker(cfg)
        self.worker.progress.connect(self._log)
        self.worker.done.connect(self._on_done)
        self.worker.start()
        self._log("started…")

    def _run_worker_blocking(self, cfg: GenConfig):
        # used for the 4× set; runs in its own thread already
        try:
            import torch, torch_directml
            from diffusers import AutoPipelineForText2Image
            device = torch_directml.device()
            pipe = AutoPipelineForText2Image.from_pretrained(cfg.model_dir, torch_dtype=torch.float16).to(device)
            if cfg.seed is not None:
                import random
                torch.manual_seed(cfg.seed); random.seed(cfg.seed)
            img = pipe(cfg.prompt, num_inference_steps=cfg.steps, guidance_scale=cfg.guidance,
                       width=cfg.width, height=cfg.height).images[0]
            img.save(cfg.out_path)
            self._log(f"saved {cfg.out_path}")
        except Exception as e:
            self._log(f"ERROR: {e}")

    def _on_done(self, out_path: str):
        if out_path.startswith("ERROR:"):
            self._log(out_path); return
        self._log(f"saved {out_path}")
        pix = QtGui.QPixmap(out_path)
        self.preview.setPixmap(pix.scaled(self.preview.size(), QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                                          QtCore.Qt.TransformationMode.SmoothTransformation))

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    w = WallpaperApp(); w.show()
    sys.exit(app.exec())
