# MatAnyone

- **Package**: `matanyone`
- **Menu**: Media Panel → **DG: Clip** → MatAnyone…
- **Flame**: 2025+

## できること

クリップを書き出し、SAM2 でマスクを編集し、MatAnyone2 でマットを推論して Flame に取り込みます。

## 使い方

1. Preferences で **Runtime READY** と **SAM2 READY**、必要なら **ffmpeg** を用意
2. クリップを選択 → **MatAnyone…**
3. Export 後、マスク UI で点／ペイント → **OK**
4. Infer 完了後、Alpha（および設定により Foreground）を確認

## 注意

- macOS ではマスク UI が非モーダル。Linux は従来どおり
- Infer は時間がかかることがある。進捗ウィンドウで Cancel 可
- Runtime / SAM2 は Preferences から Setup

## 関連

- [Manual index](../README.md)
- Script Manager でのパッケージ名: `matanyone`

