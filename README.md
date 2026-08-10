# DGpy (Flame / Flare 2025+)

Python tools for Autodesk Flame / Flare.  
After the first install, add and update packages from **DG Script Manager** inside Flame.

**Free ([MIT License](LICENSE))** — Copyright © 2026 Isamu Oue (personal).  
Optional support for ongoing development → **[GitHub Sponsors](https://github.com/sponsors/is4mu)**

Repository: https://github.com/is4mu/dg-python-scripts

## First-time install

1. Download the latest **`dgpy-bootstrap-*.zip`** from [Releases](https://github.com/is4mu/dg-python-scripts/releases)  
   (current: [v0.3.12](https://github.com/is4mu/dg-python-scripts/releases/tag/v0.3.12))
2. Unzip so you get a `dgpy/` folder
3. Place it in **one** of these locations (this becomes the install root)

| Use | Path |
|-----|------|
| Personal (macOS) | `~/Library/Preferences/Autodesk/flame/python/dgpy` |
| Personal (Linux) | `~/flame/python/dgpy` |
| Studio shared | `/opt/Autodesk/shared/python/dgpy` (write access required) |

4. In Flame: **Python → Rescan Python Hooks** (or restart Flame)
5. Main menu **DGpy → DG Script Manager**
6. **Refresh**, then **Update All** or install packages individually

Use the Manager for later installs, updates, and uninstalls.  
Other Python scripts outside `dgpy/` are left alone.

## Menus

| Where | Name |
|-------|------|
| Main menu | **DGpy** (Script Manager / Preferences / List Plugins / Clear Archive TOCs, …) |
| Media Panel and elsewhere | **DG:** prefix (Color / Rename / Batch / Audio / Clip / Segment / Sequence / Export, …) |

## Script Manager

| Action | Purpose |
|--------|---------|
| **Refresh** | Compare the package list with GitHub |
| **Update All** | Install every package that needs an update |
| **Install / Update Selected** | Selected table rows only |
| **Uninstall Selected** | Remove selected apps (Core / Manager cannot be removed) |
| **Donate…** | Optional donation (GitHub Sponsors); DGpy stays free |
| **Advanced** | Channel, Verify / Repair, log |

Startup warns if the install root is not writable, or if both user and shared `dgpy` folders exist.

## Main features

- **DG:** Color / Rename / Batch / Audio / Clip / Segment / Sequence / Sequence Render / Export
- **DGpy:** Script Manager / Preferences (manual, ffmpeg) / List Plugins / Clear Archive TOCs

The Manager Refresh view is the source of truth for package versions. Details: [Manual](manual/README.md).

## Troubleshooting

| Symptom | Check |
|---------|-------|
| Menus missing | `dgpy` path, Rescan Python Hooks, Flame 2025+ |
| Install / Update fails | Network, GitHub access, write permission on the install root |
| `sha256 mismatch` | Advanced → Verify / Repair; retry after restarting Flame |
| Unstable after Core / Manager update | Restart Flame, then try again |

## License (details)

DGpy distribution code in this repository is under the **[MIT License](LICENSE)**.

Report issues on the repository Issues page when available.

## User manual

- [Manual (index)](manual/README.md)
- [Getting started](manual/getting-started.md)

In Flame: **DGpy → Preferences…** → **Open Manual…**.
