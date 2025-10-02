# Issue 002: DirectML initialization failure in wallpaper generator

## Summary
`ai_wallpaper_generator.py` fails to initialize the DirectML pipeline when a user selects a CUDA-only checkpoint. The UI surfaces a generic "model load failed" message without explaining that DirectML weights are required, leading to confusion.

## Environment
- Windows 11 22H2
- Python 3.10.13
- torch-directml 1.13.1
- diffusers 0.24.0

## Steps to reproduce
1. Launch `python ai_wallpaper_generator.py`.
2. Browse to a Stable Diffusion 1.5 checkpoint exported for CUDA (safetensors).
3. Attempt to generate a wallpaper.

## Expected behavior
The app should validate the model backend before attempting to load it and provide actionable feedback if the checkpoint is incompatible.

## Actual behavior
Model loading fails with an uncaught exception from `diffusers`, and the GUI only shows a generic error toast.

## Proposed fix
Add a validation step to inspect the `config.json` for `torch_dtype`/`device` compatibility or allow the user to convert the checkpoint by triggering `diffusers.pipelines.pipeline_utils.load_single_file_checkpoint` with `torch_directml`. Also surface a dialog that lists compatible model formats.
