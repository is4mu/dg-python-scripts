# DG Script Manager

- **Package**: `manager`
- **Menu**: DGpy → DG Script Manager
- **Flame**: 2025+

## What it does

Lists DGpy packages inside Flame and handles Install / Update / Uninstall, Verify / Repair, and channel switching.
Day-to-day updates should go through this Manager.

## How to use

1. Open **DGpy → DG Script Manager**
2. **Everyday**: **Refresh**, then **Update All** when needed
3. **Selection**: select rows → **Install / Update Selected** or **Uninstall Selected**
4. **Advanced** tab: Channel, **Verify…** / **Repair**, technical details, log
5. After Core / Manager self-updates, **restart Flame** is recommended

Optional: **Support DGpy…** in the header opens GitHub Sponsors (donations are optional; DGpy is free).

## Notes

- Core / Manager cannot be uninstalled (deleting `dgpy/` entirely is the last resort)
- channel=`dev` is for Private `-dev`. Normal users use `latest` (Public)
- Non-writable install roots or duplicate layouts trigger warnings at startup

## Related

- [Manual index](../README.md)
- Package name in Script Manager: `manager`
