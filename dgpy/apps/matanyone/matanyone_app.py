"""MatAnyone app entry: export → mask dialog → infer."""

from __future__ import annotations

from pathlib import Path

import matanyone_dialog as dialog
import matanyone_job as job
import matanyone_job_progress as job_progress
import matanyone_selection as selection

__version__ = "0.6.2"


def run_from_selection(selection_items) -> None:
    import dgpy_gui
    import dgpy_log
    import matanyone_runtime_paths as rpaths
    from PySide6 import QtCore

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

    if not rpaths.is_ready():
        dgpy_gui.warning(
            None,
            "MatAnyone",
            "MatAnyone 2 runtime is not set up.\n"
            "Run DGpy → MatAnyone → Runtime Setup… first.",
        )
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

    work = job.default_work_dir()

    def _on_infer_finished(result: job.JobResult) -> None:
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

    def _start_infer(opts_ui: dialog.DialogResult, video: Path) -> None:
        def _go() -> None:
            job_progress.close_finished_progress()
            started = job_progress.start_job_nonblocking(
                job.JobOptions(
                    clip=clip,
                    phase="infer",
                    mask_source=opts_ui.mask_source,
                    mask_path=opts_ui.mask_path,
                    sam_points=list(opts_ui.sam_points),
                    output_kind=opts_ui.output_kind,
                    write_foreground=opts_ui.write_foreground,
                    import_to_flame=opts_ui.import_to_flame,
                    work_dir=opts_ui.work_dir or work,
                    source_video=video,
                ),
                logger=logger,
                on_finished=_on_infer_finished,
            )
            if not started:
                logger.info("MatAnyone infer already running")

        # Defer so the mask dialog can finish tearing down (avoids Flame segfaults).
        QtCore.QTimer.singleShot(0, _go)

    def _open_mask_then_infer(
        video: Path, still: Path, work_dir: Path
    ) -> None:
        opts_ui = dialog.open_mask_dialog(
            clip,
            still_path=still,
            work_dir=work_dir,
            ignored_count=ignored,
        )
        if opts_ui is None:
            return
        _start_infer(opts_ui, video)

    def _on_export_finished(result: job.JobResult) -> None:
        if result.cancelled:
            dgpy_gui.info(None, "MatAnyone", "Export cancelled.")
            return
        if not result.ok:
            dgpy_gui.error(None, "MatAnyone", result.message)
            return
        video = result.video_path
        still = result.still_path
        work_dir = result.work_dir or work
        if video is None or still is None or not video.is_file():
            dgpy_gui.error(None, "MatAnyone", "Export finished but files are missing.")
            return

        def _go() -> None:
            job_progress.close_finished_progress()
            _open_mask_then_infer(video, still, work_dir)

        # Let the export progress window close before opening the mask dialog.
        QtCore.QTimer.singleShot(50, _go)

    started = job_progress.start_job_nonblocking(
        job.JobOptions(
            clip=clip,
            phase="export",
            work_dir=work,
        ),
        logger=logger,
        on_finished=_on_export_finished,
    )
    if not started:
        logger.info("MatAnyone export already running")
