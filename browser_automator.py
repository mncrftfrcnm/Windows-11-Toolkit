import os
import re
import sys
import json
import time
import datetime
import subprocess
from dataclasses import dataclass
from typing import List, Optional, Dict, Any

# ---------------- PyQt6 ----------------
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal, QDate, QTime, QSize
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QTabWidget, QLabel, QLineEdit, QPushButton, QComboBox, QCheckBox,
    QFileDialog, QMessageBox, QListWidget, QListWidgetItem, QSpinBox,
    QDoubleSpinBox, QPlainTextEdit, QScrollArea
)

# ---------------- Globals & Paths ----------------
APP_TITLE = "Playwright Assistant — Recorder • Scripts • Visual Flows • Schedules (PyQt6)"
default_dir = os.path.join(os.getcwd(), "recordings")
flows_dir = os.path.join(os.getcwd(), "flows")
for d in (default_dir, flows_dir):
    os.makedirs(d, exist_ok=True)

# --------------- Helpers -----------------
def inject_headless_flag(code: str) -> str:
    code = re.sub(r"headless\s*=\s*[^,\)]+,?\s*", "", code)
    code = re.sub(r"(launch\()", r"\1headless=HEADLESS, ", code)
    return code

def now_str() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# --------------- Visual Flow Model ---------------
ACTION_VALUES = (
    "open_url",
    "click_selector",
    "type_text",
    "wait_seconds",
    "screenshot",
    "close_browser",
)

@dataclass
class FlowStep:
    action: str
    selector: str = ""
    value: str = ""
    seconds: float = 0.0

# --------------- Scheduler ----------------
@dataclass
class ScheduledJob:
    job_id: int
    kind: str                 # "script" | "flow"
    path: str                 # file path to .py or .json
    browser: str
    headless: bool
    close_browser: bool
    next_run: datetime.datetime
    every_seconds: Optional[int] = None  # None = one-off

class Scheduler:
    def __init__(self, on_fire_callback):
        self.on_fire = on_fire_callback
        self.jobs: Dict[int, ScheduledJob] = {}
        self._counter = 0

    def next_id(self) -> int:
        self._counter += 1
        return self._counter

    def add(self, job: ScheduledJob) -> None:
        self.jobs[job.job_id] = job

    def remove(self, job_id: int) -> None:
        self.jobs.pop(job_id, None)

    def all(self) -> List[ScheduledJob]:
        return list(self.jobs.values())

    def tick(self) -> None:
        now = datetime.datetime.now()
        due = [j for j in self.jobs.values() if j.next_run <= now]
        for j in due:
            self.on_fire(j)
            if j.every_seconds:
                j.next_run = now + datetime.timedelta(seconds=j.every_seconds)
            else:
                self.remove(j.job_id)

# --------------- QThread for Flow Runner ---------------
class FlowRunner(QThread):
    log_signal = pyqtSignal(str)
    done_signal = pyqtSignal()

    def __init__(self, steps: List[FlowStep], cfg: Dict[str, Any], save_dir: str):
        super().__init__()
        self.steps = steps
        self.cfg = cfg
        self.save_dir = save_dir

    def log(self, msg: str):
        self.log_signal.emit(f"{msg}")

    def run(self):
        try:
            from playwright.sync_api import sync_playwright
        except Exception as e:
            self.log(f"Playwright not available: {e}")
            self.done_signal.emit()
            return

        self.log("Flow starting…")
        try:
            with sync_playwright() as p:
                browser_type = getattr(p, self.cfg.get("browser", "chromium"))
                browser = browser_type.launch(headless=bool(self.cfg.get("headless", False)))
                context = browser.new_context()
                page = context.new_page()

                per_step = float(self.cfg.get("per_step_wait", 0.0))

                for i, step in enumerate(self.steps, start=1):
                    self.log(f"[Step {i}] {step.action}")
                    if step.action == "open_url":
                        if not step.selector:
                            raise ValueError("open_url requires URL in 'selector'")
                        page.goto(step.selector)
                    elif step.action == "click_selector":
                        page.click(step.selector)
                    elif step.action == "type_text":
                        page.fill(step.selector, step.value)
                    elif step.action == "wait_seconds":
                        time.sleep(float(step.seconds))
                    elif step.action == "screenshot":
                        fname = f"snap_{datetime.datetime.now().strftime('%H%M%S_%f')}.png"
                        path = os.path.join(self.save_dir, fname)
                        page.screenshot(path=path, full_page=True)
                        self.log(f"Saved screenshot: {fname}")
                    elif step.action == "close_browser":
                        try:
                            browser.close()
                        except Exception:
                            pass
                        if i < len(self.steps):
                            browser = browser_type.launch(headless=bool(self.cfg.get("headless", False)))
                            context = browser.new_context()
                            page = context.new_page()
                    else:
                        raise ValueError(f"Unknown action: {step.action}")

                    if per_step > 0:
                        time.sleep(per_step)

                try:
                    browser.close()
                except Exception:
                    pass

            self.log("Flow complete.")
        except Exception as e:
            self.log(f"Flow error: {e}")

        self.done_signal.emit()

