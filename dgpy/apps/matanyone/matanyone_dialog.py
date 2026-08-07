"""MatAnyone mask-prep dialog (PySide6) — SAM2 + ref frame."""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

import matanyone_sam2 as sam
import matanyone_selection as selection

__version__ = "0.12.1"

_WINDOW: QtWidgets.QWidget | None = None

_TOOL_POS = "pos"
_TOOL_NEG = "neg"
_TOOL_PAINT_ADD = "paint_add"
_TOOL_PAINT_ERASE = "paint_erase"

_PAINT_NEUTRAL = 128


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


@dataclass
class _ObjSlot:
    """One SAM2 object: points + base / paint / composed edit."""

    name: str
    index: int
    points: list[tuple[float, float, int]] = field(default_factory=list)
    base: QtGui.QImage | None = None
    paint: QtGui.QImage | None = None
    edit: QtGui.QImage | None = None

    def obj_dir(self, work: Path) -> Path:
        return work / "sam_obj" / str(self.index)

    def paths(self, work: Path) -> tuple[Path, Path, Path]:
        d = self.obj_dir(work)
        return d / "base.png", d / "paint.png", d / "edit.png"

    def has_positive(self) -> bool:
        return any(int(p[2]) == 1 for p in self.points)

    def paint_dirty(self) -> bool:
        if self.paint is None or self.paint.isNull():
            return False
        img = self.paint
        for y in range(0, img.height(), 8):
            for x in range(0, img.width(), 8):
                if img.pixelColor(x, y).value() != _PAINT_NEUTRAL:
                    return True
        return False


def _blank_gray(w: int, h: int, value: int) -> QtGui.QImage:
    img = QtGui.QImage(w, h, QtGui.QImage.Format.Format_Grayscale8)
    img.fill(value)
    return img


def _compose_base_paint(base: QtGui.QImage, paint: QtGui.QImage) -> QtGui.QImage:
    """Compose SAM base with paint overlay (128=neutral, 255=fg, 0=bg).

    Used on OK / after SAM — not on every brush dab.
    """
    b = base.convertToFormat(QtGui.QImage.Format.Format_Grayscale8)
    p = paint.convertToFormat(QtGui.QImage.Format.Format_Grayscale8)
    w, h = b.width(), b.height()
    if p.width() != w or p.height() != h:
        p = p.scaled(
            w,
            h,
            QtCore.Qt.AspectRatioMode.IgnoreAspectRatio,
            QtCore.Qt.TransformationMode.FastTransformation,
        )
    out = b.copy()
    # Prefer scanline bytes when available (much faster than pixelColor).
    try:
        for y in range(h):
            out_mv = memoryview(out.scanLine(y)).cast("B")
            p_mv = memoryview(p.scanLine(y)).cast("B")
            for x in range(w):
                pv = p_mv[x]
                if pv >= 250:
                    out_mv[x] = 255
                elif pv <= 5:
                    out_mv[x] = 0
        return out
    except (TypeError, ValueError, BufferError):
        pass
    for y in range(h):
        for x in range(w):
            pv = p.pixelColor(x, y).value()
            if pv >= 250:
                out.setPixel(x, y, 255)
            elif pv <= 5:
                out.setPixel(x, y, 0)
    return out


def _or_edits(slots: list[_ObjSlot]) -> QtGui.QImage | None:
    images = [
        s.edit
        for s in slots
        if s.edit is not None and not s.edit.isNull()
    ]
    if not images:
        return None
    if len(images) == 1:
        return images[0]
    return sam.or_qimages(images)


