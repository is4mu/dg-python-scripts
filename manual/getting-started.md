# Getting started

## 必要環境

- Autodesk **Flame / Flare 2025** 以降（PySide6）
- ネットワーク（Script Manager で GitHub から取得する場合）

## 初回インストール

1. [Releases](https://github.com/is4mu/dg-python-scripts/releases) から最新の **`dgpy-bootstrap-*.zip`** を入手する  
   （無い場合はリポジトリの `dgpy/` を次の表の場所へコピーしてもよい）
2. 解凍した **`dgpy/`** を次のいずれかへ置く

| 用途 | パス |
|------|------|
| 個人（macOS） | `~/Library/Preferences/Autodesk/flame/python/dgpy` |
| 個人（Linux） | `~/flame/python/dgpy` |
| スタジオ共有 | `/opt/Autodesk/shared/python/dgpy`（書き込み権限が必要） |

3. Flame で **Python → Rescan Python Hooks**（または Flame 再起動）
4. メインメニュー **DGpy → DG Script Manager**
5. **Refresh** → 必要に応じて **Update All** / 個別 Install

## 日常の更新

- **DGpy → DG Script Manager** → Refresh → Update / Update All  
- Core / Manager 自己更新後は **Flame 再起動**を推奨  

## Preferences・ffmpeg

- **DGpy → Preferences…** — パス、MatAnyone Runtime / SAM2、ffmpeg / ffprobe の確認と Install  
- ffmpeg は OS に無くても Preferences から `dgpy_runtimes/bin` へ入れられます（DGpy が優先して使います）

## マニュアルを開く

- **DGpy → Manual…** — このマニュアルの目次（GitHub）  
- Preferences 内の **Open Manual…** でも同じページを開けます  

## トラブルシュート

| 症状 | 確認 |
|------|------|
| メニューが出ない | `dgpy` の配置、Rescan、Flame 2025+ |
| Install / Update 失敗 | ネットワーク、GitHub、書き込み権限。Private `-dev` 利用時は Preferences の GitHub token |
| MatAnyone が動かない | Preferences で Runtime / SAM2 READY、ffmpeg、ログ `dgpy.log` |