# --------------- Step Row Widget ----------------
class StepRow(QWidget):
    move_up = pyqtSignal(QWidget)
    move_down = pyqtSignal(QWidget)
    delete_me = pyqtSignal(QWidget)

    def __init__(self, preset: Optional[FlowStep] = None):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0,0,0,0)
        layout.setSpacing(8)

        self.action = QComboBox()
        self.action.addItems(ACTION_VALUES)
        self.action.setCurrentText(preset.action if preset else "open_url")

        self.selector = QLineEdit(preset.selector if preset else "")
        self.selector.setPlaceholderText("selector / URL")

        self.value = QLineEdit(preset.value if preset else "")
        self.value.setPlaceholderText("text value")

        self.seconds = QDoubleSpinBox()
        self.seconds.setDecimals(2)
        self.seconds.setRange(0.0, 10_000.0)
        self.seconds.setValue(float(preset.seconds) if preset else 0.0)
        self.seconds.setSuffix(" s")
        self.seconds.setFixedWidth(110)

        up_btn = QPushButton("↑")
        down_btn = QPushButton("↓")
        del_btn = QPushButton("✕")
        up_btn.setFixedWidth(32); down_btn.setFixedWidth(32); del_btn.setFixedWidth(32)

        up_btn.clicked.connect(lambda: self.move_up.emit(self))
        down_btn.clicked.connect(lambda: self.move_down.emit(self))
        del_btn.clicked.connect(lambda: self.delete_me.emit(self))

        layout.addWidget(self.action)
        layout.addWidget(self.selector, 2)
        layout.addWidget(self.value, 2)
        layout.addWidget(self.seconds)
        layout.addWidget(up_btn)
        layout.addWidget(down_btn)
        layout.addWidget(del_btn)

    def to_step(self) -> FlowStep:
        return FlowStep(
            action=self.action.currentText().strip(),
            selector=self.selector.text().strip(),
            value=self.value.text().strip(),
            seconds=float(self.seconds.value())
        )