class _ImagePreview(QtWidgets.QLabel):
    """Image preview with tool modes, ± points, paint drag, and mask overlay."""

    point_added = QtCore.Signal(float, float, int)
    paint_at = QtCore.Signal(float, float, bool)  # x, y, add
    paint_finished = QtCore.Signal()

    def __init__(self, *, interactive: bool = False, parent=None):
        super().__init__(parent)
        self.setMinimumSize(520, 292)
        self.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("background:#222; color:#aaa;")
        self.setText("No preview")
        self.setMouseTracking(True)
        self._interactive = interactive
        self._accept_input = interactive
        self._pixmap: QtGui.QPixmap | None = None
        self._mask_img: QtGui.QImage | None = None
        self._points: list[tuple[float, float, int]] = []
        self._tool = _TOOL_POS
        self._brush_radius = 20.0
        self._painting = False
        self._cursor_widget: QtCore.QPointF | None = None
        # Cached layout for paint/hit-testing (avoid re-scale every mouse move).
        self._scaled: QtGui.QPixmap | None = None
        self._x_off = 0.0
        self._y_off = 0.0
        self._sx = 1.0
        self._sy = 1.0

    def set_accept_input(self, enabled: bool) -> None:
        self._accept_input = bool(enabled and self._interactive)

    def set_tool(self, tool: str) -> None:
        self._tool = tool
        if tool not in (_TOOL_PAINT_ADD, _TOOL_PAINT_ERASE):
            self._cursor_widget = None
        self.update()

    def set_brush_radius(self, radius: float) -> None:
        self._brush_radius = max(1.0, float(radius))
        self.update()

    def set_image_path(
        self, path: Path | None, *, clear_overlay: bool = True
    ) -> None:
        if clear_overlay:
            self._points.clear()
            self._mask_img = None
        if path is None or not path.is_file():
            self._pixmap = None
            self._scaled = None
            self.setText("No preview")
            return
        pm = QtGui.QPixmap(str(path))
        self._pixmap = pm if not pm.isNull() else None
        if self._pixmap is None:
            self._scaled = None
            self.setText("Could not load image")
            return
        self._refresh()

    def set_mask_path(self, path: Path | None) -> None:
        if path is None or not path.is_file():
            self._mask_img = None
            self._refresh()
            return
        img = QtGui.QImage(str(path))
        if img.isNull():
            self._mask_img = None
        else:
            self._mask_img = img.convertToFormat(
                QtGui.QImage.Format.Format_Grayscale8
            )
        self._refresh()

    def set_mask_image(self, img: QtGui.QImage | None) -> None:
        if img is None or img.isNull():
            self._mask_img = None
        else:
            self._mask_img = img.convertToFormat(
                QtGui.QImage.Format.Format_Grayscale8
            )
        self._refresh()

    def points(self) -> list[tuple[float, float, int]]:
        return list(self._points)

    def set_points(self, points: list[tuple[float, float, int]]) -> None:
        self._points = [(float(x), float(y), int(lab)) for x, y, lab in points]
        self._refresh()

    def clear_points(self) -> None:
        self._points.clear()
        self._mask_img = None
        self._refresh()

    def _mask_overlay(self, size: QtCore.QSize) -> QtGui.QPixmap | None:
        """Fast green overlay via alpha channel (preview-sized only)."""
        if self._mask_img is None or self._mask_img.isNull():
            return None
        gray = self._mask_img.scaled(
            size,
            QtCore.Qt.AspectRatioMode.IgnoreAspectRatio,
            QtCore.Qt.TransformationMode.FastTransformation,
        ).convertToFormat(QtGui.QImage.Format.Format_Grayscale8)
        tint = QtGui.QImage(
            gray.size(), QtGui.QImage.Format.Format_ARGB32_Premultiplied
        )
        tint.fill(QtGui.QColor(0, 220, 120, 180))
        tint.setAlphaChannel(gray)
        return QtGui.QPixmap.fromImage(tint)

    def _rebuild_scaled_cache(self) -> QtGui.QPixmap | None:
        if self._pixmap is None or self._pixmap.isNull():
            self._scaled = None
            return None
        scaled = self._pixmap.scaled(
            self.size(),
            QtCore.Qt.AspectRatioMode.KeepAspectRatio,
            QtCore.Qt.TransformationMode.FastTransformation,
        )
        self._scaled = scaled
        self._x_off = (self.width() - scaled.width()) / 2
        self._y_off = (self.height() - scaled.height()) / 2
        self._sx = scaled.width() / max(self._pixmap.width(), 1)
        self._sy = scaled.height() / max(self._pixmap.height(), 1)
        return scaled

    def _image_xy(self, event) -> tuple[float, float] | None:
        if self._pixmap is None or self._pixmap.isNull():
            return None
        if self._scaled is None or self._scaled.isNull():
            self._rebuild_scaled_cache()
        if self._scaled is None:
            return None
        pos = event.position() if hasattr(event, "position") else event.localPos()
        lx = float(pos.x()) - self._x_off
        ly = float(pos.y()) - self._y_off
        if lx < 0 or ly < 0 or lx > self._scaled.width() or ly > self._scaled.height():
            return None
        ix = lx / max(self._sx, 1e-6)
        iy = ly / max(self._sy, 1e-6)
        return ix, iy

    def _refresh(self) -> None:
        if self._pixmap is None or self._pixmap.isNull():
            return
        scaled = self._rebuild_scaled_cache()
        if scaled is None:
            return
        canvas = QtGui.QPixmap(scaled)
        painter = QtGui.QPainter(canvas)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        overlay = self._mask_overlay(scaled.size())
        if overlay is not None:
            painter.drawPixmap(0, 0, overlay)
        if self._interactive:
            for x, y, lab in self._points:
                if int(lab) == 1:
                    color = QtGui.QColor(0, 255, 120)
                else:
                    color = QtGui.QColor(255, 64, 64)
                painter.setPen(QtGui.QPen(color, 2))
                painter.setBrush(QtGui.QBrush(color))
                painter.drawEllipse(
                    QtCore.QPointF(x * self._sx, y * self._sy), 4, 4
                )
        painter.end()
        self.setPixmap(canvas)

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        if not self._interactive:
            return
        if self._tool not in (_TOOL_PAINT_ADD, _TOOL_PAINT_ERASE):
            return
        if self._cursor_widget is None or self._scaled is None or self._scaled.isNull():
            return
        rx = self._brush_radius * max(self._sx, 1e-6)
        ry = self._brush_radius * max(self._sy, 1e-6)
        if self._tool == _TOOL_PAINT_ADD:
            color = QtGui.QColor(0, 255, 120, 220)
        else:
            color = QtGui.QColor(255, 72, 72, 220)
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        painter.setPen(QtGui.QPen(color, 1.5))
        painter.drawEllipse(self._cursor_widget, rx, ry)
        painter.end()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._scaled = None
        self._refresh()

    def leaveEvent(self, event) -> None:  # noqa: N802
        if self._cursor_widget is not None:
            self._cursor_widget = None
            self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if not self._accept_input:
            return
        if event.button() != QtCore.Qt.MouseButton.LeftButton:
            return
        xy = self._image_xy(event)
        if xy is None:
            return
        ix, iy = xy
        if self._tool in (_TOOL_PAINT_ADD, _TOOL_PAINT_ERASE):
            pos = event.position() if hasattr(event, "position") else event.localPos()
            self._cursor_widget = QtCore.QPointF(float(pos.x()), float(pos.y()))
            self._painting = True
            add = self._tool == _TOOL_PAINT_ADD
            self.paint_at.emit(ix, iy, add)
            self.update()
            return
        label = 1 if self._tool == _TOOL_POS else 0
        self._points.append((ix, iy, label))
        self._refresh()
        self.point_added.emit(ix, iy, label)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if not self._accept_input:
            return
        if self._tool in (_TOOL_PAINT_ADD, _TOOL_PAINT_ERASE):
            pos = event.position() if hasattr(event, "position") else event.localPos()
            xy = self._image_xy(event)
            if xy is None:
                if self._cursor_widget is not None:
                    self._cursor_widget = None
                    self.update()
            else:
                self._cursor_widget = QtCore.QPointF(
                    float(pos.x()), float(pos.y())
                )
                self.update()
            if (
                self._painting
                and (event.buttons() & QtCore.Qt.MouseButton.LeftButton)
                and xy is not None
            ):
                add = self._tool == _TOOL_PAINT_ADD
                self.paint_at.emit(xy[0], xy[1], add)
            return
        if self._cursor_widget is not None:
            self._cursor_widget = None
            self.update()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == QtCore.Qt.MouseButton.LeftButton and self._painting:
            self._painting = False
            self.paint_finished.emit()
        elif event.button() == QtCore.Qt.MouseButton.LeftButton:
            self._painting = False


