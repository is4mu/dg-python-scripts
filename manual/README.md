# DGpy Manual

Autodesk **Flame / Flare 2025+** 向けツールセット **DGpy** のユーザー向けマニュアルです。

リポジトリ（配布）: [is4mu/dg-python-scripts](https://github.com/is4mu/dg-python-scripts)

## はじめに

- [Getting started](getting-started.md) — インストール、Script Manager、更新

## ツール一覧

各ツールの詳細ページは順次追加します。現状は Script Manager の概要・Changelog、および Flame 内のメニューを参照してください。

| ツール | Package | 主なメニュー |
|--------|---------|----------------|
| Script Manager | `manager` | DGpy → DG Script Manager |
| Preferences | `prefs` | DGpy → Preferences… |
| Manual（本ページ） | `prefs` | DGpy → Manual… |
| Rename | `rename` | Media Panel 等 → DG: Rename |
| Color | `color` | Media Panel 等 → DG: Colour |
| MatAnyone | `matanyone` | Media Panel → DG: Clip → MatAnyone… |
| MatAnyone Runtime | `matanyone_runtime` | Preferences → Runtime / SAM2 Setup |
| DG Export | `dg_export` | Media Panel → DG: Export |
| List Plugins | `list_plugins` | DGpy → List Plugins |
| Clear Archive TOCs | `archive_toc` | DGpy → Clear Archive TOCs |
| Create Batch from Clip | `create_batch_from_clip` | DG: Clip → Create Batch Group |
| Resize All Clips | `batch_resize_clips` | DG: Clip → Resize All Clips |
| Comp CG | `comp_cg` | DG: Clip → Comp CG Clips |
| Go To Frame | `goto_frame` | DG: Clip → Go To… |
| Set Start Frame to 1 | `set_start_frame_1` | DG: Clip |
| Open Batch | `open_batch` | DG: Batch |
| Save Batch Setup | `save_batch_setup` | DG: Batch |
| Render Batch | `render_batch` | DG: Batch |
| Move to Origin | `batch_move_to_origin` | Batch |
| Sequence Render | `render_sequence` | DG: Sequence |
| Cutdata | `cutdata` | DG: Sequence |
| Delete All Markers | `delete_all_markers` | DG: Sequence |
| Keep Video Tracks | `keep_video_tracks` | DG: Sequence |
| Cutout Edge Frame | `cutout_edge_frame` | DG: Sequence |
| Audio Lock / Cleanup | `audio_lock` / `audio_cleanup` | DG: Audio |
| Action Tidy | `action_tidy` | DG: Segment |

一覧・版の正は Flame 内 **DG Script Manager** の Refresh 結果です。

## 雛形

新規ツールページを書くとき: [`_template.md`](_template.md)