# --------------- Record Tab ----------------
class RecordTab(QWidget):
    def __init__(self, main):
        super().__init__()
        self.main = main
        self.record_proc: Optional[subprocess.Popen] = None
        self.out_file: Optional[str] = None

        root = QVBoxLayout(self)
        grid = QGridLayout()
        row = 0

        grid.addWidget(QLabel("Browser"), row, 0)
        self.browser = QComboBox(); self.browser.addItems(["chromium", "firefox", "webkit"])
        grid.addWidget(self.browser, row, 1)

        grid.addWidget(QLabel("Start URL"), row, 2)
        self.url = QLineEdit(); self.url.setPlaceholderText("optional")
        grid.addWidget(self.url, row, 3)

        grid.addWidget(QLabel("Script Name"), row, 4)
        self.name = QLineEdit(); self.name.setPlaceholderText("optional .py")
        grid.addWidget(self.name, row, 5)
        row += 1

        btn_row = QHBoxLayout()
        self.record_btn = QPushButton("▶ Record")
        self.stop_btn = QPushButton("■ Stop")
        btn_row.addWidget(self.record_btn)
        btn_row.addWidget(self.stop_btn)

        root.addLayout(grid)
        root.addLayout(btn_row)

        self.record_btn.clicked.connect(self.start_recording)
        self.stop_btn.clicked.connect(self.stop_recording)

    def start_recording(self):
        try:
            subprocess.run([sys.executable, "-m", "playwright", "install"], check=True)
        except subprocess.CalledProcessError as e:
            QMessageBox.critical(self, "Error", f"Playwright install failed:\n{e}")
            return

        out_dir = self.main.save_dir()
        os.makedirs(out_dir, exist_ok=True)
        browser = self.browser.currentText()
        url = self.url.text().strip()
        name = self.name.text().strip() or datetime.datetime.now().strftime(f"record_{browser}_%Y%m%d_%H%M%S")
        if not name.endswith(".py"):
            name += ".py"
        self.out_file = os.path.join(out_dir, name)

        cmd = [sys.executable, "-m", "playwright", "codegen",
               "--target", "python", "--browser", browser, "--output", self.out_file]
        if url:
            cmd.append(url)
        try:
            self.record_proc = subprocess.Popen(cmd)
            self.main.log(f"Recording started: {name}")
            QMessageBox.information(self, "Recording", f"Browser opened; recording to {name}")
        except FileNotFoundError:
            QMessageBox.critical(self, "Error", "Install Playwright CLI via pip (pip install playwright)")

    def stop_recording(self):
        if not self.record_proc:
            return
        self.record_proc.terminate()
        self.record_proc.wait()
        try:
            with open(self.out_file, 'r+', encoding="utf-8") as f:
                code = f.read()
                header = (
                    "import os\n"
                    "HEADLESS=os.getenv('HEADLESS','0')=='1'\n"
                    "from playwright.sync_api import sync_playwright\n\n"
                )
                processed = inject_headless_flag(code)
                f.seek(0); f.write(header + processed); f.truncate()
            self.main.log(f"Recording saved: {self.out_file}")
            QMessageBox.information(self, "Saved", f"Saved to {os.path.basename(self.out_file)}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Post-process failed:\n{e}")
        finally:
            self.record_proc = None

# --------------- Scripts Tab ----------------
class ScriptsTab(QWidget):
    def __init__(self, main):
        super().__init__()
        self.main = main

        root = QVBoxLayout(self)
        top = QHBoxLayout()
        refresh_btn = QPushButton("⟳ Refresh")
        top.addWidget(QLabel("Scripts in Save Dir (.py)"))
        top.addStretch(1)
        top.addWidget(refresh_btn)

        self.listw = QListWidget()
        opts = QHBoxLayout()
        self.browser = QComboBox(); self.browser.addItems(["chromium","firefox","webkit"])
        self.headless = QCheckBox("Headless")
        self.close_browser = QCheckBox("Close Browser"); self.close_browser.setChecked(True)
        play_btn = QPushButton("▶ Play")

        opts.addWidget(QLabel("Browser"))
        opts.addWidget(self.browser)
        opts.addWidget(self.headless)
        opts.addWidget(self.close_browser)
        opts.addStretch(1)
        opts.addWidget(play_btn)

        root.addLayout(top)
        root.addWidget(self.listw, 1)
        root.addLayout(opts)

        refresh_btn.clicked.connect(self.refresh)
        play_btn.clicked.connect(self.play)
        self.refresh()

    def refresh(self):
        self.listw.clear()
        base = self.main.save_dir()
        if not os.path.isdir(base):
            return
        for fname in sorted(os.listdir(base)):
            if fname.endswith(".py"):
                self.listw.addItem(QListWidgetItem(fname))
        self.main.log("Script list refreshed.")

    def play(self):
        item = self.listw.currentItem()
        if not item:
            QMessageBox.warning(self, "No selection", "Select a script to play.")
            return
        script = os.path.join(self.main.save_dir(), item.text())
        try:
            with open(script, 'r', encoding="utf-8") as f:
                code = f.read()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to read script:\n{e}")
            return

        if not self.close_browser.isChecked():
            code = re.sub(r"^[ \t]*browser\.close\(\)[ \t]*\n", "", code, flags=re.M)
            temp = os.path.join(self.main.save_dir(), f"temp_{os.path.basename(script)}")
            with open(temp, 'w', encoding="utf-8") as tf:
                tf.write(code)
            script_to_run = temp
        else:
            script_to_run = script

        env = os.environ.copy()
        env['PLAYWRIGHT_BROWSER'] = self.browser.currentText()
        env['HEADLESS'] = '1' if self.headless.isChecked() else '0'
        subprocess.Popen([sys.executable, script_to_run], env=env)
        self.main.log(f"Playing script: {os.path.basename(script_to_run)}")
        QMessageBox.information(self, "Playing", os.path.basename(script_to_run))

