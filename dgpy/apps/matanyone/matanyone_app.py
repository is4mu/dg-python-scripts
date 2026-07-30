"""MatAnyone app entry: dialog → job."""

from __future__ import annotations

from pathlib import Path

import matanyone_dialog as dialog
import matanyone_job as job
import matanyone_selection as selection

__version__ = "0.1.0"


def run_from_selection(selection_items) -> None:
    import dgpy_gui
    import dgpy_log

    logger = dgpy_log.setup()
    clips = selection.direct_clips(selection_items)
    if not clips:
        dgpy_gui.warning(None, "MatAnyone", "Select a Clip or Sequence.")
        return

    clip = clips[0]
    ignored = len(clips) - 1
    if ignored:
        logger.info("MatAnyone: using first clip only; ignoring %s", ignored)

    warn = job.gpu_vram_warning()
    if warn and not dgpy_gui.confirm(None, "MatAnyone", warn):
        return

    opts_ui = dialog.open_dialog(clip, ignored_count=ignored)
    if opts_ui is None:
        return

    def _sam_provider(still: Path):
        return dialog.collect_sam_points(still)

    result = job.run_job(
        job.JobOptions(
            clip=clip,
            mask_source=opts_ui.mask_source,
            mask_path=opts_ui.mask_path,
            sam_points=list(opts_ui.sam_points),
            sam_points_provider=_sam_provider
            if opts_ui.mask_source == "sam2"
            else None,
            output_kind=opts_ui.output_kind,
            write_foreground=opts_ui.write_foreground,
            import_to_flame=opts_ui.import_to_flame,
            work_dir=opts_ui.work_dir,
        ),
        logger=logger,
    )

    if not result.ok:
        dgpy_gui.error(None, "MatAnyone", result.message)
        return

    msg = f"Done.\nWork: {result.work_dir}\nAlpha: {result.alpha_path}"
    if result.imported:
        msg += "\nImported to Flame."
    else:
        msg += "\n(Not imported — open path manually if needed.)"
    dgpy_gui.info(None, "MatAnyone", msg)
