"""Consolidate Handles dialogs: options + single Results window."""

from __future__ import annotations

from collections.abc import Callable

from PySide6 import QtGui, QtWidgets

from segment_handle_clips_util import TITLE, __version__

DEFAULT_HANDLES = 5
DEFAULT_MERGE_GAP = 24


class ProbeOptionsDialog(QtWidgets.QDialog):
    def __init__(self, *, segment_count: int, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(TITLE)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(
            QtWidgets.QLabel(
                f"Compute keep ranges + merge preview.\n"
                f"Segments: {segment_count}\n"
                f"Create / Replace stay on the Results window."
            )
        )

        form = QtWidgets.QFormLayout()
        self._handles = QtWidgets.QSpinBox()
        self._handles.setRange(0, 9999)
        self._handles.setValue(DEFAULT_HANDLES)
        self._handles.setSuffix(" F")
        form.addRow("Handles (head = tail)", self._handles)

        self._merge_gap = QtWidgets.QSpinBox()
        self._merge_gap.setRange(0, 99999)
        self._merge_gap.setValue(DEFAULT_MERGE_GAP)
        self._merge_gap.setSuffix(" F")
        form.addRow("Merge gap (same source)", self._merge_gap)
        layout.addLayout(form)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def handles(self) -> int:
        return int(self._handles.value())

    def merge_gap(self) -> int:
        return int(self._merge_gap.value())


class ProbeReportDialog(QtWidgets.QDialog):
    """Long-lived Results window: probe → Create → Replace on one instance."""

    def __init__(
        self,
        report: str,
        *,
        on_create: Callable[["ProbeReportDialog"], None] | None = None,
        show_create: bool = True,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"{TITLE} — Results")
        self.resize(1000, 640)
        self._on_create = on_create
        self._on_replace: Callable[["ProbeReportDialog"], None] | None = None
        self._busy = False

        layout = QtWidgets.QVBoxLayout(self)
        self._text = QtWidgets.QPlainTextEdit()
        self._text.setReadOnly(True)
        self._text.setPlainText(report)
        font = QtGui.QFontDatabase.systemFont(
            QtGui.QFontDatabase.SystemFont.FixedFont
        )
        self._text.setFont(font)
        layout.addWidget(self._text)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Close
        )
        copy_btn = buttons.addButton(
            "Copy report", QtWidgets.QDialogButtonBox.ButtonRole.ActionRole
        )
        copy_btn.clicked.connect(self._copy)

        self._create_btn = buttons.addButton(
            "Create on Sources",
            QtWidgets.QDialogButtonBox.ButtonRole.ActionRole,
        )
        self._create_btn.clicked.connect(self._create_clicked)
        if not show_create or on_create is None:
            self._create_btn.hide()

        self._replace_btn = buttons.addButton(
            "Replace Media",
            QtWidgets.QDialogButtonBox.ButtonRole.ActionRole,
        )
        self._replace_btn.clicked.connect(self._replace_clicked)
        self._replace_btn.hide()

        close = buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Close)
        if close is not None:
            close.clicked.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def append_text(self, text: str) -> None:
        self._text.appendPlainText(text)
        bar = self._text.verticalScrollBar()
        bar.setValue(bar.maximum())
        QtWidgets.QApplication.processEvents()

    def set_phase_after_create(
        self,
        *,
        can_replace: bool,
        on_replace: Callable[["ProbeReportDialog"], None] | None = None,
    ) -> None:
        self._create_btn.hide()
        self._on_replace = on_replace
        if can_replace and on_replace is not None:
            self._replace_btn.show()
            self._replace_btn.setEnabled(True)
        else:
            self._replace_btn.hide()

    def set_phase_done(self) -> None:
        self._create_btn.hide()
        self._replace_btn.hide()
        self._on_create = None
        self._on_replace = None

    def _copy(self) -> None:
        QtWidgets.QApplication.clipboard().setText(self._text.toPlainText())

    def _create_clicked(self) -> None:
        if self._busy or self._on_create is None:
            return
        self._busy = True
        self._create_btn.setEnabled(False)
        try:
            self._on_create(self)
        finally:
            self._busy = False

    def _replace_clicked(self) -> None:
        if self._busy or self._on_replace is None:
            return
        self._busy = True
        self._replace_btn.setEnabled(False)
        try:
            self._on_replace(self)
        finally:
            self._busy = False


def ask_probe_options(*, segment_count: int) -> tuple[int, int] | None:
    """Return (handles, merge_gap) or None if cancelled."""
    dlg = ProbeOptionsDialog(segment_count=segment_count)
    if dlg.exec() != QtWidgets.QDialog.DialogCode.Accepted:
        return None
    return dlg.handles(), dlg.merge_gap()


def run_results_dialog(
    report: str,
    *,
    on_create: Callable[[ProbeReportDialog], None] | None = None,
    show_create: bool = True,
) -> None:
    """Show one Results window until the user closes it."""
    dlg = ProbeReportDialog(
        report, on_create=on_create, show_create=show_create
    )
    dlg.exec()
