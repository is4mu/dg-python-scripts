# Consolidate Handles

- **Package**: `segment_handle_clips`
- **Menu**: Media Panel / Timeline → **DG: Segment** → Consolidate Handles…
- **Flame**: 2025+

## What it does

Probes Primary-track segments for keep ranges (including Handles and Timewarp where readable), merges by source path, creates consolidated clips on the **Sources** reel, then **Replace Media** back onto the sequence. One Results window drives Create and Replace.

## How to use

1. Select a segment, clip/sequence, or reel
2. **DG: Segment → Consolidate Handles…**
3. Set Handles (default 5) and optional merge gap → OK
4. Review the probe report → **Create** on Sources
5. When ready → **Replace Media** on the same Results window

## Notes

- Folder / Library and Gaps are excluded
- Segments with unreadable variable TW are skipped (with reason)
- Replace uses the **Replace Media** shortcut (not Smart Replace)
- Core / Manager update is unrelated; restart Flame only if menus look stale after a Manager update

## Related

- [Manual index](../README.md)
- Script Manager package id: `segment_handle_clips`
