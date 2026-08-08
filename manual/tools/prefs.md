# Preferences / Manual

- **Package**: `prefs`
- **Menu**: DGpy → Manual… / Preferences…
- **Flame**: 2025+

## できること

パス・Runtime・ffmpeg / ffprobe・GitHub token などを一画面で確認・設定します。
**Manual…** は Public 上のユーザーマニュアル目次をブラウザで開きます。

## 使い方

1. **DGpy → Preferences…** で状態を確認する
2. MatAnyone が未準備なら **Runtime Setup…** / **SAM2 Setup…**
3. ffmpeg が無ければ Tools の **Install ffmpeg…**
4. Private `-dev` 利用時は GitHub token を保存（Contents: Read）
5. マニュアルは **DGpy → Manual…** または **Open Manual…**

## 注意

- prefs.json は `…/flame/dgpy/prefs.json`（python 走査の外）
- ffmpeg 解決順: 環境変数 → `dgpy_runtimes/bin` → PATH

## 関連

- [Manual index](../README.md)
- Script Manager でのパッケージ名: `prefs`

