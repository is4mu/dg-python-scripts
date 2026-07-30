"""Progress dialog for MatAnyone runtime setup (PySide6).

Non-modal so Flame stays interactive while setup runs on a QThread.
"""

from __future__ import annotations

import time

from PySide6 import QtCore, QtWidgets

import matanyone_runtime_setup as setup

__version__ = "0.1.8"

# Keep alive while the background job runs (menu callback returns immediately).
_ACTIVE: SetupProgressDialog | None = None


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
    """Non-modal progress UI. Work runs on a QThread."""

    def __init__(self, *, force: bool, parent=None):
        super().__init__(parent)
        self.setWindowTitle("MatAnyone Runtime Setup")
        self.setMinimumSize(640, 420)
        self.setModal(False)
        self.setWindowModality(QtCore.Qt.WindowModality.NonModal)
        # Tool window: stays handy without blocking Flame's main window.
        flags = self.windowFlags()
        flags |= QtCore.Qt.WindowType.Tool
        self.setWindowFlags(flags)
        self._force = force
        self._finished = False
        self._ok = False
        self._error = ""
        self._started = time.monotonic()
        self._thread: QtCore.QThread | None = None
        self._worker: _SetupWorker | None = None

        layout = QtWidgets.QVBoxLayout(self)

        note = QtWidgets.QLabel(
            "Flame stays usable while setup runs. You can keep editing; "
            "this window is non-modal (Hide to tuck it away)."
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        self._step_label = QtWidgets.QLabel("Starting…")
        layout.addWidget(self._step_label)

        self._bar = QtWidgets.QProgressBar()
        self._bar.setRange(0, setup.setup_step_count())
        self._bar.setValue(0)
        self._bar.setFormat("%v / %m steps")
        layout.addWidget(self._bar)

        self._eta = QtWidgets.QLabel(
            "Typical total: ~10–40 min. "
            "Miniforge (if needed) then PyTorch are the long steps."
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

        row = QtWidgets.QHBoxLayout()
        self._hide_btn = QtWidgets.QPushButton("Hide")
        self._hide_btn.setToolTip("Hide this window; setup keeps running")
        self._hide_btn.clicked.connect(self.hide)
        self._close_btn = QtWidgets.QPushButton("Close")
        self._close_btn.setEnabled(False)
        self._close_btn.clicked.connect(self.close)
        row.addStretch(1)
        row.addWidget(self._hide_btn)
        row.addWidget(self._close_btn)
        layout.addLayout(row)

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
        base = (
            "Typical total: ~10–40 min. "
            "Miniforge (if needed) then PyTorch are the long steps."
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
        self._bar.setValue(min(index + 1, total))
        self._step_label.setText(f"Step {index + 1}/{total}: {label}")

    @QtCore.Slot(object)
    def _on_ok(self, _root) -> None:
        import dgpy_gui
        import matanyone_runtime_paths as paths

        self._finished = True
        self._ok = True
        self._elapsed_timer.stop()
        self._bar.setValue(self._bar.maximum())
        self._step_label.setText("Done")
        self._on_log("— setup finished —")
        self._hide_btn.setEnabled(False)
        self._close_btn.setEnabled(True)
        self.show()
        self.raise_()
        self.activateWindow()
        dgpy_gui.info(
            self,
            "MatAnyone Runtime",
            f"Ready.\n\n{paths.runtime_root()}\npython={paths.resolve_python()}",
        )

    @QtCore.Slot(str)
    def _on_err(self, message: str) -> None:
        import dgpy_gui
        import dgpy_log

        self._finished = True
        self._ok = False
        self._error = message
        self._elapsed_timer.stop()
        self._step_label.setText("Failed")
        self._on_log("— setup failed —")
        self._on_log(message)
        self._hide_btn.setEnabled(False)
        self._close_btn.setEnabled(True)
        dgpy_log.setup().error("MatAnyone runtime setup failed: %s", message)
        self.show()
        self.raise_()
        self.activateWindow()
        dgpy_gui.error(self, "MatAnyone Runtime", f"Setup failed:\n{message}")

    def closeEvent(self, event) -> None:  # noqa: N802
        global _ACTIVE
        # While running: treat close like Hide (job keeps going).
        if self._thread is not None and self._thread.isRunning() and not self._finished:
            event.ignore()
            self.hide()
            return
        _ACTIVE = None
        super().closeEvent(event)

    @property
    def succeeded(self) -> bool:
        return self._ok

    @property
    def error_message(self) -> str:
        return self._error


def setup_is_running() -> bool:
    return _ACTIVE is not None and _ACTIVE._thread is not None and _ACTIVE._thread.isRunning()


def start_setup_nonblocking(*, force: bool) -> bool:
    """Start non-modal setup. Returns False if a setup is already running."""
    global _ACTIVE
    if setup_is_running():
        assert _ACTIVE is not None
        _ACTIVE.show()
        _ACTIVE.raise_()
        _ACTIVE.activateWindow()
        return False
    dlg = SetupProgressDialog(force=force)
    _ACTIVE = dlg
    dlg.start()
    dlg.show()
    dlg.raise_()
    return True
