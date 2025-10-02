# Windows 11 Toolkit

A grab bag of desktop utilities and experiments aimed at making Windows 10/11 a more creative and productive environment.  The scripts range from GPU-assisted wallpaper generation to custom overlays, automation helpers, and power-user taskbar tweaks.

## Getting started

1. Install **Python 3.10+** on Windows (some scripts work on 3.9 but the toolkit targets 3.10 for consistency).
2. Create and activate a virtual environment:
   ```powershell
   python -m venv .venv
   .venv\Scripts\activate
   ```
3. Install the dependencies that match the tool(s) you want to run (see the sections below).
4. Launch the desired script with `python <script_name>.py` from an activated virtual environment.

> Many tools require GPU-accelerated libraries (DirectML, PyTorch) or Windows-only APIs (pywin32).  Make sure you install the prerequisites before running them.

## Tools at a glance

| Script | What it does |
| --- | --- |
| `ai_wallpaper_generator.py` | Local DirectML text-to-image wallpaper studio with PyQt6 GUI and status logging. |
| `audio_reactor.py` | Audio-reactive overlay that highlights windows and ambient effects based on system audio. |
| `browser_automator.py` | Playwright assistant for recording, editing, and scheduling browser automation flows. |
| `custom_cursor.py` | Designer for animated Windows cursor themes with AI-assisted texture generation hooks. |
| `deep_research.py` | Research helper that searches the web, summarizes sources, and answers questions with transformers. |
| `powershell_helper.py` | CLI agent that uses a language model to draft and optionally execute PowerShell scripts. |
| `prompt_engineer.py` | Prompt-building GUI with presets, combiners, and export utilities for generative models. |
| `retro_overlay.py` | Click-through overlay with cinematic/retro/HUD visual presets for multiple monitors. |
| `spotlight.py` | Win+Space searchable launcher that indexes Start Menu shortcuts with fuzzy search and icons. |
| `taskbar.py` | Highly customizable taskbar replacement with blur/opacity styles, widgets, and pinned apps. |
| `win_tiler.py` | Gesture-driven window tiler/resizer that listens for mouse strokes and snaps windows into layouts. |

## Detailed tool descriptions

### `ai_wallpaper_generator.py`
- **Description:** PyQt6 desktop app for generating 4K wallpapers locally using Stable Diffusion Turbo or other DirectML-compatible checkpoints.  Supports automatic model setup, prompt editing, seeds, batch time-of-day sets, and live status updates.
- **Key dependencies:** `PyQt6`, `diffusers`, `torch`, `torch-directml` (for AMD/Intel GPU acceleration).
- **Optional extras:** Local Stable Diffusion Turbo weights (place the model path in the GUI or allow auto-setup).
- **Run:** `python ai_wallpaper_generator.py`

### `audio_reactor.py`
- **Description:** Always-on-top, click-through overlay per monitor that reacts to system audio by pulsing colors and outlining active windows via WASAPI loopback capture.
- **Key dependencies:** `PyQt6`, `numpy`, `soundcard` (preferred) or `sounddevice` as a fallback.
- **Run:** `python audio_reactor.py`

### `browser_automator.py`
- **Description:** Multi-tab PyQt6 assistant for Playwright automation.  Record new flows, assemble visual drag-and-drop steps, configure schedules, and replay scripts with headless toggles and logging.
- **Key dependencies:** `PyQt6`, `playwright` (Python package and CLI via `pip install playwright` followed by `playwright install`).
- **Optional extras:** `ffmpeg` on PATH for video captures of browser runs.
- **Run:** `python browser_automator.py`

### `custom_cursor.py`
- **Description:** Cursor authoring studio with live animation preview, randomization tools, and one-click install/apply for Windows cursor schemes.  Supports manual drawing and optional AI texture generation hooks.
- **Key dependencies:** `PyQt6`, `Pillow`.
- **Optional extras:** Stable Diffusion Turbo via DirectML if you wire in AI texture generation helpers.
- **Run:** `python custom_cursor.py`

### `deep_research.py`
- **Description:** Automates deep-dive research by searching DuckDuckGo, fetching articles, summarizing them, and answering questions with transformer pipelines.
- **Key dependencies:** `requests`, `requests-cache`, `duckduckgo-search`, `newspaper3k`, `transformers`, `torch`.
- **Run:** `python deep_research.py`

### `powershell_helper.py`
- **Description:** Command-line agent that uses a Hugging Face causal language model to draft PowerShell scripts, review them with the user, and optionally execute them locally.
- **Key dependencies:** `transformers`, `torch` (with a model such as `gpt2`).
- **Run:** `python powershell_helper.py`

### `prompt_engineer.py`
- **Description:** Prompt engineering workbench with preset templates, combiners, weighting helpers, and export options geared toward generative AI workflows.
- **Key dependencies:** `PyQt6`.
- **Run:** `python prompt_engineer.py`

### `retro_overlay.py`
- **Description:** Always-on-top overlay generator with curated presets (Filmic, CRT, HUD, Vaporwave, etc.), color controls, and per-monitor deployment.
- **Key dependencies:** `PyQt6`.
- **Run:** `python retro_overlay.py`

### `spotlight.py`
- **Description:** Lightweight Spotlight-style launcher triggered by `Win+Space`, indexing Start Menu shortcuts, caching icons, and using fuzzy search to launch apps.
- **Key dependencies:** `keyboard`, `rapidfuzz`, `Pillow`, `pywin32` (via `pypiwin32`), standard-library `tkinter`.
- **Run:** `python spotlight.py`

### `taskbar.py`
- **Description:** Replacement taskbar with customizable layouts, blur/acrylic effects, widget zones (clock, system stats), and pinned app management for Windows 11.
- **Key dependencies:** `PySide6`, `psutil` (for CPU/memory widgets), `pywin32` for Windows API access.
- **Run:** `python taskbar.py`

### `win_tiler.py`
- **Description:** Window management utility that listens for mouse gestures and hot corners to tile, resize, and move windows into predefined slots.
- **Key dependencies:** `PyQt6`, `numpy`, `pynput`, `pywin32` (`pywin32`/`pypiwin32`).
- **Run:** `python win_tiler.py`

## Troubleshooting

- If the GUI fails to launch, verify that the matching Qt binding (PyQt6 or PySide6) is installed in the current environment.
- For GPU-heavy tools ensure the correct DirectML or CUDA wheels of PyTorch are installed and that your GPU drivers are up to date.
- Tools that interact with system-wide hooks (keyboard, WASAPI, window management) may need to be run with administrator privileges.

## License

This repository is licensed under the terms specified in `LICENSE`.
