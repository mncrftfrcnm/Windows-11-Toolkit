# Issue 001: Hover effect regression in taskbar

## Summary
The latest hover effect refactor removed per-button QGraphicsEffect usage. However, the `TaskbarWindow._apply_hover_effects` method is not guarded against the "none" option. When the hover effect combo defaults to `focusfade`, the dimming animation never clears and pinned icons stay partially transparent.

## Environment
- Windows 11 23H2
- Python 3.11.7 (venv)
- PySide6 6.6.1
- Repository commit: `main` (22c1f1a)

## Steps to reproduce
1. Launch `python taskbar.py`.
2. Open the Settings dialog and change Hover effect to `focusfade`.
3. Hover over any pinned app icon, then move the cursor away.

## Expected behavior
The hovered icon should return to the base opacity once the cursor leaves the button.

## Actual behavior
Icons remain faded until another hover event fires, giving the appearance of stuck focus.

## Additional context
`_reset_hover_effects` is not invoked when `_hover_fx` is set to `focusfade` because the guard clause only checks for `self._hover_fx != "none"`. A manual call to `_reset_hover_effects()` inside `leaveEvent` resolves the issue.
