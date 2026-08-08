# DGpy2（Flame / Flare 2025+）

Autodesk Flame / Flare 向けの Python ツールセットです。  
インストール後の追加・更新は、Flame 内の **DG Script Manager** から行います。

リポジトリ: https://github.com/is4mu/dg-python-scripts

## 初回インストール

1. [Releases](https://github.com/is4mu/dg-python-scripts/releases) から最新の **`dgpy-bootstrap-*.zip`** をダウンロードする  
   （Release がまだ無い場合は、このリポジトリの `dgpy/` フォルダを次の表の場所へコピーしてもよい）
2. 解凍すると `dgpy/` が出る
3. **どちらか一方**に置く（ここが Install root になる）

| 用途 | パス |
|------|------|
| 個人（macOS） | `~/Library/Preferences/Autodesk/flame/python/dgpy` |
| 個人（Linux） | `~/flame/python/dgpy` |
| スタジオ共有 | `/opt/Autodesk/shared/python/dgpy`（書き込み権限が必要） |

4. Flame で **Python → Rescan Python Hooks**（または Flame を再起動）
5. メインメニュー **`DGpy2` → `DG Script Manager`**
6. **Refresh** → 必要に応じて **Update All** / 個別 Install

以降のパッケージ追加・更新・アンインストールは Manager 経由で行ってください。  
`dgpy/` の外にある他の Python スクリプトには影響しません。

移行期間中は、旧ツールが **`DGpy`**、本ツールが **`DGpy2`** として共存できます。

## Script Manager でできること

- 利用可能なパッケージの一覧表示（Install / Update / Up to date）
- **Update All** / 選択して Install・Update
- アプリの **Uninstall**（Core / Manager はアンインストール不可）
- 各パッケージの概要・変更履歴の表示
- チャンネル切替（`latest` / `stable` ※運用に応じて）

書き込みできない Install root や、ユーザ用と共有用で `dgpy` が二重にある場合は起動時に警告します。

## 含まれる主な機能

Media Panel などのコンテキストメニュー（接頭辞 **`DG2:`**）およびメインメニュー **`DGpy2`** から利用できます。

例: Color / Rename / Batch（Open・Save Setup・Render）/ Clip・Audio・Sequence 向けユーティリティ / Script Manager / List Plugins / Clear Archive TOCs など。

一覧と版は Manager の Refresh 結果が正です。

## トラブルシューティング

| 症状 | 確認すること |
|------|----------------|
| メニューが出ない | `dgpy` の配置パス、Rescan Python Hooks、Flame 2025 以上か |
| Install / Update が失敗する | ネットワーク、GitHub へのアクセス、Install root の書き込み権限 |
| `sha256 mismatch` | 一度 Refresh してから再実行。続く場合は Flame を再起動してから再試行 |
| 旧 `DG:` とメニューが並ぶ | 移行期間の想定どおり。旧を外すと `DG2:` だけになる |

## ライセンス・サポート

社内／個人利用向けの配布物です。問題があればリポジトリの Issues（利用可能な場合）または配布元の担当者へ連絡してください。

## User manual

- [Manual (index)](manual/README.md)
- [Getting started](manual/getting-started.md)

In Flame: **DGpy → Preferences…** → **Open Manual…**.
