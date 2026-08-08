# MatAnyone Runtime

- **Package**: `matanyone_runtime`
- **Menu**: DGpy → Preferences… → MatAnyone（Runtime Setup / SAM2 Setup / Remove）
- **Flame**: 2025+

## できること

MatAnyone2 と SAM2 を `dgpy_runtimes/matanyone` にセットアップ・削除します（重いデータは python 走査の外）。

## 使い方

1. **Preferences…** を開く
2. **Runtime Setup…** で venv / リポ / 重みを導入
3. **SAM2 Setup…** で tiny チェックポイント等を導入
4. READY 表示を確認してから MatAnyone を使う

## 注意

- Script Manager では `auto_install=false`（手動 Install）
- Setup はネットワークとディスク容量を多く使う
- Remove All は確認のうえ実行

## 関連

- [Manual index](../README.md)
- Script Manager でのパッケージ名: `matanyone_runtime`

