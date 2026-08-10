# Getting started

## Requirements

- Autodesk **Flame / Flare 2025** or later (PySide6)
- Network access (when fetching from GitHub via Script Manager)

## First-time installation

1. Download the latest **`dgpy-bootstrap-*.zip`** from [Releases](https://github.com/is4mu/dg-python-scripts/releases)  
   (If unavailable, you can copy the repository’s `dgpy/` folder to one of the paths in the table below)
2. Place the extracted **`dgpy/`** folder in one of these locations:

| Purpose | Path |
|---------|------|
| Personal (macOS) | `~/Library/Preferences/Autodesk/flame/python/dgpy` |
| Personal (Linux) | `~/flame/python/dgpy` |
| Studio shared | `/opt/Autodesk/shared/python/dgpy` (write access required) |

3. In Flame, run **Python → Rescan Python Hooks** (or restart Flame)
4. Open the main menu **DGpy → DG Script Manager**
5. Click **Refresh** → **Update All** or individual **Install** as needed

## Day-to-day updates

- **DGpy → DG Script Manager** → Refresh → Update / Update All  
- After Core / Manager self-updates, **restart Flame** is recommended  

## Preferences and ffmpeg

- **DGpy → Preferences…** — Check and configure paths, ffmpeg / ffprobe, and Install  
- If ffmpeg is not on the OS, you can install it into `dgpy_runtimes/bin` from Preferences (DGpy prefers that copy)

## Opening the manual

- **DGpy → Preferences…** → **Open Manual…** — Table of contents for this manual (GitHub)

## Troubleshooting

| Symptom | Check |
|---------|-------|
| Menus do not appear | `dgpy` placement, Rescan, Flame 2025+ |
| Install / Update fails | Network, GitHub, write permissions. For Private `-dev`, set GitHub token in Preferences |
