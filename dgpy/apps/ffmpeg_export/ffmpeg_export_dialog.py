"""DG2: Export dialog — preset-first, progressive details. PySide6 only."""

from __future__ import annotations

from pathlib import Path

from PySide6 import QtCore, QtWidgets

import dgpy_gui
import dgpy_log
from ffmpeg_export_paths import preview_path
from ffmpeg_export_presets import (
    ExportPreset,
    all_presets,
    default_preset,
    save_user_preset,
)
from ffmpeg_export_selection import ExportSource, resolve_export_sources

__version__ = "0.1.0"

_WINDOW: QtWidgets.QWidget | None = None

_SESSION: dict = {
    "destination": str(Path.home() / "Desktop"),
    "filename": "<name>",
    "preset_id": "review_h264_hq",
    "keep_structure": True,
    "conflict": "suffix",
}


def _ensure_runtime() -> None:
    import sys

    import dgpy_paths

    runtime = dgpy_paths.dgpy_root() / "apps" / "ffmpeg_runtime"
    if runtime.is_dir() and str(runtime) not in sys.path:
        sys.path.insert(0, str(runtime))


class _ExportWorker(QtCore.QThread):
    progress = QtCore.Signal(int, int, str)
    finished_ok = QtCore.Signal(object)
    failed = QtCore.Signal(str)

    def __init__(self, kwargs: dict, parent=None):
        super().__init__(parent)
        self._kwargs = kwargs
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        try:
            import ffmpeg_export_job

            def progress(done, total, msg):
                self.progress.emit(done, total, msg)

            result = ffmpeg_export_job.run_export(
                **self._kwargs,
                progress=progress,
                should_cancel=lambda: self._cancel,
            )
            self.finished_ok.emit(result)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class ExportDialog(QtWidgets.QDialog):
    def __init__(self, sources: list[ExportSource], parent=None):
        super().__init__(parent)
        self.setWindowTitle("DG2: Export")
        self.setMinimumSize(780, 480)
        self._sources = sources
        self._presets = all_presets()
        self._preset = self._load_session_preset()
        self._worker: _ExportWorker | None = None
        self._modified = False

        _ensure_runtime()
        import ffmpeg_runtime_resolve

        self._runtime = ffmpeg_runtime_resolve

        root = QtWidgets.QVBoxLayout(self)

        # Top: preset + runtime
        top = QtWidgets.QHBoxLayout()
        top.addWidget(QtWidgets.QLabel("Preset:"))
        self.preset_combo = QtWidgets.QComboBox()
        for p in self._presets:
            self.preset_combo.addItem(p.label, p.id)
        idx = self.preset_combo.findData(self._preset.id)
        if idx >= 0:
            self.preset_combo.setCurrentIndex(idx)
        self.preset_combo.currentIndexChanged.connect(self._on_preset_changed)
        top.addWidget(self.preset_combo, 1)

        self.save_preset_btn = QtWidgets.QPushButton("Save As…")
        self.save_preset_btn.clicked.connect(self._save_preset_as)
        top.addWidget(self.save_preset_btn)

        self.runtime_label = QtWidgets.QLabel(self._runtime.status_line())
        self.runtime_label.setStyleSheet("color: #aaa;")
        top.addWidget(self.runtime_label)
        root.addLayout(top)

        self.keep_check = QtWidgets.QCheckBox("Keep folder structure")
        self.keep_check.setChecked(bool(_SESSION.get("keep_structure", True)))
        self.keep_check.toggled.connect(self._refresh_preview)
        root.addWidget(self.keep_check)

        # Body: sources | output
        body = QtWidgets.QHBoxLayout()

        left = QtWidgets.QVBoxLayout()
        self.sources_label = QtWidgets.QLabel()
        left.addWidget(self.sources_label)
        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderLabels(["Sources"])
        self.tree.setColumnCount(1)
        self.tree.itemChanged.connect(self._on_tree_item_changed)
        left.addWidget(self.tree, 1)
        body.addLayout(left, 1)

        right = QtWidgets.QVBoxLayout()
        form = QtWidgets.QFormLayout()
        dest_row = QtWidgets.QHBoxLayout()
        self.dest_edit = QtWidgets.QLineEdit(_SESSION.get("destination", ""))
        self.dest_edit.textChanged.connect(self._refresh_preview)
        browse = QtWidgets.QPushButton("…")
        browse.setFixedWidth(32)
        browse.clicked.connect(self._browse_dest)
        dest_row.addWidget(self.dest_edit, 1)
        dest_row.addWidget(browse)
        form.addRow("Destination:", dest_row)

        self.name_edit = QtWidgets.QLineEdit(_SESSION.get("filename", "<name>"))
        self.name_edit.textChanged.connect(self._refresh_preview)
        form.addRow("Filename:", self.name_edit)

        self.conflict_combo = QtWidgets.QComboBox()
        self.conflict_combo.addItem("Add suffix", "suffix")
        self.conflict_combo.addItem("Skip existing", "skip")
        cidx = self.conflict_combo.findData(_SESSION.get("conflict", "suffix"))
        if cidx >= 0:
            self.conflict_combo.setCurrentIndex(cidx)
        form.addRow("Conflict:", self.conflict_combo)
        right.addLayout(form)

        self.preview_label = QtWidgets.QLabel("")
        self.preview_label.setWordWrap(True)
        self.preview_label.setStyleSheet("color: #9ab;")
        right.addWidget(self.preview_label)

        self.summary_label = QtWidgets.QLabel()
        self.summary_label.setWordWrap(True)
        right.addWidget(self.summary_label)

        self.details = QtWidgets.QGroupBox("Details")
        self.details.setCheckable(True)
        self.details.setChecked(False)
        details_form = QtWidgets.QFormLayout(self.details)
        self.container_edit = QtWidgets.QLineEdit()
        self.vcodec_edit = QtWidgets.QLineEdit()
        self.acodec_edit = QtWidgets.QLineEdit()
        self.crf_spin = QtWidgets.QSpinBox()
        self.crf_spin.setRange(0, 51)
        self.scale_edit = QtWidgets.QLineEdit()
        self.fps_edit = QtWidgets.QLineEdit()
        for w in (
            self.container_edit,
            self.vcodec_edit,
            self.acodec_edit,
            self.scale_edit,
            self.fps_edit,
        ):
            w.textChanged.connect(self._mark_modified)
        self.crf_spin.valueChanged.connect(self._mark_modified)
        details_form.addRow("Container:", self.container_edit)
        details_form.addRow("Video codec:", self.vcodec_edit)
        details_form.addRow("Audio codec:", self.acodec_edit)
        details_form.addRow("CRF:", self.crf_spin)
        details_form.addRow("Scale:", self.scale_edit)
        details_form.addRow("FPS:", self.fps_edit)
        right.addWidget(self.details)
        right.addStretch(1)
        body.addLayout(right, 1)
        root.addLayout(body, 1)

        # Progress + actions
        self.progress = QtWidgets.QProgressBar()
        self.progress.setValue(0)
        root.addWidget(self.progress)
        self.status = QtWidgets.QLabel("")
        root.addWidget(self.status)

        buttons = QtWidgets.QHBoxLayout()
        self.browse_ff_btn = QtWidgets.QPushButton("Browse ffmpeg…")
        self.browse_ff_btn.clicked.connect(self._browse_ffmpeg)
        buttons.addWidget(self.browse_ff_btn)
        buttons.addStretch(1)
        self.cancel_btn = QtWidgets.QPushButton("Cancel")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._cancel_job)
        buttons.addWidget(self.cancel_btn)
        self.export_btn = QtWidgets.QPushButton("Export")
        self.export_btn.setDefault(True)
        self.export_btn.clicked.connect(self._start_export)
        buttons.addWidget(self.export_btn)
        root.addLayout(buttons)

        self._fill_tree()
        self._apply_preset_to_details(self._preset)
        self._update_summary()
        self._refresh_preview()
        self._update_runtime_warning()

    def _load_session_preset(self) -> ExportPreset:
        pid = _SESSION.get("preset_id")
        for p in self._presets:
            if p.id == pid:
                return p
        return default_preset()

    def _fill_tree(self) -> None:
        self.tree.blockSignals(True)
        self.tree.clear()
        nodes: dict[tuple[str, ...], QtWidgets.QTreeWidgetItem] = {}
        enabled_n = 0
        for source in self._sources:
            parent_item = None
            parts = source.tree_parts
            for i in range(len(parts) - 1):
                key = parts[: i + 1]
                if key not in nodes:
                    item = QtWidgets.QTreeWidgetItem([parts[i]])
                    item.setFlags(item.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
                    item.setCheckState(0, QtCore.Qt.CheckState.Checked)
                    if parent_item is None:
                        self.tree.addTopLevelItem(item)
                    else:
                        parent_item.addChild(item)
                    nodes[key] = item
                parent_item = nodes[key]
            leaf = QtWidgets.QTreeWidgetItem([source.name])
            leaf.setFlags(
                leaf.flags()
                | QtCore.Qt.ItemFlag.ItemIsUserCheckable
                | QtCore.Qt.ItemFlag.ItemIsSelectable
            )
            leaf.setCheckState(
                0,
                QtCore.Qt.CheckState.Checked
                if source.enabled
                else QtCore.Qt.CheckState.Unchecked,
            )
            leaf.setData(0, QtCore.Qt.ItemDataRole.UserRole, source)
            if parent_item is None:
                self.tree.addTopLevelItem(leaf)
            else:
                parent_item.addChild(leaf)
            if source.enabled:
                enabled_n += 1
        self.tree.expandAll()
        self.tree.blockSignals(False)
        self.sources_label.setText(f"Sources ({enabled_n})")

    def _on_tree_item_changed(self, item: QtWidgets.QTreeWidgetItem, _col: int) -> None:
        source = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if isinstance(source, ExportSource):
            source.enabled = item.checkState(0) == QtCore.Qt.CheckState.Checked
        else:
            # folder: propagate to children
            state = item.checkState(0)
            for i in range(item.childCount()):
                child = item.child(i)
                child.setCheckState(0, state)
        enabled_n = sum(1 for s in self._sources if s.enabled)
        self.sources_label.setText(f"Sources ({enabled_n})")
        self._refresh_preview()

    def _on_preset_changed(self) -> None:
        pid = self.preset_combo.currentData()
        for p in all_presets():
            if p.id == pid:
                self._preset = p
                break
        self._modified = False
        self._apply_preset_to_details(self._preset)
        self._update_summary()
        self._refresh_preview()

    def _apply_preset_to_details(self, preset: ExportPreset) -> None:
        self.container_edit.blockSignals(True)
        self.vcodec_edit.blockSignals(True)
        self.acodec_edit.blockSignals(True)
        self.crf_spin.blockSignals(True)
        self.scale_edit.blockSignals(True)
        self.fps_edit.blockSignals(True)
        self.container_edit.setText(preset.container)
        self.vcodec_edit.setText(preset.video_codec)
        self.acodec_edit.setText(preset.audio_codec)
        self.crf_spin.setValue(int(preset.crf) if preset.crf is not None else 18)
        self.scale_edit.setText(preset.scale)
        self.fps_edit.setText(preset.fps)
        self.container_edit.blockSignals(False)
        self.vcodec_edit.blockSignals(False)
        self.acodec_edit.blockSignals(False)
        self.crf_spin.blockSignals(False)
        self.scale_edit.blockSignals(False)
        self.fps_edit.blockSignals(False)

    def _mark_modified(self) -> None:
        self._modified = True
        self._preset = self._preset_from_details()
        self._update_summary()
        self._refresh_preview()

    def _preset_from_details(self) -> ExportPreset:
        p = ExportPreset(
            id=self._preset.id,
            label=self._preset.label + (" *" if self._modified else ""),
            kind=self._preset.kind,
            container=self.container_edit.text().strip() or self._preset.container,
            video_codec=self.vcodec_edit.text().strip(),
            audio_codec=self.acodec_edit.text().strip(),
            audio_channels=self._preset.audio_channels,
            crf=self.crf_spin.value(),
            video_bitrate=self._preset.video_bitrate,
            audio_bitrate=self._preset.audio_bitrate,
            pix_fmt=self._preset.pix_fmt,
            scale=self.scale_edit.text().strip() or "source",
            fps=self.fps_edit.text().strip() or "source",
            builtin=False,
            extra_ffmpeg=list(self._preset.extra_ffmpeg),
        )
        return p

    def _update_summary(self) -> None:
        mark = " *" if self._modified else ""
        self.summary_label.setText(f"Summary{mark}:\n{self._preset.short_summary()}")

    def _refresh_preview(self) -> None:
        path = preview_path(
            self.dest_edit.text(),
            self._sources,
            preset=self._preset,
            filename_pattern=self.name_edit.text(),
            keep_structure=self.keep_check.isChecked(),
        )
        self.preview_label.setText(f"Preview: {path}" if path else "Preview: —")

    def _update_runtime_warning(self) -> None:
        if not self._runtime.resolve_ffmpeg():
            self.runtime_label.setStyleSheet("color: #e88;")
            self.runtime_label.setText("ffmpeg not found")
        else:
            self.runtime_label.setStyleSheet("color: #aaa;")
            self.runtime_label.setText(self._runtime.status_line())

    def _browse_dest(self) -> None:
        path = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Export destination", self.dest_edit.text() or str(Path.home())
        )
        if path:
            self.dest_edit.setText(path)

    def _browse_ffmpeg(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select ffmpeg binary", str(Path.home())
        )
        if not path:
            return
        ff = Path(path)
        probe = ff.parent / ("ffprobe.exe" if ff.suffix == ".exe" else "ffprobe")
        self._runtime.set_user_ffmpeg(ff, probe if probe.is_file() else None)
        self._update_runtime_warning()

    def _save_preset_as(self) -> None:
        name, ok = QtWidgets.QInputDialog.getText(
            self, "Save Preset As", "Preset name:", text=self._preset.label.rstrip(" *")
        )
        if not ok or not name.strip():
            return
        preset = self._preset_from_details()
        preset.id = f"user_{name.strip().lower().replace(' ', '_')}"
        preset.label = name.strip()
        preset.builtin = False
        save_user_preset(preset)
        self._presets = all_presets()
        self.preset_combo.blockSignals(True)
        self.preset_combo.clear()
        for p in self._presets:
            self.preset_combo.addItem(p.label, p.id)
        idx = self.preset_combo.findData(preset.id)
        if idx >= 0:
            self.preset_combo.setCurrentIndex(idx)
        self.preset_combo.blockSignals(False)
        self._preset = preset
        self._modified = False
        self._update_summary()

    def _persist_session(self) -> None:
        _SESSION["destination"] = self.dest_edit.text().strip()
        _SESSION["filename"] = self.name_edit.text().strip() or "<name>"
        _SESSION["preset_id"] = self.preset_combo.currentData() or self._preset.id
        _SESSION["keep_structure"] = self.keep_check.isChecked()
        _SESSION["conflict"] = self.conflict_combo.currentData() or "suffix"

    def _start_export(self) -> None:
        if self._worker and self._worker.isRunning():
            return
        dest = self.dest_edit.text().strip()
        if not dest:
            dgpy_gui.warning(self, "DG2: Export", "Set a destination folder.")
            return
        if not any(s.enabled for s in self._sources):
            dgpy_gui.warning(self, "DG2: Export", "No sources enabled.")
            return
        if not self._runtime.resolve_ffmpeg():
            dgpy_gui.warning(
                self,
                "DG2: Export",
                "ffmpeg not found.\nUse Browse ffmpeg… or install FFmpeg Runtime.",
            )
            return

        self._persist_session()
        preset = self._preset_from_details() if self._modified else self._preset
        kwargs = {
            "sources": self._sources,
            "destination": Path(dest),
            "preset": preset,
            "filename_pattern": self.name_edit.text().strip() or "<name>",
            "keep_structure": self.keep_check.isChecked(),
            "conflict": self.conflict_combo.currentData() or "suffix",
        }
        self.export_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.progress.setValue(0)
        self.status.setText("Starting…")
        self._worker = _ExportWorker(kwargs, self)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished_ok.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _cancel_job(self) -> None:
        if self._worker:
            self._worker.cancel()
            self.status.setText("Cancelling…")

    def _on_progress(self, done: int, total: int, msg: str) -> None:
        self.progress.setMaximum(max(total, 1))
        self.progress.setValue(done)
        self.status.setText(msg)

    def _on_finished(self, result) -> None:
        self.export_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.progress.setValue(self.progress.maximum())
        summary = (
            f"Done. ok={result.ok} failed={result.failed} skipped={result.skipped}"
        )
        self.status.setText(summary)
        detail = "\n".join((result.messages or [])[-12:])
        if result.failed:
            dgpy_gui.warning(self, "DG2: Export", f"{summary}\n\n{detail}")
        else:
            dgpy_gui.info(self, "DG2: Export", f"{summary}\n\n{detail}")

    def _on_failed(self, message: str) -> None:
        self.export_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.status.setText("Failed")
        dgpy_gui.error(self, "DG2: Export", message)


def open_export(selection) -> None:
    global _WINDOW
    logger = dgpy_log.setup()
    sources = resolve_export_sources(selection, logger=logger)
    if not sources:
        dgpy_gui.warning(
            None,
            "DG2: Export",
            "No Clip/Sequence found in selection.",
        )
        return
    if _WINDOW is not None:
        try:
            _WINDOW.close()
        except Exception:  # noqa: BLE001
            pass
    dlg = ExportDialog(sources)
    _WINDOW = dlg
    dlg.show()
    dlg.raise_()
    dlg.activateWindow()