class _BgCall(QtCore.QObject):
    """Run a blocking callable on a QThread."""

    finished_ok = QtCore.Signal(object)
    finished_err = QtCore.Signal(str)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self._fn = fn

    @QtCore.Slot()
    def run(self) -> None:
        try:
            self.finished_ok.emit(self._fn())
        except Exception as exc:  # noqa: BLE001
            self.finished_err.emit(str(exc))


class MatAnyoneDialog(QtWidgets.QDialog):
    """Mask preparation after export (SAM2-only)."""

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
        self.setMinimumWidth(720)
        self._result: DialogResult | None = None
        self._still = still_path
        self._video = source_video
        self._work = work_dir
        self._ref_dir = work_dir / "ref"
        self._ref_dir.mkdir(parents=True, exist_ok=True)
        self._ref_still = self._ref_dir / "ref_frame.png"
        self._sam_mask = work_dir / "mask_sam2.png"
        self._sam_busy = False
        self._frame_busy = False
        self._scrubbing = False
        self._full_ready_index: int | None = None
        self._frame_gen = 0
        self._frame_job_running = False
        self._want_proxy: tuple[int, int] | None = None  # index, gen
        self._want_full: tuple[int, int] | None = None
        self._frame_thread: QtCore.QThread | None = None
        self._finalizing = False
        self._pending_rerun = False
        self._points_at_run: list[tuple[float, float, int]] = []
        self._run_obj_index = 0
        self._bg_thread: QtCore.QThread | None = None
        self._bg_call: _BgCall | None = None

        self._worker: sam.Sam2Worker | None = None
        self._worker_ready = False
        self._worker_starting = False
        self._worker_failed = False
        self._image_on_worker: Path | None = None

        self._objects: list[_ObjSlot] = [_ObjSlot(name="Object 1", index=0)]
        self._active = 0

        self._debounce = QtCore.QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(300)
        self._debounce.timeout.connect(self._run_sam2_preview)
        self._paint_ui_timer = QtCore.QTimer(self)
        self._paint_ui_timer.setSingleShot(True)
        self._paint_ui_timer.setInterval(16)
        self._paint_ui_timer.timeout.connect(self._flush_paint_ui)
        self._proxy_timer = QtCore.QTimer(self)
        self._proxy_timer.setSingleShot(True)
        self._proxy_timer.setInterval(60)
        self._proxy_timer.timeout.connect(self._on_proxy_tick)
        self._settle_timer = QtCore.QTimer(self)
        self._settle_timer.setSingleShot(True)
        self._settle_timer.setInterval(200)
        self._settle_timer.timeout.connect(self._on_settle_tick)

        try:
            import matanyone_runtime_paths as rpaths

            self._rpaths = rpaths
            self._sam2_ready = rpaths.is_sam2_ready()
            self._python = rpaths.resolve_python() or "python3"
        except Exception:  # noqa: BLE001
            self._rpaths = None
            self._sam2_ready = False
            self._python = "python3"

        import matanyone_job as job

        try:
            self._frame_count = max(
                1, job.probe_frame_count(source_video, python=self._python)
            )
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

        sam_page = QtWidgets.QWidget()
        sam_l = QtWidgets.QVBoxLayout(sam_page)

        obj_row = QtWidgets.QHBoxLayout()
        obj_row.addWidget(QtWidgets.QLabel("Object"))
        self._obj_combo = QtWidgets.QComboBox()
        self._obj_combo.addItem("Object 1", 0)
        self._obj_combo.currentIndexChanged.connect(self._on_obj_combo)
        obj_row.addWidget(self._obj_combo, 1)
        self._obj_add = QtWidgets.QPushButton("+")
        self._obj_add.setFixedWidth(32)
        self._obj_add.clicked.connect(self._add_object)
        obj_row.addWidget(self._obj_add)
        self._obj_del = QtWidgets.QPushButton("−")
        self._obj_del.setFixedWidth(32)
        self._obj_del.clicked.connect(self._remove_object)
        obj_row.addWidget(self._obj_del)
        sam_l.addLayout(obj_row)

        tool_row = QtWidgets.QHBoxLayout()
        self._tool_group = QtWidgets.QButtonGroup(self)
        self._tool_group.setExclusive(True)
        for text, tool, tip in (
            ("+", _TOOL_POS, "Positive point"),
            ("−", _TOOL_NEG, "Negative point"),
            ("Paint Add", _TOOL_PAINT_ADD, "Paint foreground"),
            ("Paint Erase", _TOOL_PAINT_ERASE, "Paint background"),
        ):
            btn = QtWidgets.QToolButton()
            btn.setText(text)
            btn.setCheckable(True)
            btn.setToolTip(tip)
            btn.setProperty("sam_tool", tool)
            self._tool_group.addButton(btn)
            tool_row.addWidget(btn)
            if tool == _TOOL_POS:
                btn.setChecked(True)
        self._tool_group.buttonClicked.connect(self._on_tool_clicked)
        tool_row.addStretch(1)
        sam_l.addLayout(tool_row)

        brush_row = QtWidgets.QHBoxLayout()
        brush_row.addWidget(QtWidgets.QLabel("Brush"))
        self._brush_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self._brush_slider.setMinimum(2)
        self._brush_slider.setMaximum(80)
        self._brush_slider.setValue(20)
        self._brush_slider.valueChanged.connect(self._on_brush)
        brush_row.addWidget(self._brush_slider, 1)
        self._brush_label = QtWidgets.QLabel("20")
        brush_row.addWidget(self._brush_label)
        sam_l.addLayout(brush_row)

        self._sam_preview = _ImagePreview(interactive=True)
        self._sam_preview.point_added.connect(self._on_point)
        self._sam_preview.paint_at.connect(self._on_paint)
        self._sam_preview.paint_finished.connect(self._on_paint_finished)
        self._sam_preview.set_brush_radius(20)
        sam_l.addWidget(self._sam_preview, 1)

        clear_pts = QtWidgets.QPushButton("Clear points (active object)")
        clear_pts.clicked.connect(self._clear_active_points)
        sam_l.addWidget(clear_pts)
        self._clear_btn = clear_pts

        self._sam_status = QtWidgets.QLabel(
            "SAM2: + / − points and paint (tiny). OK combines object masks."
            if self._sam2_ready
            else "SAM2 is not set up. Run DGpy → MatAnyone → SAM2 Setup…"
        )
        self._sam_status.setWordWrap(True)
        sam_l.addWidget(self._sam_status)
        layout.addWidget(sam_page, 1)

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
        self._set_sam_busy(False)

        (self._ref_dir / "proxy").mkdir(parents=True, exist_ok=True)
        (self._ref_dir / "full").mkdir(parents=True, exist_ok=True)
        if still_path.is_file():
            full0 = self._full_cache_path(0)
            try:
                shutil.copy2(still_path, full0)
                shutil.copy2(still_path, self._ref_still)
            except OSError:
                pass
            if full0.is_file():
                self._still = full0
                self._full_ready_index = 0
                self._sam_preview.set_image_path(full0, clear_overlay=True)
        self._request_ref_index(0, force=True)

        if self._sam2_ready:
            QtCore.QTimer.singleShot(0, self._ensure_worker)

    # --- ref frame ---------------------------------------------------------

    def _frame_caption(self, index: int) -> str:
        last = max(0, self._frame_count - 1)
        return f"{index} / {last}"

    def _proxy_cache_path(self, index: int) -> Path:
        return self._ref_dir / "proxy" / f"{index:06d}.jpg"

    def _full_cache_path(self, index: int) -> Path:
        return self._ref_dir / "full" / f"{index:06d}.png"

    def _ref_input_ready(self) -> bool:
        return (
            not self._scrubbing
            and not self._frame_busy
            and self._full_ready_index is not None
            and self._full_ready_index == int(self._frame_slider.value())
            and self._still.is_file()
        )

    def _on_frame_slider(self, value: int) -> None:
        if self._frame_spin.value() != value:
            self._frame_spin.blockSignals(True)
            self._frame_spin.setValue(value)
            self._frame_spin.blockSignals(False)
        self._frame_label.setText(self._frame_caption(value))
        self._request_ref_index(value)

    def _on_frame_spin(self, value: int) -> None:
        if self._frame_slider.value() != value:
            self._frame_slider.blockSignals(True)
            self._frame_slider.setValue(value)
            self._frame_slider.blockSignals(False)
        self._frame_label.setText(self._frame_caption(value))
        self._request_ref_index(value)

    def _request_ref_index(self, index: int, *, force: bool = False) -> None:
        index = max(0, min(int(index), max(0, self._frame_count - 1)))
        if force:
            self._frame_slider.blockSignals(True)
            self._frame_spin.blockSignals(True)
            self._frame_slider.setValue(index)
            self._frame_spin.setValue(index)
            self._frame_slider.blockSignals(False)
            self._frame_spin.blockSignals(False)
            self._frame_label.setText(self._frame_caption(index))

        changed = self._full_ready_index != index
        self._debounce.stop()
        self._pending_rerun = False
        if changed or force:
            self._reset_all_objects(wipe_disk=False)
            self._image_on_worker = None
            if self._sam_mask.exists():
                try:
                    self._sam_mask.unlink()
                except OSError:
                    pass

        self._scrubbing = True
        self._frame_busy = True
        if self._sam2_ready and not self._worker_failed:
            self._sam_status.setText("Scrubbing…")
        self._set_sam_busy(False)

        # Cached full for this index → show immediately, still settle refresh.
        full = self._full_cache_path(index)
        if full.is_file():
            self._sam_preview.set_image_path(full, clear_overlay=True)
        else:
            proxy = self._proxy_cache_path(index)
            if proxy.is_file():
                self._sam_preview.set_image_path(proxy, clear_overlay=True)

        self._proxy_timer.start()
        self._settle_timer.start()

    def _on_proxy_tick(self) -> None:
        self._enqueue_frame(int(self._frame_slider.value()), "proxy")

    def _on_settle_tick(self) -> None:
        self._enqueue_frame(int(self._frame_slider.value()), "full")

    def _enqueue_frame(self, index: int, quality: str) -> None:
        self._frame_gen += 1
        gen = self._frame_gen
        if quality == "proxy":
            self._want_proxy = (index, gen)
        else:
            self._want_full = (index, gen)
        self._kick_frame_job()

    def _kick_frame_job(self) -> None:
        if self._frame_job_running:
            return
        # Full has priority so settle is not starved by proxy spam.
        if self._want_full is not None:
            index, gen = self._want_full
            self._want_full = None
            quality = "full"
        elif self._want_proxy is not None:
            index, gen = self._want_proxy
            self._want_proxy = None
            quality = "proxy"
        else:
            return
        self._frame_job_running = True

        video = self._video
        python = self._python
        proxy_path = self._proxy_cache_path(index)
        full_path = self._full_cache_path(index)

        def work():
            import matanyone_job as job

            def _log(_m: str) -> None:
                return

            if quality == "proxy":
                if not proxy_path.is_file():
                    job.extract_frame_at(
                        video,
                        index,
                        proxy_path,
                        python=python,
                        log=_log,
                        max_short_side=job.PROXY_SHORT_SIDE,
                    )
                return gen, index, quality, proxy_path
            if not full_path.is_file():
                job.extract_frame_at(
                    video,
                    index,
                    full_path,
                    python=python,
                    log=_log,
                    max_short_side=None,
                )
            return gen, index, quality, full_path

        def ok(result: object) -> None:
            self._frame_job_running = False
            try:
                _r_gen, r_index, r_quality, r_path = result  # type: ignore[misc]
            except Exception:  # noqa: BLE001
                self._kick_frame_job()
                return
            path = Path(str(r_path))
            current = int(self._frame_slider.value())
            if int(r_index) != current:
                self._kick_frame_job()
                return
            if not path.is_file():
                self._kick_frame_job()
                return
            if r_quality == "proxy":
                if self._full_ready_index == current and self._still.is_file():
                    self._kick_frame_job()
                    return
                self._sam_preview.set_image_path(path, clear_overlay=True)
                self._sam_status.setText(f"Scrubbing… frame {current}")
            else:
                self._still = path
                try:
                    shutil.copy2(path, self._ref_still)
                except OSError:
                    pass
                self._sam_preview.set_image_path(path, clear_overlay=True)
                self._full_ready_index = int(r_index)
                self._scrubbing = False
                self._frame_busy = False
                self._image_on_worker = None
                if self._sam2_ready and not self._worker_failed:
                    self._sam_status.setText(
                        "Reference ready. Click + / − or paint to generate a mask."
                    )
                self._set_sam_busy(False)
            self._kick_frame_job()

        def err(message: str) -> None:
            self._frame_job_running = False
            if message != "busy":
                self._sam_status.setText(f"Frame load failed: {message}")
                if quality == "full" and int(self._frame_slider.value()) == index:
                    self._scrubbing = False
                    self._frame_busy = False
                    self._set_sam_busy(False)
            self._kick_frame_job()

        self._run_frame_bg(work, ok, err)

    def _run_frame_bg(self, fn, on_ok, on_err) -> None:
        """Background extract path (separate from SAM2 `_run_bg`)."""
        self._frame_on_ok = on_ok
        self._frame_on_err = on_err
        thread = QtCore.QThread(self)
        call = _BgCall(fn)
        call.moveToThread(thread)
        thread.started.connect(call.run)
        call.finished_ok.connect(self._frame_bg_ok)
        call.finished_err.connect(self._frame_bg_err)
        call.finished_ok.connect(thread.quit)
        call.finished_err.connect(thread.quit)
        thread.finished.connect(call.deleteLater)
        thread.finished.connect(thread.deleteLater)

        def _clear() -> None:
            if self._frame_thread is thread:
                self._frame_thread = None

        thread.finished.connect(_clear)
        self._frame_thread = thread
        thread.start()

    @QtCore.Slot(object)
    def _frame_bg_ok(self, result: object) -> None:
        cb = getattr(self, "_frame_on_ok", None)
        self._frame_on_ok = None
        self._frame_on_err = None
        if cb is not None:
            cb(result)

    @QtCore.Slot(str)
    def _frame_bg_err(self, message: str) -> None:
        cb = getattr(self, "_frame_on_err", None)
        self._frame_on_ok = None
        self._frame_on_err = None
        if cb is not None:
            cb(message)

    # --- objects / tools ---------------------------------------------------

    def _active_slot(self) -> _ObjSlot:
        if not self._objects:
            self._objects = [_ObjSlot(name="Object 1", index=0)]
            self._active = 0
        self._active = max(0, min(self._active, len(self._objects) - 1))
        return self._objects[self._active]

    def _reset_all_objects(self, *, wipe_disk: bool = False) -> None:
        self._objects = [_ObjSlot(name="Object 1", index=0)]
        self._active = 0
        self._refresh_obj_combo()
        self._sam_preview.set_points([])
        self._sam_preview.set_mask_image(None)
        if wipe_disk:
            sam_root = self._work / "sam_obj"
            if sam_root.is_dir():
                try:
                    shutil.rmtree(sam_root)
                except OSError:
                    pass

    def _refresh_obj_combo(self) -> None:
        self._obj_combo.blockSignals(True)
        self._obj_combo.clear()
        for i, slot in enumerate(self._objects):
            self._obj_combo.addItem(slot.name, i)
        self._obj_combo.setCurrentIndex(self._active)
        self._obj_combo.blockSignals(False)
        self._obj_add.setEnabled(len(self._objects) < sam.MAX_OBJECTS)
        self._obj_del.setEnabled(len(self._objects) > 1)

    def _on_obj_combo(self, index: int) -> None:
        if index < 0 or index >= len(self._objects):
            return
        self._active = index
        slot = self._active_slot()
        self._sam_preview.set_points(slot.points)
        self._refresh_sam_overlay()

    def _add_object(self) -> None:
        if len(self._objects) >= sam.MAX_OBJECTS:
            return
        used = {s.index for s in self._objects}
        idx = 0
        while idx in used:
            idx += 1
        n = len(self._objects) + 1
        self._objects.append(_ObjSlot(name=f"Object {n}", index=idx))
        # Renumber display names 1..N
        for i, slot in enumerate(self._objects):
            slot.name = f"Object {i + 1}"
        self._active = len(self._objects) - 1
        self._refresh_obj_combo()
        self._sam_preview.set_points([])
        self._refresh_sam_overlay()

    def _remove_object(self) -> None:
        if len(self._objects) <= 1:
            return
        del self._objects[self._active]
        for i, slot in enumerate(self._objects):
            slot.name = f"Object {i + 1}"
        self._active = min(self._active, len(self._objects) - 1)
        self._refresh_obj_combo()
        slot = self._active_slot()
        self._sam_preview.set_points(slot.points)
        self._refresh_sam_overlay()

    def _on_tool_clicked(self, btn) -> None:
        tool = btn.property("sam_tool")
        if tool:
            self._sam_preview.set_tool(str(tool))

    def _on_brush(self, value: int) -> None:
        self._brush_label.setText(str(value))
        self._sam_preview.set_brush_radius(float(value))

    # --- worker lifecycle --------------------------------------------------

    def _ensure_worker(self) -> None:
        if (
            not self._sam2_ready
            or self._worker_ready
            or self._worker_starting
            or self._worker_failed
        ):
            return
        if self._rpaths is None:
            self._disable_sam2_ui("SAM2 paths unavailable")
            return
        self._worker_starting = True
        self._sam_status.setText("Starting SAM2 worker (tiny)…")
        rpaths = self._rpaths
        still = self._still

        def work():
            w = sam.Sam2Worker()
            w.start()
            w.init_model(
                rpaths.sam2_checkpoint_path(size="tiny"),
                rpaths.sam2_config_id(size="tiny"),
            )
            if still.is_file():
                w.set_image(still)
            return w

        self._run_bg(work, self._on_worker_started, self._on_worker_start_err)

    def _on_worker_started(self, worker: object) -> None:
        self._worker_starting = False
        self._worker = worker  # type: ignore[assignment]
        self._worker_ready = True
        self._image_on_worker = self._still if self._still.is_file() else None
        self._sam_status.setText(
            "SAM2 ready (tiny). Use + / − / paint, then OK."
        )
        self._set_sam_busy(False)

    def _on_worker_start_err(self, message: str) -> None:
        self._worker_starting = False
        self._worker_failed = True
        self._disable_sam2_ui(message)

    def _disable_sam2_ui(self, message: str) -> None:
        self._sam2_ready = False
        self._sam_status.setText(f"SAM2 worker failed: {message}")
        self._sam_preview.set_accept_input(False)
        if self._ok_btn is not None:
            self._ok_btn.setEnabled(False)
        QtWidgets.QMessageBox.warning(
            self, "MatAnyone", f"Could not start SAM2 worker:\n{message}"
        )

    def _shutdown_worker(self) -> None:
        self._debounce.stop()
        w = self._worker
        self._worker = None
        self._worker_ready = False
        if w is not None:
            try:
                w.close()
            except Exception:  # noqa: BLE001
                pass

    def closeEvent(self, event) -> None:  # noqa: N802
        self._proxy_timer.stop()
        self._settle_timer.stop()
        self._reset_all_objects(wipe_disk=True)
        self._shutdown_worker()
        super().closeEvent(event)

    def reject(self) -> None:
        self._proxy_timer.stop()
        self._settle_timer.stop()
        self._reset_all_objects(wipe_disk=True)
        self._shutdown_worker()
        super().reject()

    # --- busy / bg ---------------------------------------------------------

    def _set_sam_busy(self, busy: bool) -> None:
        self._sam_busy = busy
        lock = (
            busy
            or self._finalizing
            or self._frame_busy
            or self._scrubbing
            or not self._ref_input_ready()
        )
        self._sam_preview.set_accept_input(
            self._sam2_ready
            and self._worker_ready
            and not self._finalizing
            and self._ref_input_ready()
        )
        if self._clear_btn is not None:
            self._clear_btn.setEnabled(not lock)
        if self._ok_btn is not None:
            self._ok_btn.setEnabled(not lock and self._ref_input_ready())
        self._obj_combo.setEnabled(not self._finalizing and not self._scrubbing)
        self._obj_add.setEnabled(
            not lock and len(self._objects) < sam.MAX_OBJECTS
        )
        self._obj_del.setEnabled(not lock and len(self._objects) > 1)
        # Keep scrubbing the slider even while a frame loads.
        self._frame_slider.setEnabled(not self._finalizing)
        self._frame_spin.setEnabled(not self._finalizing)

    def _run_bg(self, fn, on_ok, on_err) -> None:
        """Serialize background calls (one QThread at a time)."""
        if self._bg_thread is not None and self._bg_thread.isRunning():
            on_err("busy")
            return
        self._bg_on_ok = on_ok
        self._bg_on_err = on_err
        thread = QtCore.QThread(self)
        call = _BgCall(fn)
        call.moveToThread(thread)
        thread.started.connect(call.run)
        call.finished_ok.connect(self._bg_finished_ok)
        call.finished_err.connect(self._bg_finished_err)
        call.finished_ok.connect(thread.quit)
        call.finished_err.connect(thread.quit)
        thread.finished.connect(call.deleteLater)
        thread.finished.connect(thread.deleteLater)

        def _clear() -> None:
            if self._bg_thread is thread:
                self._bg_thread = None
                self._bg_call = None

        thread.finished.connect(_clear)
        self._bg_thread = thread
        self._bg_call = call
        thread.start()

    @QtCore.Slot(object)
    def _bg_finished_ok(self, result: object) -> None:
        cb = getattr(self, "_bg_on_ok", None)
        self._bg_on_ok = None
        self._bg_on_err = None
        if cb is not None:
            cb(result)

    @QtCore.Slot(str)
    def _bg_finished_err(self, message: str) -> None:
        cb = getattr(self, "_bg_on_err", None)
        self._bg_on_ok = None
        self._bg_on_err = None
        if cb is not None:
            cb(message)

    # --- SAM preview / paint -----------------------------------------------

    def _on_point(self, x: float, y: float, label: int) -> None:
        if not self._worker_ready:
            return
        slot = self._active_slot()
        slot.points = self._sam_preview.points()
        # Re-SAM clears paint for this object (BY).
        self._reset_paint(slot)
        n = len(slot.points)
        if self._sam_busy:
            self._pending_rerun = True
            self._sam_status.setText(
                f"SAM2: {n} point(s) — will regenerate after current run…"
            )
            return
        self._sam_status.setText(
            f"SAM2: {n} point(s) — mask updates after you pause…"
        )
        self._debounce.start()

    def _reset_paint(self, slot: _ObjSlot) -> None:
        if slot.base is not None and not slot.base.isNull():
            w, h = slot.base.width(), slot.base.height()
            slot.paint = _blank_gray(w, h, _PAINT_NEUTRAL)
            slot.edit = slot.base.copy()
        else:
            slot.paint = None
            slot.edit = None
        self._refresh_sam_overlay()

    def _ensure_paint_layers(self, slot: _ObjSlot) -> bool:
        """Ensure base/paint/edit exist for painting. Returns False if no size."""
        if slot.edit is not None and not slot.edit.isNull():
            if slot.paint is None or slot.paint.isNull():
                slot.paint = _blank_gray(
                    slot.edit.width(), slot.edit.height(), _PAINT_NEUTRAL
                )
            if slot.base is None or slot.base.isNull():
                slot.base = _blank_gray(slot.edit.width(), slot.edit.height(), 0)
            return True
        if self._sam_preview._pixmap is None or self._sam_preview._pixmap.isNull():
            return False
        w = self._sam_preview._pixmap.width()
        h = self._sam_preview._pixmap.height()
        slot.base = _blank_gray(w, h, 0)
        slot.paint = _blank_gray(w, h, _PAINT_NEUTRAL)
        slot.edit = _blank_gray(w, h, 0)
        return True

    def _on_paint(self, x: float, y: float, add: bool) -> None:
        if not self._worker_ready or self._finalizing:
            return
        slot = self._active_slot()
        if not self._ensure_paint_layers(slot):
            return
        assert slot.edit is not None and slot.paint is not None
        r = float(self._brush_slider.value())
        sam.brush_edit_qimage(slot.edit, x, y, r, add=add)
        sam.brush_edit_qimage(slot.paint, x, y, r, add=add)
        # Coalesce UI refresh (~60fps); never write PNG while dragging.
        if not self._paint_ui_timer.isActive():
            self._paint_ui_timer.start()

    def _flush_paint_ui(self) -> None:
        self._refresh_sam_overlay()

    def _on_paint_finished(self) -> None:
        self._paint_ui_timer.stop()
        self._flush_paint_ui()
        slot = self._active_slot()
        self._persist_slot(slot)

    def _clear_active_points(self) -> None:
        if self._sam_busy or self._finalizing:
            return
        self._debounce.stop()
        self._pending_rerun = False
        slot = self._active_slot()
        slot.points.clear()
        slot.base = None
        slot.paint = None
        slot.edit = None
        self._sam_preview.set_points([])
        self._refresh_sam_overlay()
        self._sam_status.setText("Points cleared. Click + / − or paint.")
        self._set_sam_busy(False)

    def _refresh_sam_overlay(self) -> None:
        if len(self._objects) == 1:
            slot = self._objects[0]
            self._sam_preview.set_mask_image(slot.edit)
            return
        combined = _or_edits(self._objects)
        self._sam_preview.set_mask_image(combined)

    def _persist_slot(self, slot: _ObjSlot) -> None:
        base_p, paint_p, edit_p = slot.paths(self._work)
        try:
            if slot.base is not None and not slot.base.isNull():
                sam.save_qimage_l(slot.base, base_p)
            if slot.paint is not None and not slot.paint.isNull():
                sam.save_qimage_l(slot.paint, paint_p)
            if slot.edit is not None and not slot.edit.isNull():
                sam.save_qimage_l(slot.edit, edit_p)
        except Exception:  # noqa: BLE001
            pass

    def _run_sam2_preview(self) -> None:
        slot = self._active_slot()
        points = list(slot.points)
        if not points or not slot.has_positive():
            self._set_sam_busy(False)
            if points and not slot.has_positive():
                self._sam_status.setText(
                    "Add at least one positive (+) point before SAM predicts."
                )
            return
        if not self._worker_ready or self._worker is None:
            self._ensure_worker()
            self._pending_rerun = True
            return
        if self._sam_busy or (
            self._bg_thread is not None and self._bg_thread.isRunning()
        ):
            self._pending_rerun = True
            return
        self._points_at_run = list(points)
        self._run_obj_index = self._active
        self._pending_rerun = False
        self._sam_status.setText(
            f"SAM2: generating preview ({len(points)} points)…"
        )
        self._set_sam_busy(True)
        worker = self._worker
        still = self._still
        out = slot.paths(self._work)[0]
        out.parent.mkdir(parents=True, exist_ok=True)
        need_set = self._image_on_worker != still

        def work():
            if need_set:
                worker.set_image(still)
            return worker.predict(points, out)

        def ok(path: object) -> None:
            self._image_on_worker = still
            self._on_preview_ok(Path(str(path)))

        def err(message: str) -> None:
            if message == "busy":
                self._pending_rerun = True
                return
            self._on_preview_err(message)

        self._run_bg(work, ok, err)

    def _on_preview_ok(self, path: Path) -> None:
        idx = self._run_obj_index
        if 0 <= idx < len(self._objects):
            slot = self._objects[idx]
            try:
                base = sam.load_qimage_l(path)
            except Exception as exc:  # noqa: BLE001
                self._on_preview_err(str(exc))
                return
            slot.base = base
            # Paint was reset on point change; keep neutral overlay.
            slot.paint = _blank_gray(base.width(), base.height(), _PAINT_NEUTRAL)
            slot.edit = base.copy()
            self._persist_slot(slot)
        self._refresh_sam_overlay()
        self._set_sam_busy(False)
        slot_now = self._active_slot()
        current = list(slot_now.points)
        if self._pending_rerun or current != getattr(
            self, "_points_at_run", current
        ):
            self._pending_rerun = False
            self._sam_status.setText("SAM2: points changed — regenerating…")
            QtCore.QTimer.singleShot(0, self._run_sam2_preview)
            return
        self._sam_status.setText(
            "SAM2 preview ready. Refine with ± / paint, then OK."
        )

    def _on_preview_err(self, message: str) -> None:
        self._pending_rerun = False
        self._sam_status.setText(f"SAM2 failed: {message}")
        self._set_sam_busy(False)
        QtWidgets.QMessageBox.warning(
            self, "MatAnyone", f"SAM2 mask failed:\n{message}"
        )

    # --- accept / finalize -------------------------------------------------

    def _accept(self) -> None:
        if self._sam_busy or self._frame_busy or self._finalizing or self._scrubbing:
            QtWidgets.QMessageBox.information(
                self, "MatAnyone", "Still busy. Wait a moment."
            )
            return
        if not self._ref_input_ready():
            QtWidgets.QMessageBox.information(
                self,
                "MatAnyone",
                "Wait for the reference frame to finish loading.",
            )
            return

        if not self._sam2_ready or not self._worker_ready or self._worker is None:
            QtWidgets.QMessageBox.warning(
                self,
                "MatAnyone",
                "SAM2 is not ready.\nRun DGpy → MatAnyone → SAM2 Setup…",
            )
            return
        usable = [
            s
            for s in self._objects
            if s.has_positive()
            or (s.edit is not None and not s.edit.isNull())
        ]
        if not usable:
            QtWidgets.QMessageBox.warning(
                self,
                "MatAnyone",
                "Generate a SAM2 mask first (+ points and/or paint).",
            )
            return

        self._finalizing = True
        self._set_sam_busy(True)
        self._sam_status.setText("Finalizing mask…")
        slots_snapshot = list(self._objects)
        work = self._work
        worker = self._worker
        still = self._still
        need_set = self._image_on_worker != still

        def work_fn():
            assert worker is not None
            if need_set and still.is_file():
                worker.set_image(still)
            edits: list[QtGui.QImage] = []
            for slot in slots_snapshot:
                base_p, paint_p, edit_p = slot.paths(work)
                base_p.parent.mkdir(parents=True, exist_ok=True)
                if slot.edit is not None and not slot.edit.isNull():
                    sam.save_qimage_l(slot.edit, edit_p)
                    edits.append(slot.edit)
                    continue
                if not slot.has_positive():
                    continue
                # Points exist but preview edit missing — one tiny predict.
                worker.predict(list(slot.points), base_p)
                base = sam.load_qimage_l(base_p)
                if slot.paint is not None and not slot.paint.isNull():
                    paint = slot.paint
                elif paint_p.is_file():
                    paint = sam.load_qimage_l(paint_p)
                else:
                    paint = _blank_gray(
                        base.width(), base.height(), _PAINT_NEUTRAL
                    )
                edit = _compose_base_paint(base, paint)
                sam.save_qimage_l(base, base_p)
                sam.save_qimage_l(paint, paint_p)
                sam.save_qimage_l(edit, edit_p)
                edits.append(edit)
            if not edits:
                raise RuntimeError("no object masks to combine")
            combined = edits[0] if len(edits) == 1 else sam.or_qimages(edits)
            out = work / "mask.png"
            sam.save_qimage_l(combined, out)
            sam.save_qimage_l(combined, work / "mask_sam2.png")
            return out

        def ok(path: object) -> None:
            self._finalizing = False
            if need_set:
                self._image_on_worker = still
            dest_path = Path(str(path))
            # Positives from active object for JobOptions compat (xy only).
            active = self._active_slot()
            points = [
                (float(x), float(y))
                for x, y, lab in active.points
                if int(lab) == 1
            ]
            self._finish_accept("sam2", dest_path, points)

        def err(message: str) -> None:
            self._finalizing = False
            self._set_sam_busy(False)
            self._sam_status.setText(f"Finalize failed: {message}")
            QtWidgets.QMessageBox.warning(
                self, "MatAnyone", f"Final mask failed:\n{message}"
            )

        self._run_bg(work_fn, ok, err)

    def _finish_accept(
        self,
        mask_source: str,
        dest: Path,
        points: list[tuple[float, float]],
    ) -> None:
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
        self._shutdown_worker()
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
    try:
        if dlg.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return None
        return dlg.result_data()
    finally:
        # Belt-and-suspenders if reject path missed shutdown.
        if hasattr(dlg, "_shutdown_worker"):
            dlg._shutdown_worker()
