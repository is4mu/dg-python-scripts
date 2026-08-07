"""MatAnyone mask-prep dialog (PySide6) — Flame / SAM2 tabs."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

import matanyone_selection as selection

__version__ = "0.6.0"

_WINDOW: QtWidgets.QWidget | None = None


@dataclass
class DialogResult:
    mask_source: str
    mask_path: Path
    sam_points: list[tuple[float, float]]
    output_kind: str
    write_foreground: bool
    import_to_flame: bool
    work_dir: Path | None


class _ImagePreview(QtWidgets.QLabel):
    """Image preview with optional clickable points and mask overlay."""

    point_added = QtCore.Signal(float, float)

    def __init__(self, *, clickable: bool = False, parent=None):
        super().__init__(parent)
        self.setMinimumSize(520, 292)
        self.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("background:#222; color:#aaa;")
        self.setText("No preview")
        self._clickable = clickable
        self._pixmap: QtGui.QPixmap | None = None
        self._mask: QtGui.QPixmap | None = None
        self._points: list[tuple[float, float]] = []

    def set_image_path(self, path: Path | None) -> None:
        self._points.clear()
        self._mask = None
        if path is None or not path.is_file():
            self._pixmap = None
            self.setText("No preview")
            return
        pm = QtGui.QPixmap(str(path))
        self._pixmap = pm if not pm.isNull() else None
        if self._pixmap is None:
            self.setText("Could not load image")
            return
        self._refresh()

    def set_mask_path(self, path: Path | None) -> None:
        if path is None or not path.is_file():
            self._mask = None
        else:
            pm = QtGui.QPixmap(str(path))
            self._mask = pm if not pm.isNull() else None
        self._refresh()

    def points(self) -> list[tuple[float, float]]:
        return list(self._points)

    def clear_points(self) -> None:
        self._points.clear()
        self._mask = None
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
        if self._mask is not None and not self._mask.isNull():
            mask_s = self._mask.scaled(
                scaled.size(),
                QtCore.Qt.AspectRatioMode.IgnoreAspectRatio,
                QtCore.Qt.TransformationMode.SmoothTransformation,
            )
            painter.setOpacity(0.45)
            # Tint mask green via CompositionMode
            tinted = QtGui.QPixmap(mask_s.size())
            tinted.fill(QtCore.Qt.GlobalColor.transparent)
            tp = QtGui.QPainter(tinted)
            tp.drawPixmap(0, 0, mask_s)
            tp.setCompositionMode(
                QtGui.QPainter.CompositionMode.CompositionMode_SourceIn
            )
            tp.fillRect(tinted.rect(), QtGui.QColor(0, 220, 120, 200))
            tp.end()
            painter.drawPixmap(0, 0, tinted)
            painter.setOpacity(1.0)
        if self._clickable:
            pen = QtGui.QPen(QtGui.QColor(0, 255, 120), 2)
            painter.setPen(pen)
            painter.setBrush(QtGui.QBrush(QtGui.QColor(0, 255, 120)))
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
        if not self._clickable:
            return
        if self._pixmap is None or self._pixmap.isNull():
            return
        if event.button() != QtCore.Qt.MouseButton.LeftButton:
            return
        scaled = self._pixmap.scaled(
            self.size(),
            QtCore.Qt.AspectRatioMode.KeepAspectRatio,
            QtCore.Qt.TransformationMode.SmoothTransformation,
        )
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


class _SamMaskWorker(QtCore.QObject):
    finished_ok = QtCore.Signal(object)  # Path
    finished_err = QtCore.Signal(str)

    def __init__(
        self,
        *,
        still: Path,
        points: list[tuple[float, float]],
        out_mask: Path,
        work: Path,
    ):
        super().__init__()
        self._still = still
        self._points = points
        self._out = out_mask
        self._work = work

    @QtCore.Slot()
    def run(self) -> None:
        try:
            import matanyone_job as job
            import matanyone_runtime_paths as rpaths
            import matanyone_runtime_setup as rsetup

            python = rpaths.resolve_python()
            sam = rpaths.sam_script()
            if not python or sam is None:
                raise RuntimeError("SAM2 helper / python missing")
            rsetup._write_sam_helper(sam)
            logs: list[str] = []

            def _log(m: str) -> None:
                logs.append(m)

            job.run_sam_mask(
                python=python,
                sam_script=sam,
                image=self._still,
                points=self._points,
                out_mask=self._out,
                checkpoint=rpaths.sam2_checkpoint_path(),
                config=rpaths.sam2_config_id(),
                cwd=self._work,
                log=_log,
            )
            self.finished_ok.emit(self._out)
        except Exception as exc:  # noqa: BLE001
            self.finished_err.emit(str(exc))


class MatAnyoneDialog(QtWidgets.QDialog):
    """Mask preparation after export."""

    def __init__(
        self,
        clip,
        *,
        still_path: Path,
        work_dir: Path,
        ignored_count: int = 0,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("MatAnyone 2")
        self.setMinimumWidth(640)
        self._result: DialogResult | None = None
        self._still = still_path
        self._work = work_dir
        self._sam_mask = work_dir / "mask_sam2.png"
        self._flame_mask: Path | None = None
        self._sam_busy = False
        self._sam_thread: QtCore.QThread | None = None
        self._sam_worker: _SamMaskWorker | None = None
        self._debounce = QtCore.QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(350)
        self._debounce.timeout.connect(self._run_sam2)

        try:
            import matanyone_runtime_paths as rpaths

            self._sam2_ready = rpaths.is_sam2_ready()
        except Exception:  # noqa: BLE001
            self._sam2_ready = False

        layout = QtWidgets.QVBoxLayout(self)
        src = selection.clip_label(clip)
        if ignored_count:
            src += f"  (ignoring {ignored_count} other)"
        layout.addWidget(QtWidgets.QLabel(f"Source: {src} (exported)"))
        layout.addWidget(QtWidgets.QLabel("Max size: short side ≤ 1080 (fixed)"))

        self._tabs = QtWidgets.QTabWidget()
        flame_page = QtWidgets.QWidget()
        flame_l = QtWidgets.QVBoxLayout(flame_page)
        row = QtWidgets.QHBoxLayout()
        self._mask_edit = QtWidgets.QLineEdit()
        self._mask_edit.setPlaceholderText("Path to first-frame mask (PNG / EXR)…")
        browse = QtWidgets.QPushButton("Browse…")
        browse.clicked.connect(self._browse_mask)
        row.addWidget(self._mask_edit)
        row.addWidget(browse)
        flame_l.addLayout(row)
        self._flame_preview = _ImagePreview(clickable=False)
        flame_l.addWidget(self._flame_preview, 1)
        self._tabs.addTab(flame_page, "Flame")

        sam_page = QtWidgets.QWidget()
        sam_l = QtWidgets.QVBoxLayout(sam_page)
        self._sam_preview = _ImagePreview(clickable=True)
        self._sam_preview.set_image_path(still_path if still_path.is_file() else None)
        self._sam_preview.point_added.connect(self._on_point)
        sam_l.addWidget(self._sam_preview, 1)
        clear_pts = QtWidgets.QPushButton("Clear points")
        clear_pts.clicked.connect(self._clear_sam)
        sam_l.addWidget(clear_pts)
        self._sam_status = QtWidgets.QLabel(
            "Click the subject. Mask updates automatically."
            if self._sam2_ready
            else "SAM2 is not set up. Run DGpy → MatAnyone → SAM2 Setup…"
        )
        self._sam_status.setWordWrap(True)
        sam_l.addWidget(self._sam_status)
        self._tabs.addTab(sam_page, "SAM2")
        if not self._sam2_ready:
            self._tabs.setTabEnabled(1, False)
            self._tabs.setTabToolTip(
                1, "Run DGpy → MatAnyone → SAM2 Setup… to enable this tab."
            )
        layout.addWidget(self._tabs, 1)

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
        self._work_edit = QtWidgets.QLineEdit(str(work_dir))
        self._work_edit.setReadOnly(True)
        out_layout.addRow("Work dir", self._work_edit)
        layout.addWidget(out_box)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _browse_mask(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "First-frame mask",
            "",
            "Images (*.png *.exr *.jpg *.jpeg *.tif *.tiff);;All (*)",
        )
        if not path:
            return
        self._mask_edit.setText(path)
        self._flame_mask = Path(path)
        self._flame_preview.set_image_path(self._flame_mask)

    def _on_point(self, _x: float, _y: float) -> None:
        if not self._sam2_ready or self._sam_busy:
            return
        self._sam_status.setText("SAM2: updating mask…")
        self._debounce.start()

    def _clear_sam(self) -> None:
        self._debounce.stop()
        self._sam_preview.clear_points()
        if self._sam_mask.exists():
            try:
                self._sam_mask.unlink()
            except OSError:
                pass
        self._sam_status.setText("Click the subject. Mask updates automatically.")

    def _run_sam2(self) -> None:
        points = self._sam_preview.points()
        if not points or self._sam_busy:
            return
        self._sam_busy = True
        self._sam_status.setText("SAM2: generating mask…")
        self._sam_thread = QtCore.QThread(self)
        self._sam_worker = _SamMaskWorker(
            still=self._still,
            points=points,
            out_mask=self._sam_mask,
            work=self._work,
        )
        self._sam_worker.moveToThread(self._sam_thread)
        self._sam_thread.started.connect(self._sam_worker.run)
        self._sam_worker.finished_ok.connect(self._on_sam_ok)
        self._sam_worker.finished_err.connect(self._on_sam_err)
        self._sam_worker.finished_ok.connect(self._sam_thread.quit)
        self._sam_worker.finished_err.connect(self._sam_thread.quit)
        self._sam_thread.finished.connect(self._sam_worker.deleteLater)
        self._sam_thread.start()

    @QtCore.Slot(object)
    def _on_sam_ok(self, path: object) -> None:
        self._sam_busy = False
        mask = Path(str(path))
        self._sam_preview.set_mask_path(mask if mask.is_file() else None)
        self._sam_status.setText("SAM2 mask ready. Add points to refine, then OK.")

    @QtCore.Slot(str)
    def _on_sam_err(self, message: str) -> None:
        self._sam_busy = False
        self._sam_status.setText(f"SAM2 failed: {message}")
        QtWidgets.QMessageBox.warning(self, "MatAnyone", f"SAM2 mask failed:\n{message}")

    def _accept(self) -> None:
        if self._sam_busy:
            QtWidgets.QMessageBox.information(
                self, "MatAnyone", "SAM2 is still generating. Wait a moment."
            )
            return
        tab = self._tabs.currentIndex()
        dest = self._work / "mask.png"
        if tab == 0:
            raw = self._mask_edit.text().strip()
            if not raw or not Path(raw).is_file():
                QtWidgets.QMessageBox.warning(
                    self, "MatAnyone", "Choose a valid mask image on the Flame tab."
                )
                return
            src = Path(raw)
            if src.resolve() != dest.resolve():
                shutil.copy2(src, dest)
            mask_source = "flame"
            points: list[tuple[float, float]] = []
        else:
            if not self._sam2_ready:
                QtWidgets.QMessageBox.warning(
                    self,
                    "MatAnyone",
                    "SAM2 is not set up.\nRun DGpy → MatAnyone → SAM2 Setup…",
                )
                return
            if not self._sam_mask.is_file():
                QtWidgets.QMessageBox.warning(
                    self,
                    "MatAnyone",
                    "Generate a SAM2 mask first (click points on the preview).",
                )
                return
            shutil.copy2(self._sam_mask, dest)
            mask_source = "sam2"
            points = self._sam_preview.points()

        self._result = DialogResult(
            mask_source=mask_source,
            mask_path=dest,
            sam_points=points,
            output_kind=str(self._kind.currentData()),
            write_foreground=self._fgr.isChecked(),
            import_to_flame=self._import.isChecked(),
            work_dir=self._work,
        )
        self.accept()

    def result_data(self) -> DialogResult | None:
        return self._result


def open_mask_dialog(
    clip,
    *,
    still_path: Path,
    work_dir: Path,
    ignored_count: int = 0,
) -> DialogResult | None:
    global _WINDOW
    dlg = MatAnyoneDialog(
        clip,
        still_path=still_path,
        work_dir=work_dir,
        ignored_count=ignored_count,
    )
    _WINDOW = dlg
    if dlg.exec() != QtWidgets.QDialog.DialogCode.Accepted:
        return None
    return dlg.result_data()
