"""Progress dialogs for MatAnyone runtime Setup / Remove (PySide6).

Non-modal so Flame stays interactive while work runs on a QThread.
"""

from __future__ import annotations

import time

from PySide6 import QtCore, QtWidgets

import matanyone_runtime_setup as setup

__version__ = "0.4.0"

# Keep alive while the background job runs (menu callback returns immediately).
_ACTIVE_SETUP: SetupProgressDialog | None = None
_ACTIVE_REMOVE: RemoveProgressDialog | None = None
_ACTIVE_SAM2: Sam2SetupProgressDialog | None = None


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


class _RemoveWorker(QtCore.QObject):
    log_line = QtCore.Signal(str)
    step_changed = QtCore.Signal(int, int, str)
    finished_ok = QtCore.Signal()
    finished_err = QtCore.Signal(str)

    @QtCore.Slot()
    def run(self) -> None:
        try:
            setup.remove_runtime(
                log=lambda m: self.log_line.emit(m),
                step=lambda i, t, label: self.step_changed.emit(i, t, label),
            )
            self.finished_ok.emit()
        except Exception as exc:  # noqa: BLE001
            self.finished_err.emit(str(exc))


class _Sam2SetupWorker(QtCore.QObject):
    log_line = QtCore.Signal(str)
    step_changed = QtCore.Signal(int, int, str)
    finished_ok = QtCore.Signal(object)
    finished_err = QtCore.Signal(str)

    def __init__(self, force: bool):
        super().__init__()
        self._force = force

    @QtCore.Slot()
    def run(self) -> None:
        try:
            root = setup.setup_sam2(
                log=lambda m: self.log_line.emit(m),
                step=lambda i, t, label: self.step_changed.emit(i, t, label),
                force=self._force,
            )
            self.finished_ok.emit(root)
        except Exception as exc:  # noqa: BLE001
            self.finished_err.emit(str(exc))


