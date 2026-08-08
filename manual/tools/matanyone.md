# MatAnyone

- **Package**: `matanyone`
- **Menu**: Media Panel → **DG: Clip** → MatAnyone…
- **Flame**: 2025+

## What it does

Exports a clip, edits masks with SAM2, runs MatAnyone2 matting inference, and imports results into Flame.

## How to use

1. In Preferences, ensure **Runtime READY**, **SAM2 READY**, and **ffmpeg** if needed
2. Select a clip → **MatAnyone…**
3. After export, use points / paint in the mask UI → **OK**
4. After inference completes, review Alpha (and Foreground per settings)

## Notes

- On macOS the mask UI is non-modal; on Linux it behaves as before
- Inference can take time. Cancel from the progress window if needed
- Set up Runtime / SAM2 from Preferences

## Related

- [Manual index](../README.md)
- Package name in Script Manager: `matanyone`
