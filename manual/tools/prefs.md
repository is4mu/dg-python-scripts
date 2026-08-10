# Preferences

- **Package**: `prefs`
- **Menu**: DGpy → Preferences…
- **Flame**: 2025+

## What it does

View and configure paths, Runtime, ffmpeg / ffprobe, GitHub token, and more on one screen.
**Open Manual…** in the window opens the Public user manual index in your browser.

## How to use

1. Open **DGpy → Preferences…** and review status
2. If ffmpeg is missing, use **Install ffmpeg…** under Tools
3. For Private `-dev`, save a GitHub token (Contents: Read)
4. Open the manual via **Open Manual…**

## Notes

- prefs.json lives at `…/flame/dgpy/prefs.json` (outside Python scan paths)
- ffmpeg resolution order: environment variables → `dgpy_runtimes/bin` → PATH

## Related

- [Manual index](../README.md)
- Package name in Script Manager: `prefs`
