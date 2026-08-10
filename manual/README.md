# DGpy Manual

User manual for **DGpy**, a toolset for Autodesk **Flame / Flare 2025+**.

Repository (distribution): [is4mu/dg-python-scripts](https://github.com/is4mu/dg-python-scripts)

## Getting started

- [Getting started](getting-started.md) — Installation, Script Manager, updates

## Tool index

Ordered roughly like the Flame menu structure. The authoritative list and versions come from **DG Script Manager** after **Refresh**.

### DGpy (main menu)

| Tool | Package | Menu |
|------|---------|------|
| [Script Manager](tools/manager.md) | `manager` | DGpy → DG Script Manager |
| [Preferences](tools/prefs.md) | `prefs` | DGpy → Preferences… (Open Manual…) |
| [List Plugins](tools/list_plugins.md) | `list_plugins` | DGpy → List Plugins |
| [Clear Archive TOCs](tools/archive_toc.md) | `archive_toc` | DGpy → Clear Archive TOCs |

### Media Panel — DG: Color / Rename

| Tool | Package | Menu |
|------|---------|------|
| [Color](tools/color.md) | `color` | DG: Color → color name |
| [Rename](tools/rename.md) | `rename` | DG: Rename (root) |

### Media Panel — DG: Batch

| Tool | Package | Menu |
|------|---------|------|
| [Open Batch](tools/open_batch.md) | `open_batch` | DG: Batch → Open |
| [Save Batch Setup](tools/save_batch_setup.md) | `save_batch_setup` | DG: Batch → Save Setup |
| [Render Batch](tools/render_batch.md) | `render_batch` | DG: Batch → Render |
| [Move to Origin](tools/batch_move_to_origin.md) | `batch_move_to_origin` | DG: Move to Origin (Batch context) |

### Media Panel — DG: Audio

| Tool | Package | Menu |
|------|---------|------|
| [Audio Lock](tools/audio_lock.md) | `audio_lock` | DG: Audio → Lock / Unlock |
| [Audio Cleanup](tools/audio_cleanup.md) | `audio_cleanup` | DG: Audio → Only… / Delete… |

### Media Panel — DG: Clip

| Tool | Package | Menu |
|------|---------|------|
| [Create Batch from Clip](tools/create_batch_from_clip.md) | `create_batch_from_clip` | DG: Clip → Create Batch Group |
| [Resize All Clips](tools/batch_resize_clips.md) | `batch_resize_clips` | DG: Clip → Resize All Clips |
| [Comp CG](tools/comp_cg.md) | `comp_cg` | DG: Clip → Comp CG Clips |
| [Go To Frame](tools/goto_frame.md) | `goto_frame` | DG: Clip → Go To → … |
| [Set Start Frame to 1](tools/set_start_frame_1.md) | `set_start_frame_1` | DG: Clip → Set Start Frame to 1 |

### Media Panel — DG: Segment

| Tool | Package | Menu |
|------|---------|------|
| [Action Tidy](tools/action_tidy.md) | `action_tidy` | DG: Segment → Clean Up / Fit / Strip… |
| [Consolidate Handles](tools/segment_handle_clips.md) | `segment_handle_clips` | DG: Segment → Consolidate Handles… |

### Media Panel — DG: Sequence / Render / Export

| Tool | Package | Menu |
|------|---------|------|
| [Cutdata](tools/cutdata.md) | `cutdata` | DG: Sequence → Add / Create Cutdata… |
| [Delete All Markers](tools/delete_all_markers.md) | `delete_all_markers` | DG: Sequence → Delete All Markers |
| [Cutout Edge Frame](tools/cutout_edge_frame.md) | `cutout_edge_frame` | DG: Sequence → Cutout First / Last Frame |
| [Keep Video Tracks](tools/keep_video_tracks.md) | `keep_video_tracks` | DG: Sequence → Only Primary / Top… |
| [Sequence Render](tools/render_sequence.md) | `render_sequence` | DG: Sequence Render (root) |
| [DG Export](tools/dg_export.md) | `dg_export` | DG: Export → preset |

### Foundation

| Tool | Package | Menu |
|------|---------|------|
| [DG Core](tools/core.md) | `core` | (shared library — no user menu) |

## Template

When writing a new tool page: [`_template.md`](_template.md)
