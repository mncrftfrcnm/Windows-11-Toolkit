# Issue 003: Win Tiler gesture listener hangs on wake-from-sleep

## Summary
After the system resumes from sleep, `win_tiler.py` stops reacting to mouse gestures. The overlay remains visible but no tiling actions fire until the script is restarted.

## Environment
- Windows 11 Insider Canary (build 26058)
- Python 3.10.12
- pynput 1.7.6
- pywin32 306

## Steps to reproduce
1. Run `python win_tiler.py` and ensure gesture recognition is active.
2. Put the PC to sleep using Start > Power > Sleep.
3. Wake the machine and attempt a configured corner gesture.

## Expected behavior
Gestures should continue to be recognized after waking from sleep without needing a restart.

## Actual behavior
The global mouse listener never receives events post-resume. The console logs stop updating despite the overlay still running.

## Additional context
Dumping thread stacks reveals the `pynput.mouse.Listener` thread waiting on `user32.GetMessage`. Calling `Listener.stop()` and reinitializing the listener when a `WM_POWERBROADCAST` resume event is detected should restore functionality.
