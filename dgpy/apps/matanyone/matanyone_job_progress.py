"""Non-modal progress UI for MatAnyone jobs (export / mask / infer / import)."""

from __future__ import annotations

import threading
import time
from typing import Callable

from PySide6 import QtCore, QtWidgets

import matanyone_job as job

__version__ = "0.6.2"

_ACTIVE: JobProgressDialog | None = None


class _JobWorker(QtCore.QObject):
    log_line = QtCore.Signal(str)
    step_changed = QtCore.Signal(int, int, str)
    finished = QtCore.Signal(object)  # JobResult

    def __init__(
        self,
        opts: job.JobOptions,
        *,
        cancel: threading.Event,
        holder: job._ProcHolder,
        logger,
    ):
        super().__init__()
        self._opts = opts
        self._cancel = cancel
        self._holder = holder
        self._logger = logger

    @QtCore.Slot()
    def run(self) -> None:
        result = job.run_job(
            self._opts,
            logger=self._logger,
            progress=lambda m: self.log_line.emit(m),
            step=lambda i, t, label: self.step_changed.emit(i, t, label),
            cancel=self._cancel,
            proc_holder=self._holder,
        )
        self.finished.emit(result)


class JobProgressDialog(QtWidgets.QDialog):
    """Non-modal job progress. Cancel kills the active subprocess."""

    def __init__(
        self,
        opts: job.JobOptions,
        *,
        logger,
        on_finished: Callable[[job.JobResult], None] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("MatAnyone 2")
        self.setMinimumSize(640, 420)
        self.setModal(False)
        self.setWindowModality(QtCore.Qt.WindowModality.NonModal)
        # Avoid WindowType.Tool — under Flame it often paints blank / unstable.
        self.setWindowFlags(
            QtCore.Qt.WindowType.Window
            | QtCore.Qt.WindowType.WindowStaysOnTopHint
        )
        self.setStyleSheet(
            "QDialog { background-color: #2b2b2b; color: #e6e6e6; }"
            "QLabel { color: #e6e6e6; }"
            "QTextEdit { background-color: #1e1e1e; color: #d0d0d0; "
            "border: 1px solid #444; }"
            "QProgressBar { text-align: center; color: #eee; "
            "border: 1px solid #555; background: #1e1e1e; }"
            "QProgressBar::chunk { background-color: #3d7a4a; }"
            "QPushButton { min-height: 24px; }"
        )

        self._opts = opts
        self._logger = logger
        self._on_finished = on_finished
        self._finished = False
        self._result: job.JobResult | None = None
        self._started = time.monotonic()
        self._cancel = threading.Event()
        self._holder = job._ProcHolder()
        self._thread: QtCore.QThread | None = None
        self._worker: _JobWorker | None = None

        layout = QtWidgets.QVBoxLayout(self)
        note = QtWidgets.QLabel(
            "Flame stays usable while MatAnyone runs. "
            "Hide to tuck this away; Cancel stops the external process."
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        self._step_label = QtWidgets.QLabel("Starting…")
        layout.addWidget(self._step_label)

        self._bar = QtWidgets.QProgressBar()
        self._bar.setRange(0, job.job_step_count(opts.phase))
        self._bar.setValue(0)
        self._bar.setFormat("%v / %m steps")
        layout.addWidget(self._bar)

        if opts.phase == "export":
            eta_text = "Exporting source for MatAnyone…"
            title = "MatAnyone 2 — Export"
        elif opts.phase == "infer":
            eta_text = "Infer can take several minutes depending on length."
            title = "MatAnyone 2 — Infer"
        else:
            eta_text = "Infer can take several minutes depending on length."
            title = "MatAnyone 2"
        self.setWindowTitle(title)
        self._eta = QtWidgets.QLabel(eta_text)
        self._eta.setWordWrap(True)
        layout.addWidget(self._eta)

        self._log = QtWidgets.QTextEdit()
        self._log.setReadOnly(True)
        self._log.setLineWrapMode(QtWidgets.QTextEdit.LineWrapMode.NoWrap)
        font = self._log.font()
        font.setFamily("Menlo")
        if font.family() != "Menlo":
            font.setFamily("monospace")
        self._log.setFont(font)
        layout.addWidget(self._log, 1)

        row = QtWidgets.QHBoxLayout()
        self._hide_btn = QtWidgets.QPushButton("Hide")
        self._hide_btn.clicked.connect(self.hide)
        self._cancel_btn = QtWidgets.QPushButton("Cancel")
        self._cancel_btn.clicked.connect(self._request_cancel)
        self._close_btn = QtWidgets.QPushButton("Close")
        self._close_btn.setEnabled(False)
        self._close_btn.clicked.connect(self.close)
        row.addStretch(1)
        row.addWidget(self._hide_btn)
        row.addWidget(self._cancel_btn)
        row.addWidget(self._close_btn)
        layout.addLayout(row)

        self._elapsed_timer = QtCore.QTimer(self)
        self._elapsed_timer.setInterval(1000)
        self._elapsed_timer.timeout.connect(self._tick_elapsed)
        self._elapsed_timer.start()

    def start(self) -> None:
        self._thread = QtCore.QThread(self)
        self._worker = _JobWorker(
            self._opts,
            cancel=self._cancel,
            holder=self._holder,
            logger=self._logger,
        )
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.log_line.connect(self._on_log)
        self._worker.step_changed.connect(self._on_step)
        self._worker.finished.connect(self._on_done)
        self._worker.finished.connect(self._thread.quit)
        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.start()

    def _tick_elapsed(self) -> None:
        secs = int(time.monotonic() - self._started)
        mm, ss = divmod(secs, 60)
        if self._opts.phase == "export":
            base = "Exporting source for MatAnyone…"
        else:
            base = "Infer can take several minutes depending on length."
        self._eta.setText(f"{base}\nElapsed: {mm:02d}:{ss:02d}")

    @QtCore.Slot(str)
    def _on_log(self, line: str) -> None:
        self._log.append(line)
        cursor = self._log.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self._log.setTextCursor(cursor)

    @QtCore.Slot(int, int, str)
    def _on_step(self, index: int, total: int, label: str) -> None:
        self._bar.setMaximum(max(total, 1))
        self._bar.setValue(min(index + 1, total))
        self._step_label.setText(f"Step {index + 1}/{total}: {label}")

    def _request_cancel(self) -> None:
        self._cancel.set()
        self._holder.kill()
        self._cancel_btn.setEnabled(False)
        self._on_log("— cancel requested —")

    @QtCore.Slot(object)
    def _on_done(self, result: job.JobResult) -> None:
        self._finished = True
        self._result = result
        self._elapsed_timer.stop()
        self._cancel_btn.setEnabled(False)
        self._hide_btn.setEnabled(False)
        self._close_btn.setEnabled(True)
        if result.cancelled:
            self._step_label.setText("Cancelled")
            self._on_log("— cancelled —")
        elif result.ok:
            self._bar.setValue(self._bar.maximum())
            self._step_label.setText("Done")
            self._on_log("— finished —")
        else:
            self._step_label.setText("Failed")
            self._on_log("— failed —")
            self._on_log(result.message)
        # For export success, close immediately so the mask dialog is not buried.
        auto_close = result.ok and self._opts.phase == "export"
        if auto_close:
            self.hide()
        else:
            self.show()
            self.raise_()
            self.activateWindow()
        cb = self._on_finished
        self._on_finished = None
        if cb is not None:
            cb(result)
        if auto_close:
            QtCore.QTimer.singleShot(0, self.close)

    def closeEvent(self, event) -> None:  # noqa: N802
        global _ACTIVE
        if self._thread is not None and self._thread.isRunning() and not self._finished:
            event.ignore()
            self.hide()
            return
        if _ACTIVE is self:
            _ACTIVE = None
        super().closeEvent(event)


def job_is_running() -> bool:
    return _ACTIVE is not None and _ACTIVE._thread is not None and _ACTIVE._thread.isRunning()


def raise_job_window() -> None:
    if _ACTIVE is None:
        return
    _ACTIVE.show()
    _ACTIVE.raise_()
    _ACTIVE.activateWindow()


def close_finished_progress() -> None:
    """Close a finished progress dialog (e.g. before opening another stage)."""
    global _ACTIVE
    dlg = _ACTIVE
    if dlg is None:
        return
    if dlg._thread is not None and dlg._thread.isRunning() and not dlg._finished:
        return
    _ACTIVE = None
    dlg.hide()
    dlg.close()


def start_job_nonblocking(
    opts: job.JobOptions,
    *,
    logger,
    on_finished: Callable[[job.JobResult], None] | None = None,
) -> bool:
    """Start non-modal job. Returns False if a job is already running."""
    global _ACTIVE
    if job_is_running():
        assert _ACTIVE is not None
        _ACTIVE.show()
        _ACTIVE.raise_()
        _ACTIVE.activateWindow()
        return False
    # Replace a finished leftover window (export Done) if still open.
    if _ACTIVE is not None and _ACTIVE._finished:
        old = _ACTIVE
        _ACTIVE = None
        old.hide()
        old.close()
    dlg = JobProgressDialog(opts, logger=logger, on_finished=on_finished)
    _ACTIVE = dlg
    dlg.start()
    dlg.show()
    dlg.raise_()
    return True
