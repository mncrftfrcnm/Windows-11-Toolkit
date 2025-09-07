import os
import json
import subprocess
from pathlib import Path
import tkinter as tk
from tkinter import font
import keyboard
from rapidfuzz import process
from PIL import Image, ImageTk
import win32gui, win32con

APP_DIRS = [
    Path(os.getenv('PROGRAMDATA', '')) / 'Microsoft' / 'Windows' / 'Start Menu' / 'Programs',
    Path(os.getenv('APPDATA', '')) / 'Microsoft' / 'Windows' / 'Start Menu' / 'Programs'
]
CACHE_FILE = Path(os.getenv('LOCALAPPDATA', '')) / 'spotlight_cache.json'
MAX_RESULTS = 10
HOTKEY = 'win+space'
ICON_SIZE = 24
FADE_IN_STEP = 0.05
SLIDE_STEP = 20
SLIDE_DELAY = 10  # ms

# Cache

def load_cache():
    try:
        return json.loads(CACHE_FILE.read_text()) if CACHE_FILE.exists() else {}
    except:
        return {}


def save_cache(cache):
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(cache))


def scan_apps():
    apps = {}
    for base in APP_DIRS:
        for root, _, files in os.walk(base):
            for fname in files:
                if fname.lower().endswith(('.lnk', '.exe')):
                    name = os.path.splitext(fname)[0]
                    apps[name] = str(Path(root) / fname)
    return apps


def get_icon(path):
    try:
        large, small = win32gui.ExtractIconEx(path, 0)
        hicon = small[0] if small else large[0] if large else None
        if not hicon:
            return None
        hdc = win32gui.CreateCompatibleDC(0)
        hbm = win32gui.CreateCompatibleBitmap(hdc, ICON_SIZE, ICON_SIZE)
        h_old = win32gui.SelectObject(hdc, hbm)
        win32gui.DrawIconEx(hdc, 0, 0, hicon, ICON_SIZE, ICON_SIZE, 0, 0, win32con.DI_NORMAL)
        win32gui.SelectObject(hdc, h_old)
        bmpinfo = win32gui.GetObject(hbm)
        bmpstr = win32gui.GetBitmapBits(hbm, True)
        image = Image.frombuffer('RGBA', (bmpinfo.bmWidth, bmpinfo.bmHeight), bmpstr, 'raw', 'BGRA', 0, 1)
        image = image.resize((ICON_SIZE, ICON_SIZE), Image.ANTIALIAS)
        photo = ImageTk.PhotoImage(image)
        win32gui.DestroyIcon(hicon)
        return photo
    except:
        return None


