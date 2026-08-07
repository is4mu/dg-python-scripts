"""MatAnyone app entry: dialog → non-blocking job."""

from __future__ import annotations

from pathlib import Path

import matanyone_dialog as dialog
import matanyone_job as job
import matanyone_job_progress as job_progress
import matanyone_selection as selection

__version__ = "0.5.1"


def run_from_selection(selection_items) -> None:
    import dgpy_gui
    import dgpy_log
    import matanyone_runtime_paths as rpaths

    logger = dgpy_log.setup()
    if job_progress.job_is_running():
        dgpy_gui.info(
            None,
            "MatAnyone",
            "A MatAnyone job is already running.\n"
            "The progress window was brought to the front.",
        )
        job_progress.raise_job_window()
        return

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

    if opts_ui.mask_source == "sam2" and not rpaths.is_sam2_ready():
        dgpy_gui.warning(
            None,
            "MatAnyone",
            "SAM2 is not ready in the MatAnyone runtime.\n\n"
            "Run DGpy → MatAnyone → SAM2 Setup… first "
            "(uses the existing runtime; no system packages),\n"
            "or choose Flame (PNG/EXR) mask instead.",
        )
        return

    def _sam_provider(still: Path):
        return dialog.collect_sam_points(still)

    def _on_finished(result: job.JobResult) -> None:
        if result.cancelled:
            dgpy_gui.info(None, "MatAnyone", "Cancelled.")
            return
        if not result.ok:
            dgpy_gui.error(None, "MatAnyone", result.message)
            return
        msg = f"Done.\nWork: {result.work_dir}\nAlpha: {result.alpha_path}"
        if result.imported:
            msg += "\nImported to Flame."
            dgpy_gui.info(None, "MatAnyone", msg)
        elif "import failed" in result.message.lower():
            dgpy_gui.warning(None, "MatAnyone", result.message)
        else:
            msg += "\n(Not imported — open path manually if needed.)"
            dgpy_gui.info(None, "MatAnyone", msg)

    started = job_progress.start_job_nonblocking(
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
        on_finished=_on_finished,
    )
    if not started:
        logger.info("MatAnyone job already running")
