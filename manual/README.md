# DGpy Manual

Autodesk **Flame / Flare 2025+** 向けツールセット **DGpy** のユーザー向けマニュアルです。

リポジトリ（配布）: [is4mu/dg-python-scripts](https://github.com/is4mu/dg-python-scripts)

## はじめに

- [Getting started](getting-started.md) — インストール、Script Manager、更新

## ツール一覧

| ツール | Package | 主なメニュー |
|--------|---------|----------------|
| [Script Manager](tools/manager.md) | `manager` | DGpy → DG Script Manager |
| [Preferences](tools/prefs.md) | `prefs` | DGpy → Preferences… |
| Manual（本ページ） | `prefs` | DGpy → Manual… |
| [Rename](tools/rename.md) | `rename` | Media Panel 等 → DG: Rename |
| [Color](tools/color.md) | `color` | Media Panel 等 → DG: Color |
| [MatAnyone](tools/matanyone.md) | `matanyone` | Media Panel → DG: Clip → MatAnyone… |
| [MatAnyone Runtime](tools/matanyone_runtime.md) | `matanyone_runtime` | Preferences → Runtime / SAM2 Setup |
| [DG Export](tools/dg_export.md) | `dg_export` | Media Panel → DG: Export |
| [List Plugins](tools/list_plugins.md) | `list_plugins` | DGpy → List Plugins |
| [Clear Archive TOCs](tools/archive_toc.md) | `archive_toc` | DGpy → Clear Archive TOCs |
| [Create Batch from Clip](tools/create_batch_from_clip.md) | `create_batch_from_clip` | DG: Clip → Create Batch Group |
| [Resize All Clips](tools/batch_resize_clips.md) | `batch_resize_clips` | DG: Clip → Resize All Clips |
| [Comp CG](tools/comp_cg.md) | `comp_cg` | DG: Clip → Comp CG Clips |
| [Go To Frame](tools/goto_frame.md) | `goto_frame` | DG: Clip → Go To… |
| [Set Start Frame to 1](tools/set_start_frame_1.md) | `set_start_frame_1` | DG: Clip → Set Start Frame to 1 |
| [Open Batch](tools/open_batch.md) | `open_batch` | DG: Batch → Open |
| [Save Batch Setup](tools/save_batch_setup.md) | `save_batch_setup` | DG: Batch → Save Setup |
| [Render Batch](tools/render_batch.md) | `render_batch` | DG: Batch → Render |
| [Move to Origin](tools/batch_move_to_origin.md) | `batch_move_to_origin` | Batch → DG: Move to Origin |
| [Sequence Render](tools/render_sequence.md) | `render_sequence` | DG: Sequence Render |
| [Cutdata](tools/cutdata.md) | `cutdata` | DG: Sequence → Cutdata |
| [Delete All Markers](tools/delete_all_markers.md) | `delete_all_markers` | DG: Sequence → Delete All Markers |
| [Keep Video Tracks](tools/keep_video_tracks.md) | `keep_video_tracks` | DG: Sequence → Keep Video Tracks |
| [Cutout Edge Frame](tools/cutout_edge_frame.md) | `cutout_edge_frame` | DG: Sequence → Cutout First/Last Frame |
| [Audio Lock](tools/audio_lock.md) | `audio_lock` | DG: Audio → Lock / Unlock |
| [Audio Cleanup](tools/audio_cleanup.md) | `audio_cleanup` | DG: Audio → Only / Delete… |
| [Action Tidy](tools/action_tidy.md) | `action_tidy` | DG: Segment |
| [DG Core](tools/core.md) | `core` | （共通基盤・ユーザーメニューなし） |

一覧・版の正は Flame 内 **DG Script Manager** の Refresh 結果です。

## 雛形

新規ツールページを書くとき: [`_template.md`](_template.md)