class Spotlight(tk.Toplevel):
    def __init__(self, master, apps, cache):
        super().__init__(master)
        self.apps, self.cache = apps, cache
        self.names = sorted(apps.keys())
        self.results = []
        self.selection = 0
        self.icons = {}
        self.frames = []

        # Window appearance
        self.overrideredirect(True)
        self.attributes('-topmost', True)
        self.configure(bg='#222222')
        self.wm_attributes('-transparentcolor', '#000000')

        # Fonts and widgets
        self.entry_font = font.Font(family='Segoe UI', size=20)
        self.list_font = font.Font(family='Segoe UI', size=14)

        self.entry = tk.Entry(self, font=self.entry_font, bd=0, fg='white', bg='#333333', insertbackground='white', relief='flat')
        self.entry.pack(padx=20, pady=20, fill='x')

        # Result frame
        self.result_frame = tk.Frame(self, bg='#222222')
        self.result_frame.pack(padx=20, fill='both')

        # Bindings
        self.entry.bind('<KeyRelease>', self.on_type)
        self.entry.bind('<Down>', self.on_down)
        self.entry.bind('<Up>', self.on_up)
        self.entry.bind('<Return>', self.on_launch)
        self.bind('<Escape>', lambda e: self.destroy())
        self.bind('<FocusIn>', lambda e: self.entry.focus_set())
        self.bind_all('<Button-1>', self.on_click_outside)

        # Animation targets
        self.target_alpha = 0.95
        self.current_alpha = 0.0
        self.attributes('-alpha', self.current_alpha)

        # Initial placement above center
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        width = 600
        self.final_height = 120
        self.final_x = (sw - width) // 2
        self.final_y = (sh - self.final_height) // 4
        self.geometry(f'{width}x{self.final_height}+{self.final_x}+{self.final_y - 50}')

        # Show and animate
        self.lift()
        self.focus_force()
        self.grab_set()
        self.entry.focus_set()
        self.update_list([])
        self.animate_in()

    def animate_in(self):
        # Fade in
        if self.current_alpha < self.target_alpha:
            self.current_alpha = min(self.target_alpha, self.current_alpha + FADE_IN_STEP)
            self.attributes('-alpha', self.current_alpha)

        # Slide down
        geom = self.geometry().split('+')
        size = geom[0]
        x = int(geom[1])
        y = int(geom[2])
        if y < self.final_y:
            y = min(self.final_y, y + SLIDE_STEP)
            self.geometry(f'{size}+{x}+{y}')

        if self.current_alpha < self.target_alpha or y < self.final_y:
            self.after(SLIDE_DELAY, self.animate_in)

    def center(self):
        # Not used since animation handles positioning
        pass

    def on_click_outside(self, event):
        if event.widget not in self.winfo_children() and event.widget is not self.entry:
            self.destroy()

    def on_type(self, event=None):
        if event and event.keysym in ('Up', 'Down', 'Return', 'Escape'):
            return
        q = self.entry.get()
        items = [n for n, *_ in process.extract(q, self.names, limit=MAX_RESULTS)] if q else []
        self.update_list(items)

    def update_list(self, items):
        # Clear existing
        for widget in self.result_frame.winfo_children():
            widget.destroy()
        self.frames.clear()

        self.results = items
        self.selection = 0

        for idx, name in enumerate(items):
            frame = tk.Frame(self.result_frame, bg='#222222')
            frame.pack(fill='x', pady=2)
            self.frames.append(frame)

            icon = self.icons.get(name) or get_icon(self.apps[name])
            self.icons[name] = icon

            lbl_icon = tk.Label(frame, image=icon, bg='#222222')
            lbl_icon.pack(side='left', padx=(0, 10))
            lbl_icon.bind('<Button-1>', lambda e, i=idx: self.on_click(i))

            lbl_text = tk.Label(frame, text=name, anchor='w', font=self.list_font, bg='#222222', fg='white')
            lbl_text.pack(fill='x', expand=True)
            lbl_text.bind('<Button-1>', lambda e, i=idx: self.on_click(i))

            frame.bind('<Enter>', lambda e, i=idx: self.on_hover(i))
            frame.bind('<Button-1>', lambda e, i=idx: self.on_click(i))

        # Resize based on results
        new_height = 120 + len(items) * 44
        width = 600
        self.final_y = (self.winfo_screenheight() - new_height) // 4
        self.geometry(f'{width}x{new_height}+{self.final_x}+{max(self.final_y, self.winfo_y())}')
        self.update_highlight()

    def on_down(self, event=None):
        if self.selection < len(self.results) - 1:
            self.selection += 1
            self.update_highlight()
        return 'break'

    def on_up(self, event=None):
        if self.selection > 0:
            self.selection -= 1
            self.update_highlight()
        return 'break'

    def on_hover(self, idx):
        self.selection = idx
        self.update_highlight()

    def update_highlight(self):
        for idx, frame in enumerate(self.frames):
            bg = '#444444' if idx == self.selection else '#222222'
            for widget in frame.winfo_children():
                widget.configure(bg=bg)
            frame.configure(bg=bg)

    def on_click(self, idx):
        self.selection = idx
        self.update_highlight()
        self.on_launch()

    def on_launch(self, event=None):
        if not self.results:
            return 'break'
        name = self.results[self.selection]
        path = self.apps.get(name)
        if path:
            try:
                os.startfile(path)
            except Exception:
                subprocess.Popen(['cmd', '/c', 'start', '""', path], shell=True)
            self.cache[name] = self.cache.get(name, 0) + 1
            save_cache(self.cache)
        self.destroy()
        return 'break'


if __name__ == '__main__':
    root = tk.Tk()
    root.withdraw()
    apps = scan_apps()
    cache = load_cache()

    def show_spotlight():
        Spotlight(root, apps, cache)

    keyboard.add_hotkey(HOTKEY, lambda: root.after(0, show_spotlight))
    root.mainloop()