# --------------- Visual Flow Tab ----------------
class FlowTab(QWidget):
    def __init__(self, main):
        super().__init__()
        self.main = main
        self.runner: Optional[FlowRunner] = None

        root = QVBoxLayout(self)

        # top row
        top = QHBoxLayout()
        self.flow_name = QLineEdit(); self.flow_name.setPlaceholderText("Flow name (optional)")
        self.browser = QComboBox(); self.browser.addItems(["chromium", "firefox", "webkit"])
        self.headless = QCheckBox("Headless")
        self.per_step = QDoubleSpinBox(); self.per_step.setDecimals(2); self.per_step.setRange(0.0, 10000.0); self.per_step.setValue(0.0); self.per_step.setSuffix(" s")
        top.addWidget(QLabel("Name")); top.addWidget(self.flow_name, 1)
        top.addWidget(QLabel("Browser")); top.addWidget(self.browser)
        top.addWidget(self.headless)
        top.addWidget(QLabel("Per-step wait")); top.addWidget(self.per_step)

        # steps area (scroll)
        self.steps_holder = QWidget()
        self.steps_layout = QVBoxLayout(self.steps_holder)
        self.steps_layout.setContentsMargins(0,0,0,0)
        self.steps_layout.setSpacing(6)
        self.steps_layout.addStretch(1)  # stretch at end

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.steps_holder)

        # controls
        ctrl = QHBoxLayout()
        add_btn = QPushButton("+ Add Step")
        save_btn = QPushButton("💾 Save Flow")
        load_btn = QPushButton("📂 Load Flow")
        run_btn = QPushButton("▶ Run Flow")
        ctrl.addWidget(add_btn)
        ctrl.addWidget(save_btn)
        ctrl.addWidget(load_btn)
        ctrl.addStretch(1)
        ctrl.addWidget(run_btn)

        root.addLayout(top)
        root.addWidget(scroll, 1)
        root.addLayout(ctrl)

        add_btn.clicked.connect(self.add_step)
        save_btn.clicked.connect(self.save_flow)
        load_btn.clicked.connect(self.load_flow_dialog)
        run_btn.clicked.connect(self.run_flow)

    def add_step(self, preset: Optional[FlowStep] = None):
        row = StepRow(preset)
        row.move_up.connect(self.move_step_up)
        row.move_down.connect(self.move_step_down)
        row.delete_me.connect(self.delete_step)
        # insert above the stretch (i.e., before last item)
        self.steps_layout.insertWidget(self.steps_layout.count()-1, row)

    def move_step_up(self, row: StepRow):
        idx = self.steps_layout.indexOf(row)
        if idx > 0:
            self.steps_layout.removeWidget(row)
            self.steps_layout.insertWidget(idx-1, row)

    def move_step_down(self, row: StepRow):
        idx = self.steps_layout.indexOf(row)
        # count includes the final stretch; last usable index is count-2
        if 0 <= idx < self.steps_layout.count()-2:
            self.steps_layout.removeWidget(row)
            self.steps_layout.insertWidget(idx+1, row)

    def delete_step(self, row: StepRow):
        row.setParent(None)
        row.deleteLater()

    def collect_flow(self) -> List[FlowStep]:
        steps: List[FlowStep] = []
        for i in range(self.steps_layout.count()-1):  # skip stretch
            w = self.steps_layout.itemAt(i).widget()
            if isinstance(w, StepRow):
                steps.append(w.to_step())
        return steps

    def save_flow(self):
        steps = self.collect_flow()
        if not steps:
            QMessageBox.warning(self, "Empty", "Add at least one step.")
            return
        payload = {
            "name": self.flow_name.text().strip() or datetime.datetime.now().strftime("flow_%Y%m%d_%H%M%S"),
            "browser": self.browser.currentText(),
            "headless": self.headless.isChecked(),
            "per_step_wait": float(self.per_step.value()),
            "steps": [s.__dict__ for s in steps],
        }
        name = payload["name"] + ".json"
        path = os.path.join(flows_dir, name)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
            self.main.log(f"Flow saved: {path}")
            QMessageBox.information(self, "Saved", f"Flow saved to flows/{name}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save flow:\n{e}")

    def load_flow_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load Flow", flows_dir, "Flow JSON (*.json)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.flow_name.setText(data.get("name",""))
            self.browser.setCurrentText(data.get("browser","chromium"))
            self.headless.setChecked(bool(data.get("headless", False)))
            self.per_step.setValue(float(data.get("per_step_wait", 0.0)))
            # clear current steps
            for i in reversed(range(self.steps_layout.count()-1)):
                w = self.steps_layout.itemAt(i).widget()
                if w: w.setParent(None); w.deleteLater()
            for s in data.get("steps", []):
                self.add_step(FlowStep(**s))
            self.main.log(f"Flow loaded: {os.path.basename(path)}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load flow:\n{e}")

    def run_flow(self):
        steps = self.collect_flow()
        if not steps:
            QMessageBox.warning(self, "Empty", "Add at least one step.")
            return
        cfg = dict(
            browser=self.browser.currentText(),
            headless=self.headless.isChecked(),
            per_step_wait=float(self.per_step.value()),
        )
        self.runner = FlowRunner(steps, cfg, self.main.save_dir())
        self.runner.log_signal.connect(lambda m: self.main.log(m))
        self.runner.done_signal.connect(lambda: self.main.log("Flow thread finished."))
        self.runner.start()
        self.main.log("Flow thread started.")

