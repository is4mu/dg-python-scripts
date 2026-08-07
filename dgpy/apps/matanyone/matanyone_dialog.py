"""MatAnyone mask-prep dialog (PySide6) — Flame / SAM2 tabs + ref frame."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

import matanyone_selection as selection

__version__ = "0.9.1"

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
    ref_frame_index: int = 0


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
        self._accept_clicks = clickable
        self._pixmap: QtGui.QPixmap | None = None
        self._mask_img: QtGui.QImage | None = None
        self._points: list[tuple[float, float]] = []

    def set_accept_clicks(self, enabled: bool) -> None:
        self._accept_clicks = bool(enabled and self._clickable)

    def set_image_path(
        self, path: Path | None, *, clear_overlay: bool = True
    ) -> None:
        if clear_overlay:
            self._points.clear()
            self._mask_img = None
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
        """Load an L/RGB mask; luminance becomes overlay alpha (not image alpha)."""
        if path is None or not path.is_file():
            self._mask_img = None
            self._refresh()
            return
        img = QtGui.QImage(str(path))
        if img.isNull():
            self._mask_img = None
        else:
            self._mask_img = img.convertToFormat(QtGui.QImage.Format.Format_Grayscale8)
        self._refresh()

    def points(self) -> list[tuple[float, float]]:
        return list(self._points)

    def clear_points(self) -> None:
        self._points.clear()
        self._mask_img = None
        self._refresh()

    def _mask_overlay(self, size: QtCore.QSize) -> QtGui.QPixmap | None:
        if self._mask_img is None or self._mask_img.isNull():
            return None
        gray = self._mask_img.scaled(
            size,
            QtCore.Qt.AspectRatioMode.IgnoreAspectRatio,
            QtCore.Qt.TransformationMode.FastTransformation,
        ).convertToFormat(QtGui.QImage.Format.Format_Grayscale8)
        w, h = gray.width(), gray.height()
        overlay = QtGui.QImage(w, h, QtGui.QImage.Format.Format_ARGB32)
        overlay.fill(QtCore.Qt.GlobalColor.transparent)
        # Preview-sized only (~520×292). Use pixelColor — safe under Flame's Qt.
        for y in range(h):
            for x in range(w):
                v = gray.pixelColor(x, y).value()
                if v < 16:
                    continue
                a = min(200, int(v * 0.7))
                overlay.setPixelColor(x, y, QtGui.QColor(0, 220, 120, a))
        return QtGui.QPixmap.fromImage(overlay)

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
        overlay = self._mask_overlay(scaled.size())
        if overlay is not None:
            painter.drawPixmap(0, 0, overlay)
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
        if not self._accept_clicks:
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
        source_video: Path,
        work_dir: Path,
        ignored_count: int = 0,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("MatAnyone 2")
        self.setMinimumWidth(640)
        self._result: DialogResult | None = None
        self._still = still_path
        self._video = source_video
        self._work = work_dir
        self._ref_dir = work_dir / "ref"
        self._ref_dir.mkdir(parents=True, exist_ok=True)
        self._ref_still = self._ref_dir / "ref_frame.png"
        self._sam_mask = work_dir / "mask_sam2.png"
        self._flame_mask: Path | None = None
        self._sam_busy = False
        self._frame_busy = False
        self._sam_thread: QtCore.QThread | None = None
        self._sam_worker: _SamMaskWorker | None = None
        self._pending_rerun = False
        self._points_at_run: list[tuple[float, float]] = []
        self._debounce = QtCore.QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(900)
        self._debounce.timeout.connect(self._run_sam2)
        self._frame_debounce = QtCore.QTimer(self)
        self._frame_debounce.setSingleShot(True)
        self._frame_debounce.setInterval(250)
        self._frame_debounce.timeout.connect(self._apply_ref_frame)

        try:
            import matanyone_runtime_paths as rpaths

            self._sam2_ready = rpaths.is_sam2_ready()
            self._python = rpaths.resolve_python() or "python3"
        except Exception:  # noqa: BLE001
            self._sam2_ready = False
            self._python = "python3"

        import matanyone_job as job

        try:
            self._frame_count = max(1, job.probe_frame_count(source_video, python=self._python))
        except Exception:  # noqa: BLE001
            self._frame_count = 1

        layout = QtWidgets.QVBoxLayout(self)
        src = selection.clip_label(clip)
        if ignored_count:
            src += f"  (ignoring {ignored_count} other)"
        layout.addWidget(QtWidgets.QLabel(f"Source: {src} (exported)"))
        layout.addWidget(QtWidgets.QLabel("Max size: short side ≤ 1080 (fixed)"))

        ref_row = QtWidgets.QHBoxLayout()
        ref_row.addWidget(QtWidgets.QLabel("Reference frame"))
        self._frame_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self._frame_slider.setMinimum(0)
        self._frame_slider.setMaximum(max(0, self._frame_count - 1))
        self._frame_slider.setValue(0)
        self._frame_slider.valueChanged.connect(self._on_frame_slider)
        ref_row.addWidget(self._frame_slider, 1)
        self._frame_spin = QtWidgets.QSpinBox()
        self._frame_spin.setMinimum(0)
        self._frame_spin.setMaximum(max(0, self._frame_count - 1))
        self._frame_spin.valueChanged.connect(self._on_frame_spin)
        ref_row.addWidget(self._frame_spin)
        self._frame_label = QtWidgets.QLabel(self._frame_caption(0))
        ref_row.addWidget(self._frame_label)
        layout.addLayout(ref_row)

        self._tabs = QtWidgets.QTabWidget()
        flame_page = QtWidgets.QWidget()
        flame_l = QtWidgets.QVBoxLayout(flame_page)
        row = QtWidgets.QHBoxLayout()
        self._mask_edit = QtWidgets.QLineEdit()
        self._mask_edit.setPlaceholderText(
            "Path to reference-frame mask (PNG / EXR)…"
        )
        browse = QtWidgets.QPushButton("Browse…")
        browse.clicked.connect(self._browse_mask)
        row.addWidget(self._mask_edit)
        row.addWidget(browse)
        flame_l.addLayout(row)
        flame_l.addWidget(
            QtWidgets.QLabel(
                "Mask overlays the source. Scrub the reference frame until they align."
            )
        )
        self._flame_preview = _ImagePreview(clickable=False)
        flame_l.addWidget(self._flame_preview, 1)
        self._tabs.addTab(flame_page, "Flame")

        sam_page = QtWidgets.QWidget()
        sam_l = QtWidgets.QVBoxLayout(sam_page)
        self._sam_preview = _ImagePreview(clickable=True)
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
        self._buttons = buttons
        self._ok_btn = buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._clear_btn = clear_pts
        self._set_sam_busy(False)

        # Seed previews from export still (frame 0) or extract if needed.
        if still_path.is_file():
            try:
                shutil.copy2(still_path, self._ref_still)
            except OSError:
                pass
        self._apply_ref_frame(force_index=0)

    def _frame_caption(self, index: int) -> str:
        last = max(0, self._frame_count - 1)
        return f"{index} / {last}"

    def _on_frame_slider(self, value: int) -> None:
        if self._frame_spin.value() != value:
            self._frame_spin.blockSignals(True)
            self._frame_spin.setValue(value)
            self._frame_spin.blockSignals(False)
        self._frame_label.setText(self._frame_caption(value))
        self._frame_debounce.start()

    def _on_frame_spin(self, value: int) -> None:
        if self._frame_slider.value() != value:
            self._frame_slider.blockSignals(True)
            self._frame_slider.setValue(value)
            self._frame_slider.blockSignals(False)
        self._frame_label.setText(self._frame_caption(value))
        self._frame_debounce.start()

    def _apply_ref_frame(self, force_index: int | None = None) -> None:
        import matanyone_job as job

        index = self._frame_slider.value() if force_index is None else force_index
        if force_index is not None:
            self._frame_slider.blockSignals(True)
            self._frame_spin.blockSignals(True)
            self._frame_slider.setValue(index)
            self._frame_spin.setValue(index)
            self._frame_slider.blockSignals(False)
            self._frame_spin.blockSignals(False)
            self._frame_label.setText(self._frame_caption(index))

        # Changing ref clears SAM points/mask (spec BE).
        self._debounce.stop()
        self._pending_rerun = False
        self._sam_preview.clear_points()
        if self._sam_mask.exists():
            try:
                self._sam_mask.unlink()
            except OSError:
                pass
        if self._sam2_ready:
            self._sam_status.setText(
                "Reference frame changed. Click the subject to generate a mask."
            )

        self._frame_busy = True
        if hasattr(self, "_ok_btn") and self._ok_btn is not None:
            self._ok_btn.setEnabled(False)
        try:
            def _log(_m: str) -> None:
                return

            job.extract_frame_at(
                self._video,
                index,
                self._ref_still,
                python=self._python,
                log=_log,
            )
            self._still = self._ref_still
            # Flame: keep mask overlay while swapping source.
            self._flame_preview.set_image_path(
                self._ref_still, clear_overlay=False
            )
            if self._flame_mask is not None:
                self._flame_preview.set_mask_path(self._flame_mask)
            self._sam_preview.set_image_path(self._ref_still, clear_overlay=True)
        except Exception as exc:  # noqa: BLE001
            QtWidgets.QMessageBox.warning(
                self, "MatAnyone", f"Could not extract frame {index}:\n{exc}"
            )
        finally:
            self._frame_busy = False
            if hasattr(self, "_ok_btn") and self._ok_btn is not None:
                self._ok_btn.setEnabled(not self._sam_busy)

    def _set_sam_busy(self, busy: bool) -> None:
        self._sam_busy = busy
        # Always allow placing more points (queued regenerate). Only lock OK.
        self._sam_preview.set_accept_clicks(self._sam2_ready)
        if hasattr(self, "_clear_btn") and self._clear_btn is not None:
            self._clear_btn.setEnabled(not busy)
        if hasattr(self, "_ok_btn") and self._ok_btn is not None:
            self._ok_btn.setEnabled(not busy and not self._frame_busy)
        self._frame_slider.setEnabled(not busy)
        self._frame_spin.setEnabled(not busy)
        if busy:
            self._tabs.setTabEnabled(0, False)
        else:
            self._tabs.setTabEnabled(0, True)
            if not self._sam2_ready:
                self._tabs.setTabEnabled(1, False)

    def _browse_mask(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Reference-frame mask",
            "",
            "Images (*.png *.exr *.jpg *.jpeg *.tif *.tiff);;All (*)",
        )
        if not path:
            return
        self._mask_edit.setText(path)
        self._flame_mask = Path(path)
        # Source stays; mask becomes overlay.
        if self._still.is_file():
            self._flame_preview.set_image_path(self._still, clear_overlay=False)
        self._flame_preview.set_mask_path(self._flame_mask)

    def _on_point(self, _x: float, _y: float) -> None:
        if not self._sam2_ready:
            return
        n = len(self._sam_preview.points())
        if self._sam_busy:
            self._pending_rerun = True
            self._sam_status.setText(
                f"SAM2: {n} point(s) — will regenerate after current run…"
            )
            return
        self._sam_status.setText(
            f"SAM2: {n} point(s) — mask updates after you pause clicking…"
        )
        self._debounce.start()

    def _clear_sam(self) -> None:
        if self._sam_busy:
            return
        self._debounce.stop()
        self._pending_rerun = False
        self._sam_preview.clear_points()
        if self._sam_mask.exists():
            try:
                self._sam_mask.unlink()
            except OSError:
                pass
        self._sam_status.setText("Click the subject. Mask updates automatically.")
        self._set_sam_busy(False)

    def _run_sam2(self) -> None:
        points = self._sam_preview.points()
        if not points:
            self._set_sam_busy(False)
            return
        if self._sam_busy:
            self._pending_rerun = True
            return
        self._points_at_run = list(points)
        self._pending_rerun = False
        self._sam_status.setText(f"SAM2: generating mask ({len(points)} points)…")
        self._set_sam_busy(True)
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
        mask = Path(str(path))
        self._sam_preview.set_mask_path(mask if mask.is_file() else None)
        self._set_sam_busy(False)
        current = self._sam_preview.points()
        if self._pending_rerun or current != getattr(self, "_points_at_run", current):
            self._pending_rerun = False
            self._sam_status.setText("SAM2: points changed — regenerating…")
            QtCore.QTimer.singleShot(0, self._run_sam2)
            return
        self._sam_status.setText("SAM2 mask ready. Add points to refine, then OK.")

    @QtCore.Slot(str)
    def _on_sam_err(self, message: str) -> None:
        self._pending_rerun = False
        self._sam_status.setText(f"SAM2 failed: {message}")
        self._set_sam_busy(False)
        QtWidgets.QMessageBox.warning(self, "MatAnyone", f"SAM2 mask failed:\n{message}")

    def _accept(self) -> None:
        if self._sam_busy or self._frame_busy:
            QtWidgets.QMessageBox.information(
                self, "MatAnyone", "Still busy. Wait a moment."
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
            ref_frame_index=int(self._frame_slider.value()),
        )
        self.accept()

    def result_data(self) -> DialogResult | None:
        return self._result


def open_mask_dialog(
    clip,
    *,
    still_path: Path,
    source_video: Path,
    work_dir: Path,
    ignored_count: int = 0,
) -> DialogResult | None:
    global _WINDOW
    dlg = MatAnyoneDialog(
        clip,
        still_path=still_path,
        source_video=source_video,
        work_dir=work_dir,
        ignored_count=ignored_count,
    )
    _WINDOW = dlg
    if dlg.exec() != QtWidgets.QDialog.DialogCode.Accepted:
        return None
    return dlg.result_data()
