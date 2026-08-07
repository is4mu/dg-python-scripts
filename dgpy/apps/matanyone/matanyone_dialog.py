"""MatAnyone dialog (PySide6)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

import matanyone_selection as selection

__version__ = "0.5.1"

_WINDOW: QtWidgets.QWidget | None = None


@dataclass
class DialogResult:
    mask_source: str
    mask_path: Path | None
    sam_points: list[tuple[float, float]]
    output_kind: str
    write_foreground: bool
    import_to_flame: bool
    work_dir: Path | None


class _SamPreview(QtWidgets.QLabel):
    """Clickable first-frame preview; stores image-space points."""

    point_added = QtCore.Signal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(480, 270)
        self.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("background:#222; color:#aaa;")
        self.setText(
            "SAM2: after export, click foreground points on the first frame"
        )
        self._pixmap: QtGui.QPixmap | None = None
        self._points: list[tuple[float, float]] = []

    def set_image_path(self, path: Path | None) -> None:
        self._points.clear()
        if path is None or not path.is_file():
            self._pixmap = None
            self.setText("No preview")
            return
        pm = QtGui.QPixmap(str(path))
        self._pixmap = pm
        self._refresh()

    def points(self) -> list[tuple[float, float]]:
        return list(self._points)

    def clear_points(self) -> None:
        self._points.clear()
        self._refresh()

    def _refresh(self) -> None:
        if self._pixmap is None or self._pixmap.isNull():
            return
        scaled = self._pixmap.scaled(
            self.size(),
            QtCore.Qt.AspectRatioMode.KeepAspectRatio,
            QtCore.Qt.TransformationMode.SmoothTransformation,
        )
        canvas = QtGui.QPixmap(scaled)
        painter = QtGui.QPainter(canvas)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        pen = QtGui.QPen(QtGui.QColor(0, 255, 120), 2)
        painter.setPen(pen)
        brush = QtGui.QBrush(QtGui.QColor(0, 255, 120))
        painter.setBrush(brush)
        sx = scaled.width() / max(self._pixmap.width(), 1)
        sy = scaled.height() / max(self._pixmap.height(), 1)
        for x, y in self._points:
            painter.drawEllipse(QtCore.QPointF(x * sx, y * sy), 4, 4)
        painter.end()
        self.setPixmap(canvas)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._refresh()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if self._pixmap is None or self._pixmap.isNull():
            return
        if event.button() != QtCore.Qt.MouseButton.LeftButton:
            return
        scaled = self._pixmap.scaled(
            self.size(),
            QtCore.Qt.AspectRatioMode.KeepAspectRatio,
            QtCore.Qt.TransformationMode.SmoothTransformation,
        )
        # Map click from label coords into pixmap coords.
        x_off = (self.width() - scaled.width()) / 2
        y_off = (self.height() - scaled.height()) / 2
        pos = event.position() if hasattr(event, "position") else event.localPos()
        lx = float(pos.x()) - x_off
        ly = float(pos.y()) - y_off
        if lx < 0 or ly < 0 or lx > scaled.width() or ly > scaled.height():
            return
        ix = lx * (self._pixmap.width() / max(scaled.width(), 1))
        iy = ly * (self._pixmap.height() / max(scaled.height(), 1))
        self._points.append((ix, iy))
        self._refresh()
        self.point_added.emit(ix, iy)


class MatAnyoneDialog(QtWidgets.QDialog):
    def __init__(self, clip, ignored_count: int = 0, parent=None):
        super().__init__(parent)
        self.setWindowTitle("MatAnyone 2")
        self.setMinimumWidth(560)
        self._result: DialogResult | None = None
        self._clip = clip

        layout = QtWidgets.QVBoxLayout(self)

        src = selection.clip_label(clip)
        if ignored_count:
            src += f"  (ignoring {ignored_count} other)"
        layout.addWidget(QtWidgets.QLabel(f"Source: {src}"))
        layout.addWidget(QtWidgets.QLabel("Engine: MatAnyone 2"))
        layout.addWidget(
            QtWidgets.QLabel("Max size: short side ≤ 1080 (fixed)")
        )

        try:
            import matanyone_runtime_paths as rpaths

            sam2_ready = rpaths.is_sam2_ready()
        except Exception:  # noqa: BLE001
            sam2_ready = False

        mask_box = QtWidgets.QGroupBox("Mask source")
        mask_layout = QtWidgets.QVBoxLayout(mask_box)
        self._mask_flame = QtWidgets.QRadioButton(
            "Flame (PNG / EXR file) — recommended"
        )
        if sam2_ready:
            sam_label = "SAM2 (click points after export)"
            hint_text = (
                "SAM2 is ready. After Run, click foreground points on the "
                "first-frame preview. Points on this dialog are optional."
            )
        else:
            sam_label = "SAM2 (requires DGpy → MatAnyone → SAM2 Setup…)"
            hint_text = (
                "SAM2 is not installed yet. Run DGpy → MatAnyone → SAM2 Setup… "
                "first (same runtime folder; no system packages), or use a "
                "Flame PNG/EXR mask."
            )
        self._mask_sam = QtWidgets.QRadioButton(sam_label)
        self._mask_flame.setChecked(True)
        mask_layout.addWidget(self._mask_flame)
        mask_layout.addWidget(self._mask_sam)

        row = QtWidgets.QHBoxLayout()
        self._mask_edit = QtWidgets.QLineEdit()
        self._mask_edit.setPlaceholderText("Path to first-frame mask…")
        browse = QtWidgets.QPushButton("Browse…")
        browse.clicked.connect(self._browse_mask)
        row.addWidget(self._mask_edit)
        row.addWidget(browse)
        mask_layout.addLayout(row)

        self._sam_preview = _SamPreview()
        mask_layout.addWidget(self._sam_preview)
        clear_pts = QtWidgets.QPushButton("Clear SAM points")
        clear_pts.clicked.connect(self._sam_preview.clear_points)
        mask_layout.addWidget(clear_pts)
        hint = QtWidgets.QLabel(hint_text)
        hint.setWordWrap(True)
        mask_layout.addWidget(hint)
        layout.addWidget(mask_box)

        out_box = QtWidgets.QGroupBox("Output")
        out_layout = QtWidgets.QFormLayout(out_box)
        self._kind = QtWidgets.QComboBox()
        self._kind.addItem("Alpha sequence", "alpha_sequence")
        self._kind.addItem("Alpha movie", "alpha_movie")
        out_layout.addRow("Kind", self._kind)
        self._fgr = QtWidgets.QCheckBox("Also write foreground")
        out_layout.addRow(self._fgr)
        self._import = QtWidgets.QCheckBox("Import to Flame")
        self._import.setChecked(True)
        out_layout.addRow(self._import)
        self._work = QtWidgets.QLineEdit()
        self._work.setPlaceholderText("/tmp/dgpy_matanyone/<job_id>/ (default)")
        out_layout.addRow("Work dir", self._work)
        layout.addWidget(out_box)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._mask_flame.toggled.connect(self._sync_mode)
        self._sync_mode()

    def _sync_mode(self) -> None:
        flame_mode = self._mask_flame.isChecked()
        self._mask_edit.setEnabled(flame_mode)

    def _browse_mask(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "First-frame mask",
            "",
            "Images (*.png *.exr *.jpg *.jpeg *.tif *.tiff);;All (*)",
        )
        if path:
            self._mask_edit.setText(path)

    def _accept(self) -> None:
        if self._mask_flame.isChecked():
            raw = self._mask_edit.text().strip()
            if not raw or not Path(raw).is_file():
                QtWidgets.QMessageBox.warning(
                    self, "MatAnyone", "Choose a valid mask image file."
                )
                return
            mask_path = Path(raw)
            mask_source = "flame"
            points: list[tuple[float, float]] = []
        else:
            mask_path = None
            mask_source = "sam2"
            points = self._sam_preview.points()

        work_raw = self._work.text().strip()
        work_dir = Path(work_raw).expanduser() if work_raw else None
        self._result = DialogResult(
            mask_source=mask_source,
            mask_path=mask_path,
            sam_points=points,
            output_kind=str(self._kind.currentData()),
            write_foreground=self._fgr.isChecked(),
            import_to_flame=self._import.isChecked(),
            work_dir=work_dir,
        )
        self.accept()

    def result_data(self) -> DialogResult | None:
        return self._result


class SamPointsDialog(QtWidgets.QDialog):
    """Collect foreground clicks on the exported first frame."""

    def __init__(self, image_path: Path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("MatAnyone — SAM2 points")
        self._points: list[tuple[float, float]] = []
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(
            QtWidgets.QLabel("Click the subject (foreground). Then OK.")
        )
        self._preview = _SamPreview()
        self._preview.set_image_path(image_path)
        layout.addWidget(self._preview)
        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._ok)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _ok(self) -> None:
        self._points = self._preview.points()
        if not self._points:
            QtWidgets.QMessageBox.warning(
                self, "MatAnyone", "Add at least one foreground point."
            )
            return
        self.accept()

    def points(self) -> list[tuple[float, float]]:
        return list(self._points)


def open_dialog(clip, ignored_count: int = 0) -> DialogResult | None:
    global _WINDOW
    dlg = MatAnyoneDialog(clip, ignored_count=ignored_count)
    _WINDOW = dlg
    if dlg.exec() != QtWidgets.QDialog.DialogCode.Accepted:
        return None
    return dlg.result_data()


def collect_sam_points(image_path: Path) -> list[tuple[float, float]] | None:
    dlg = SamPointsDialog(image_path)
    if dlg.exec() != QtWidgets.QDialog.DialogCode.Accepted:
        return None
    return dlg.points()