# --------------- Schedule Tab ----------------
class ScheduleTab(QWidget):
    def __init__(self, main):
        super().__init__()
        self.main = main

        root = QVBoxLayout(self)

        # Row 1: kind + file
        r1 = QHBoxLayout()
        self.kind = QComboBox(); self.kind.addItems(["script","flow"])
        self.path = QLineEdit(); self.path.setPlaceholderText("Select a .py (script) or .json (flow)")
        browse = QPushButton("Browse…")
        r1.addWidget(QLabel("Kind")); r1.addWidget(self.kind)
        r1.addWidget(self.path, 1); r1.addWidget(browse)

        # Row 2: options
        r2 = QHBoxLayout()
        self.browser = QComboBox(); self.browser.addItems(["chromium","firefox","webkit"])
        self.headless = QCheckBox("Headless")
        self.close_browser = QCheckBox("Close Browser"); self.close_browser.setChecked(True)
        r2.addWidget(QLabel("Browser")); r2.addWidget(self.browser)
        r2.addWidget(self.headless); r2.addWidget(self.close_browser)
        r2.addStretch(1)

        # Row 3: time + repeat
        r3 = QHBoxLayout()
        self.date = QDate.currentDate()
        self.time = QTime.currentTime()
        self.date_edit = QLineEdit(); self.date_edit.setPlaceholderText("YYYY-MM-DD")
        self.time_edit = QLineEdit(); self.time_edit.setPlaceholderText("HH:MM (24h)")
        self.repeat_min = QSpinBox(); self.repeat_min.setRange(0, 100000); self.repeat_min.setValue(0); self.repeat_min.setSuffix(" min")
        r3.addWidget(QLabel("Run at"))
        r3.addWidget(self.date_edit)
        r3.addWidget(self.time_edit)
        r3.addWidget(QLabel("Repeat every"))
        r3.addWidget(self.repeat_min)
        r3.addStretch(1)

        # Row 4: actions + list
        r4 = QHBoxLayout()
        add_btn = QPushButton("+ Add Schedule")
        refresh_btn = QPushButton("⟳ Refresh List")
        r4.addWidget(add_btn)
        r4.addWidget(refresh_btn)
        r4.addStretch(1)

        self.list_box = QPlainTextEdit()
        self.list_box.setReadOnly(True)
        self.list_box.setMinimumHeight(160)

        root.addLayout(r1)
        root.addLayout(r2)
        root.addLayout(r3)
        root.addLayout(r4)
        root.addWidget(self.list_box, 1)

        browse.clicked.connect(self.browse_target)
        add_btn.clicked.connect(self.add_schedule)
        refresh_btn.clicked.connect(self.refresh_list)
        self.refresh_list()

    def browse_target(self):
        if self.kind.currentText() == "flow":
            path, _ = QFileDialog.getOpenFileName(self, "Select Flow", flows_dir, "Flow JSON (*.json)")
        else:
            path, _ = QFileDialog.getOpenFileName(self, "Select Script", self.main.save_dir(), "Python script (*.py)")
        if path:
            self.path.setText(path)

    def parse_datetime(self) -> Optional[datetime.datetime]:
        d = self.date_edit.text().strip()
        t = self.time_edit.text().strip()
        if not d or not t:
            return None
        try:
            yy, mm, dd = [int(x) for x in d.split("-")]
            hh, mi = [int(x) for x in t.split(":")]
            return datetime.datetime(yy, mm, dd, hh, mi)
        except Exception:
            return None

    def add_schedule(self):
        target = self.path.text().strip()
        if not os.path.exists(target):
            QMessageBox.warning(self, "Invalid", "Pick a valid target file.")
            return
        run_at = self.parse_datetime() or (datetime.datetime.now() + datetime.timedelta(seconds=10))
        every_minutes = int(self.repeat_min.value())
        every_seconds = every_minutes * 60 if every_minutes > 0 else None

        job = ScheduledJob(
            job_id=self.main.scheduler.next_id(),
            kind=self.kind.currentText(),
            path=target,
            browser=self.browser.currentText(),
            headless=self.headless.isChecked(),
            close_browser=self.close_browser.isChecked(),
            next_run=run_at,
            every_seconds=every_seconds,
        )
        self.main.scheduler.add(job)
        self.refresh_list()
        self.main.log(f"Scheduled {job.kind} for {run_at} (repeat: {every_seconds or 'no'})")

    def refresh_list(self):
        jobs = sorted(self.main.scheduler.all(), key=lambda j: j.job_id)
        if not jobs:
            self.list_box.setPlainText("(no schedules)")
            return
        lines = []
        for j in jobs:
            rep = f"every {j.every_seconds//60} min" if j.every_seconds else "once"
            lines.append(f"[#{j.job_id}] {j.kind.upper()} :: {os.path.basename(j.path)} | {j.browser} | headless={j.headless} | next={j.next_run} | {rep}")
        self.list_box.setPlainText("\n".join(lines))

