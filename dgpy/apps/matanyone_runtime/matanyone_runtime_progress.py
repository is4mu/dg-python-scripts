"""Progress dialog for MatAnyone runtime setup (PySide6)."""

from __future__ import annotations

import time

from PySide6 import QtCore, QtWidgets

import matanyone_runtime_setup as setup

__version__ = "0.1.2"


class _SetupWorker(QtCore.QObject):
    log_line = QtCore.Signal(str)
    step_changed = QtCore.Signal(int, int, str)
    finished_ok = QtCore.Signal(object)  # Path
    finished_err = QtCore.Signal(str)

    def __init__(self, force: bool):
        super().__init__()
        self._force = force

    @QtCore.Slot()
    def run(self) -> None:
        try:
            root = setup.setup_runtime(
                log=lambda m: self.log_line.emit(m),
                step=lambda i, t, label: self.step_changed.emit(i, t, label),
                force=self._force,
            )
            self.finished_ok.emit(root)
        except Exception as exc:  # noqa: BLE001
            self.finished_err.emit(str(exc))


class SetupProgressDialog(QtWidgets.QDialog):
    """Step bar + live log. Work runs on a QThread so the UI stays alive."""

    def __init__(self, *, force: bool, parent=None):
        super().__init__(parent)
        self.setWindowTitle("MatAnyone Runtime Setup")
        self.setMinimumSize(640, 420)
        self.setModal(True)
        self._force = force
        self._ok = False
        self._error = ""
        self._started = time.monotonic()
        self._thread: QtCore.QThread | None = None
        self._worker: _SetupWorker | None = None

        layout = QtWidgets.QVBoxLayout(self)

        self._step_label = QtWidgets.QLabel("Starting…")
        layout.addWidget(self._step_label)

        self._bar = QtWidgets.QProgressBar()
        self._bar.setRange(0, setup.setup_step_count())
        self._bar.setValue(0)
        self._bar.setFormat("%v / %m steps")
        layout.addWidget(self._bar)

        self._eta = QtWidgets.QLabel(
            "Typical total: ~10–40 min (PyTorch download dominates). "
            "Exact time depends on network."
        )
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

        self._close_btn = QtWidgets.QPushButton("Close")
        self._close_btn.setEnabled(False)
        self._close_btn.clicked.connect(self.accept)
        layout.addWidget(self._close_btn, alignment=QtCore.Qt.AlignmentFlag.AlignRight)

        self._elapsed_timer = QtCore.QTimer(self)
        self._elapsed_timer.setInterval(1000)
        self._elapsed_timer.timeout.connect(self._tick_elapsed)
        self._elapsed_timer.start()

    def start(self) -> None:
        self._thread = QtCore.QThread(self)
        self._worker = _SetupWorker(self._force)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.log_line.connect(self._on_log)
        self._worker.step_changed.connect(self._on_step)
        self._worker.finished_ok.connect(self._on_ok)
        self._worker.finished_err.connect(self._on_err)
        self._worker.finished_ok.connect(self._thread.quit)
        self._worker.finished_err.connect(self._thread.quit)
        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.start()

    def _tick_elapsed(self) -> None:
        secs = int(time.monotonic() - self._started)
        mm, ss = divmod(secs, 60)
        # Keep the network hint; append elapsed.
        base = (
            "Typical total: ~10–40 min (PyTorch download dominates). "
            "Exact time depends on network."
        )
        self._eta.setText(f"{base}\nElapsed: {mm:02d}:{ss:02d}")

    @QtCore.Slot(str)
    def _on_log(self, line: str) -> None:
        self._log.append(line)
        cursor = self._log.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self._log.setTextCursor(cursor)

    @QtCore.Slot(int, int, str)
    def _on_step(self, index: int, total: int, label: str) -> None:
        self._bar.setMaximum(total)
        # Show completed steps as index (0-based step about to run / running).
        self._bar.setValue(min(index + 1, total))
        self._step_label.setText(f"Step {index + 1}/{total}: {label}")

    @QtCore.Slot(object)
    def _on_ok(self, _root) -> None:
        self._ok = True
        self._elapsed_timer.stop()
        self._bar.setValue(self._bar.maximum())
        self._step_label.setText("Done")
        self._on_log("— setup finished —")
        self._close_btn.setEnabled(True)

    @QtCore.Slot(str)
    def _on_err(self, message: str) -> None:
        self._ok = False
        self._error = message
        self._elapsed_timer.stop()
        self._step_label.setText("Failed")
        self._on_log("— setup failed —")
        self._on_log(message)
        self._close_btn.setEnabled(True)

    def closeEvent(self, event) -> None:  # noqa: N802
        # Block closing while worker runs (no Cancel for v1 — mid-pip is messy).
        if self._thread is not None and self._thread.isRunning():
            event.ignore()
            return
        super().closeEvent(event)

    @property
    def succeeded(self) -> bool:
        return self._ok

    @property
    def error_message(self) -> str:
        return self._error


def run_setup_with_progress(*, force: bool) -> tuple[bool, str]:
    """Show modal progress UI; return (ok, error_or_empty)."""
    dlg = SetupProgressDialog(force=force)
    dlg.start()
    dlg.exec()
    return dlg.succeeded, dlg.error_message
