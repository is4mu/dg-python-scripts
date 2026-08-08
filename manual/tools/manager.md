# DG Script Manager

- **Package**: `manager`
- **Menu**: DGpy → DG Script Manager
- **Flame**: 2025+

## できること

Flame 内で DGpy パッケージの一覧・Install / Update / Uninstall、Verify / Repair、チャンネル切替を行います。
日常の更新はこの Manager 経由が正です。

## 使い方

1. **DGpy → DG Script Manager** を開く
2. **Refresh** で Remote の manifest を取得する
3. 行を選んで **Install** / **Update**、または **Update All**
4. 問題があるときは **Verify…** / **Repair**（sha256 不一致の再取得）
5. Core / Manager 自己更新後は **Flame 再起動**を推奨

## 注意

- Core / Manager は Uninstall 不可（`dgpy/` ごと削除が最終手段）
- channel=`dev` は Private `-dev` 用。通常ユーザーは `latest`（Public）
- 書き込み不可の Install root や二重配置は起動時に警告される

## 関連

- [Manual index](../README.md)
- Script Manager でのパッケージ名: `manager`

