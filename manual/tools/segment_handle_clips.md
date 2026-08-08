# Consolidate Handles (Probe)

- **Package**: `segment_handle_clips`
- **Menu**: Media Panel / Timeline → **DG: Segment** → Consolidate Handles (Probe)…
- **Flame**: 2025+

## できること

Primary track 上のセグメントについて、現状の IN/OUT と、Handles 込みの **カット予定範囲** を一覧表示します。クリップは作りません。

## 使い方

1. セグメント、または Clip/Sequence、または Reel を選択
2. **DG: Segment → Consolidate Handles (Probe)…**
3. Handles（既定 5、前後同一）を確認 → OK
4. 結果ダイアログで一覧を確認（Copy 可）

## 注意

- Folder / Library は対象外
- Gap は対象外
- 可変 TW が読めないセグメントは skip 行（理由付き）
- 本線の無劣化クリップ生成は停止中（probe で数値確認後に再開予定）

## 関連

- [Manual index](../README.md)
- Script Manager: `segment_handle_clips`