class _ProgressDialogBase(QtWidgets.QDialog):
    """Shared non-modal shell: step bar + log + elapsed + Hide."""

    def __init__(self, title: str, note: str, *, steps: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(640, 420)
        self.setModal(False)
        self.setWindowModality(QtCore.Qt.WindowModality.NonModal)
        flags = self.windowFlags()
        flags |= QtCore.Qt.WindowType.Tool
        self.setWindowFlags(flags)
        self._finished = False
        self._ok = False
        self._error = ""
        self._started = time.monotonic()
        self._thread: QtCore.QThread | None = None
        self._eta_hint = note

        layout = QtWidgets.QVBoxLayout(self)

        note_lbl = QtWidgets.QLabel(note)
        note_lbl.setWordWrap(True)
        layout.addWidget(note_lbl)

        self._step_label = QtWidgets.QLabel("Starting…")
        layout.addWidget(self._step_label)

        self._bar = QtWidgets.QProgressBar()
        self._bar.setRange(0, max(steps, 1))
        self._bar.setValue(0)
        self._bar.setFormat("%v / %m steps")
        layout.addWidget(self._bar)

        self._eta = QtWidgets.QLabel("")
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
        self._hide_btn.setToolTip("Hide this window; work keeps running")
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

    def _tick_elapsed(self) -> None:
        secs = int(time.monotonic() - self._started)
        mm, ss = divmod(secs, 60)
        self._eta.setText(f"{self._eta_hint}\nElapsed: {mm:02d}:{ss:02d}")

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

    def _mark_done_ui(self, *, ok: bool, label: str) -> None:
        self._finished = True
        self._ok = ok
        self._elapsed_timer.stop()
        if ok:
            self._bar.setValue(self._bar.maximum())
        self._step_label.setText(label)
        self._hide_btn.setEnabled(False)
        self._close_btn.setEnabled(True)
        self.show()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._thread is not None and self._thread.isRunning() and not self._finished:
            event.ignore()
            self.hide()
            return
        super().closeEvent(event)

    @property
    def succeeded(self) -> bool:
        return self._ok

    @property
    def error_message(self) -> str:
        return self._error


class SetupProgressDialog(_ProgressDialogBase):
    """Non-modal Setup UI. Work runs on a QThread."""

    def __init__(self, *, force: bool, parent=None):
        super().__init__(
            "MatAnyone 2 Runtime Setup",
            "Flame stays usable while setup runs. You can keep editing; "
            "this window is non-modal (Hide to tuck it away).\n"
            "Typical total: ~10–40 min (Miniforge + PyTorch + MatAnyone 2).",
            steps=setup.setup_step_count(),
            parent=parent,
        )
        self._force = force
        self._worker: _SetupWorker | None = None

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

    @QtCore.Slot(object)
    def _on_ok(self, _root) -> None:
        import dgpy_gui
        import matanyone_runtime_paths as paths

        self._on_log("— setup finished —")
        self._mark_done_ui(ok=True, label="Done")
        dgpy_gui.info(
            self,
            "MatAnyone Runtime",
            f"Ready.\n\n{paths.runtime_root()}\npython={paths.resolve_python()}",
        )

    @QtCore.Slot(str)
    def _on_err(self, message: str) -> None:
        import dgpy_gui
        import dgpy_log

        self._error = message
        self._on_log("— setup failed —")
        self._on_log(message)
        self._mark_done_ui(ok=False, label="Failed")
        dgpy_log.setup().error("MatAnyone runtime setup failed: %s", message)
        dgpy_gui.error(self, "MatAnyone Runtime", f"Setup failed:\n{message}")

    def closeEvent(self, event) -> None:  # noqa: N802
        global _ACTIVE_SETUP
        if self._thread is not None and self._thread.isRunning() and not self._finished:
            event.ignore()
            self.hide()
            return
        _ACTIVE_SETUP = None
        QtWidgets.QDialog.closeEvent(self, event)


class RemoveProgressDialog(_ProgressDialogBase):
    """Non-modal Remove UI (large rmtree must not freeze Flame)."""

    def __init__(self, parent=None):
        super().__init__(
            "MatAnyone Runtime Remove",
            "Deleting runtime folders (may be several GB). "
            "Flame stays usable — this window is non-modal.",
            steps=setup.remove_step_count(),
            parent=parent,
        )
        self._worker: _RemoveWorker | None = None

    def start(self) -> None:
        self._thread = QtCore.QThread(self)
        self._worker = _RemoveWorker()
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

    @QtCore.Slot()
    def _on_ok(self) -> None:
        import dgpy_gui

        self._on_log("— remove finished —")
        self._mark_done_ui(ok=True, label="Done")
        dgpy_gui.info(self, "MatAnyone Runtime", "Removed.")

    @QtCore.Slot(str)
    def _on_err(self, message: str) -> None:
        import dgpy_gui
        import dgpy_log

        self._error = message
        self._on_log("— remove failed —")
        self._on_log(message)
        self._mark_done_ui(ok=False, label="Failed")
        dgpy_log.setup().error("MatAnyone runtime remove failed: %s", message)
        dgpy_gui.error(self, "MatAnyone Runtime", f"Remove failed:\n{message}")

    def closeEvent(self, event) -> None:  # noqa: N802
        global _ACTIVE_REMOVE
        if self._thread is not None and self._thread.isRunning() and not self._finished:
            event.ignore()
            self.hide()
            return
        _ACTIVE_REMOVE = None
        QtWidgets.QDialog.closeEvent(self, event)


class Sam2SetupProgressDialog(_ProgressDialogBase):
    """Non-modal SAM2 install into the existing MatAnyone runtime."""

    def __init__(self, *, force: bool, parent=None):
        super().__init__(
            "MatAnyone SAM2 Setup",
            "Installs facebookresearch/sam2 + checkpoint under "
            "dgpy_runtimes/matanyone (no system packages). "
            "Flame stays usable.",
            steps=setup.sam2_setup_step_count(),
            parent=parent,
        )
        self._force = force
        self._worker: _Sam2SetupWorker | None = None

    def start(self) -> None:
        self._thread = QtCore.QThread(self)
        self._worker = _Sam2SetupWorker(self._force)
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

    @QtCore.Slot(object)
    def _on_ok(self, _root) -> None:
        import dgpy_gui
        import matanyone_runtime_paths as paths

        self._on_log("— SAM2 setup finished —")
        self._mark_done_ui(ok=True, label="Done")
        dgpy_gui.info(
            self,
            "MatAnyone SAM2",
            "SAM2 ready.\n\n"
            f"checkpoint={paths.sam2_checkpoint_path()}\n"
            f"config={paths.sam2_config_id()}",
        )

    @QtCore.Slot(str)
    def _on_err(self, message: str) -> None:
        import dgpy_gui
        import dgpy_log

        self._error = message
        self._on_log("— SAM2 setup failed —")
        self._on_log(message)
        self._mark_done_ui(ok=False, label="Failed")
        dgpy_log.setup().error("MatAnyone SAM2 setup failed: %s", message)
        dgpy_gui.error(self, "MatAnyone SAM2", f"Setup failed:\n{message}")

    def closeEvent(self, event) -> None:  # noqa: N802
        global _ACTIVE_SAM2
        if self._thread is not None and self._thread.isRunning() and not self._finished:
            event.ignore()
            self.hide()
            return
        _ACTIVE_SAM2 = None
        QtWidgets.QDialog.closeEvent(self, event)


def setup_is_running() -> bool:
    return (
        _ACTIVE_SETUP is not None
        and _ACTIVE_SETUP._thread is not None
        and _ACTIVE_SETUP._thread.isRunning()
    )


def remove_is_running() -> bool:
    return (
        _ACTIVE_REMOVE is not None
        and _ACTIVE_REMOVE._thread is not None
        and _ACTIVE_REMOVE._thread.isRunning()
    )


def sam2_setup_is_running() -> bool:
    return (
        _ACTIVE_SAM2 is not None
        and _ACTIVE_SAM2._thread is not None
        and _ACTIVE_SAM2._thread.isRunning()
    )


def _any_runtime_job_running() -> bool:
    return setup_is_running() or remove_is_running() or sam2_setup_is_running()


def start_setup_nonblocking(*, force: bool) -> bool:
    """Start non-modal setup. Returns False if a setup is already running."""
    global _ACTIVE_SETUP
    if setup_is_running():
        assert _ACTIVE_SETUP is not None
        _ACTIVE_SETUP.show()
        _ACTIVE_SETUP.raise_()
        _ACTIVE_SETUP.activateWindow()
        return False
    if _any_runtime_job_running():
        return False
    dlg = SetupProgressDialog(force=force)
    _ACTIVE_SETUP = dlg
    dlg.start()
    dlg.show()
    dlg.raise_()
    return True


def start_remove_nonblocking() -> bool:
    """Start non-modal remove. Returns False if busy."""
    global _ACTIVE_REMOVE
    if remove_is_running():
        assert _ACTIVE_REMOVE is not None
        _ACTIVE_REMOVE.show()
        _ACTIVE_REMOVE.raise_()
        _ACTIVE_REMOVE.activateWindow()
        return False
    if _any_runtime_job_running():
        return False
    dlg = RemoveProgressDialog()
    _ACTIVE_REMOVE = dlg
    dlg.start()
    dlg.show()
    dlg.raise_()
    return True


def start_sam2_setup_nonblocking(*, force: bool) -> bool:
    """Start non-modal SAM2 setup. Returns False if busy."""
    global _ACTIVE_SAM2
    if sam2_setup_is_running():
        assert _ACTIVE_SAM2 is not None
        _ACTIVE_SAM2.show()
        _ACTIVE_SAM2.raise_()
        _ACTIVE_SAM2.activateWindow()
        return False
    if _any_runtime_job_running():
        return False
    dlg = Sam2SetupProgressDialog(force=force)
    _ACTIVE_SAM2 = dlg
    dlg.start()
    dlg.show()
    dlg.raise_()
    return True
