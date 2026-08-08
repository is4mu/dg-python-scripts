# DGpy（Flame / Flare 2025+）

Autodesk Flame / Flare 向けの Python ツールセットです。  
インストール後の追加・更新は、Flame 内の **DG Script Manager** から行います。

**無料（[MIT License](LICENSE)）** — Copyright © 2026 Isamu Oue（個人）。  
開発継続の支援は任意です → **[GitHub Sponsors](https://github.com/sponsors/is4mu)**

リポジトリ: https://github.com/is4mu/dg-python-scripts

## 初回インストール

1. [Releases](https://github.com/is4mu/dg-python-scripts/releases) から最新の **`dgpy-bootstrap-*.zip`** をダウンロードする  
   （現行: [v0.3.12](https://github.com/is4mu/dg-python-scripts/releases/tag/v0.3.12)）
2. 解凍すると `dgpy/` が出る
3. **どちらか一方**に置く（ここが Install root になる）

| 用途 | パス |
|------|------|
| 個人（macOS） | `~/Library/Preferences/Autodesk/flame/python/dgpy` |
| 個人（Linux） | `~/flame/python/dgpy` |
| スタジオ共有 | `/opt/Autodesk/shared/python/dgpy`（書き込み権限が必要） |

4. Flame で **Python → Rescan Python Hooks**（または Flame を再起動）
5. メインメニュー **DGpy → DG Script Manager**
6. **Refresh** → 必要に応じて **Update All** / 個別 Install

以降のパッケージ追加・更新・アンインストールは Manager 経由で行ってください。  
`dgpy/` の外にある他の Python スクリプトには影響しません。

## メニュー

| 場所 | 名前 |
|------|------|
| メインメニュー | **DGpy**（Script Manager / Preferences / List Plugins / Clear Archive TOCs など） |
| Media Panel ほか | **DG:** 接頭辞（Color / Rename / Batch / Audio / Clip / Segment / Sequence / Export など） |

## Script Manager

| 操作 | 用途 |
|------|------|
| **Refresh** | 一覧を GitHub と照合 |
| **Update All** | 更新があるパッケージをまとめて入れる |
| **Install / Update Selected** | 表で選んだ行だけ |
| **Uninstall Selected** | 選んだアプリを外す（Core / Manager は不可） |
| **Advanced** | チャンネル切替、Verify / Repair、ログ |

書き込みできない Install root や、ユーザ用と共有用で `dgpy` が二重にある場合は起動時に警告します。

## 含まれる主な機能

- **DG:** Color / Rename / Batch / Audio / Clip / Segment / Sequence / Sequence Render / Export
- **DGpy:** Script Manager / Preferences（マニュアル・ffmpeg）/ List Plugins / Clear Archive TOCs
- MatAnyone（Clip メニュー。Runtime は Preferences から。初回は手動 Install）

一覧と版の正は Manager の Refresh 結果です。ユーザー向け詳細は [Manual](manual/README.md)。

## トラブルシューティング

| 症状 | 確認すること |
|------|----------------|
| メニューが出ない | `dgpy` の配置パス、Rescan Python Hooks、Flame 2025 以上か |
| Install / Update が失敗する | ネットワーク、GitHub へのアクセス、Install root の書き込み権限 |
| `sha256 mismatch` | Advanced → Verify / Repair。続く場合は Flame 再起動後に再試行 |
| Core / Manager 更新後に不安定 | Flame を再起動してから再操作 |

## ライセンス（詳細）

DGpy（本リポジトリの配布コード）は **[MIT License](LICENSE)** です。

**MatAnyone** および関連モデル・ランタイムなど、同梱／別途取得する第三者コンポーネントには **それぞれ別のライセンス・利用条件** が適用されます。商用利用の可否は各条件を確認してください（確認中の項目あり）。

問題報告はリポジトリの Issues（利用可能な場合）へお願いします。

## User manual

- [Manual (index)](manual/README.md)
- [Getting started](manual/getting-started.md)

In Flame: **DGpy → Preferences…** → **Open Manual…**.