# --------------- Main Window ----------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(1100, 720)

        # Scheduler
        self.scheduler = Scheduler(self._run_scheduled_job)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.scheduler.tick)
        self.timer.start(1000)  # 1s

        # Top bar (save dir)
        topw = QWidget()
        top = QHBoxLayout(topw)
        self.dir_line = QLineEdit(default_dir)
        browse = QPushButton("Browse…")
        top.addWidget(QLabel("Save Dir"))
        top.addWidget(self.dir_line, 1)
        top.addWidget(browse)
        browse.clicked.connect(self._browse_dir)

        # Tabs
        self.tabs = QTabWidget()
        self.tab_record = RecordTab(self)
        self.tab_scripts = ScriptsTab(self)
        self.tab_flow = FlowTab(self)
        self.tab_sched = ScheduleTab(self)
        self.tabs.addTab(self.tab_record, "🎬 Record")
        self.tabs.addTab(self.tab_scripts, "📜 Scripts")
        self.tabs.addTab(self.tab_flow, "🧩 Visual Flow")
        self.tabs.addTab(self.tab_sched, "⏰ Schedules")

        # Log
        self.log_box = QPlainTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setMinimumHeight(140)

        # Layout
        central = QWidget()
        v = QVBoxLayout(central)
        v.addWidget(topw)
        v.addWidget(self.tabs, 1)
        v.addWidget(self.log_box)
        self.setCentralWidget(central)

        # Style
        self._apply_dark_theme()

    def _apply_dark_theme(self):
        # lightweight dark palette via stylesheet
        self.setStyleSheet("""
            QWidget { background-color: #14161b; color: #eaeaea; }
            QLineEdit, QPlainTextEdit, QListWidget, QComboBox, QSpinBox, QDoubleSpinBox {
                background-color: #20232a; color: #f0f0f0; border: 1px solid #2e323a; padding: 3px;
            }
            QPushButton { background-color: #2b2f36; border: 1px solid #3a3f49; padding: 6px; }
            QPushButton:hover { background-color: #353b45; }
            QTabWidget::pane { border: 1px solid #2e323a; }
            QTabBar::tab { background: #1b1e24; padding: 8px 12px; border: 1px solid #2e323a; }
            QTabBar::tab:selected { background: #232830; }
            QLabel { color: #e0e0e0; }
        """)

    def save_dir(self) -> str:
        return self.dir_line.text().strip() or default_dir

    def _browse_dir(self):
        path = QFileDialog.getExistingDirectory(self, "Select Save Directory", self.save_dir())
        if path:
            self.dir_line.setText(path)
            self.log("Save dir changed.")
            self.tab_scripts.refresh()

    # -------- Logging ----------
    def log(self, msg: str):
        self.log_box.appendPlainText(f"[{now_str()}] {msg}")
        self.log_box.moveCursor(self.log_box.textCursor().End)

    # -------- Scheduler hook ----------
    def _run_scheduled_job(self, job: ScheduledJob):
        self.log(f"Running scheduled job #{job.job_id}…")
        if job.kind == "script":
            env = os.environ.copy()
            env['PLAYWRIGHT_BROWSER'] = job.browser
            env['HEADLESS'] = '1' if job.headless else '0'
            target = job.path
            if not job.close_browser:
                try:
                    with open(job.path, "r", encoding="utf-8") as f:
                        code = f.read()
                    code = re.sub(r"^[ \t]*browser\.close\(\)[ \t]*\n", "", code, flags=re.M)
                    temp = os.path.join(self.save_dir(), f"temp_{os.path.basename(job.path)}")
                    with open(temp, "w", encoding="utf-8") as tf:
                        tf.write(code)
                    target = temp
                except Exception as e:
                    self.log(f"Temp edit failed: {e}")
            subprocess.Popen([sys.executable, target], env=env)
        else:  # flow
            try:
                with open(job.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                steps = [FlowStep(**s) for s in data.get("steps", [])]
                cfg = dict(
                    browser=job.browser or data.get("browser","chromium"),
                    headless=job.headless if job.headless is not None else data.get("headless", False),
                    per_step_wait=float(data.get("per_step_wait", 0.0)),
                )
                runner = FlowRunner(steps, cfg, self.save_dir())
                runner.log_signal.connect(lambda m: self.log(m))
                runner.done_signal.connect(lambda: self.log(f"Scheduled flow finished (#{job.job_id})."))
                runner.start()
            except Exception as e:
                self.log(f"Scheduled flow failed: {e}")

# --------------- main ----------------
def main():
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
