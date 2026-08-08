# MatAnyone Runtime

- **Package**: `matanyone_runtime`
- **Menu**: DGpy → Preferences… → MatAnyone (Runtime Setup / SAM2 Setup / Remove)
- **Flame**: 2025+

## What it does

Installs and removes MatAnyone2 and SAM2 under `dgpy_runtimes/matanyone` (heavy data stays outside Python scan paths).

## How to use

1. Open **Preferences…**
2. **Runtime Setup…** — install venv, repo, weights
3. **SAM2 Setup…** — install tiny checkpoint, etc.
4. Confirm READY status before using MatAnyone

## Notes

- `auto_install=false` in Script Manager (manual Install)
- Setup uses significant network and disk space
- Run Remove All only after confirmation

## Related

- [Manual index](../README.md)
- Package name in Script Manager: `matanyone_runtime`
