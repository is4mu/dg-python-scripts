"""DGpy Preferences — paths / runtime / tools visibility (Phase A)."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

import dgpy_config
import dgpy_gui
import dgpy_log
import dgpy_paths
import dgpy_prefs
import dgpy_tools

__version__ = "0.1.1"

_WINDOW: QtWidgets.QWidget | None = None


def _open_path(path: Path) -> None:
    """Reveal path in the OS file manager (directory containing a file)."""
    path = Path(path)
    if path.is_file():
        target = path.parent
    elif path.is_dir():
        target = path
    else:
        target = path.parent if path.suffix else path
        try:
            target.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            dgpy_gui.warning(
                None, "DGpy Preferences", f"Cannot open:\n{path}\n{exc}"
            )
            return
    if not target.exists():
        dgpy_gui.warning(None, "DGpy Preferences", f"Path does not exist:\n{target}")
        return
    QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(target)))


def _mono(text: str) -> QtWidgets.QLabel:
    lab = QtWidgets.QLabel(text)
    lab.setTextInteractionFlags(
        QtCore.Qt.TextInteractionFlag.TextSelectableByMouse
    )
    lab.setWordWrap(True)
    font = lab.font()
    font.setFamily("Menlo")
    if font.family() != "Menlo":
        font.setFamily("monospace")
    lab.setFont(font)
    return lab


def _row_open(path: Path, *, label: str | None = None) -> QtWidgets.QWidget:
    w = QtWidgets.QWidget()
    row = QtWidgets.QHBoxLayout(w)
    row.setContentsMargins(0, 0, 0, 0)
    row.addWidget(_mono(label or str(path)), 1)
    btn = QtWidgets.QPushButton("Open")
    btn.setFixedWidth(64)
    btn.clicked.connect(lambda: _open_path(path))
    row.addWidget(btn)
    return w


class PreferencesDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("DGpy Preferences")
        self.setMinimumSize(720, 560)
        self.setModal(False)
        self.setWindowModality(QtCore.Qt.WindowModality.NonModal)
        # Avoid WindowType.Tool — under Flame it often paints blank / unstable.
        self.setWindowFlags(
            QtCore.Qt.WindowType.Window
            | QtCore.Qt.WindowType.WindowStaysOnTopHint
        )
        self._logger = dgpy_log.setup()
        self._build()
        self.refresh()

    def _build(self) -> None:
        root = QtWidgets.QVBoxLayout(self)

        note = QtWidgets.QLabel(
            "Read-only overview (Phase A). Heavy data stays in dgpy_runtimes "
            "(outside Flame python scan)."
        )
        note.setWordWrap(True)
        root.addWidget(note)

        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        body = QtWidgets.QWidget()
        self._body = QtWidgets.QVBoxLayout(body)
        self._body.setSpacing(12)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        self._install_box = self._section("Install")
        self._runtimes_box = self._section("Runtimes")
        self._matanyone_box = self._section("MatAnyone")
        self._tools_box = self._section("Tools")
        self._log_box = self._section("Log")
        self._prefs_box = self._section("Prefs paths (Phase B)")

        row = QtWidgets.QHBoxLayout()
        refresh = QtWidgets.QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        row.addWidget(refresh)
        row.addStretch(1)
        close = QtWidgets.QPushButton("Close")
        close.clicked.connect(self.close)
        row.addWidget(close)
        root.addLayout(row)

    def _section(self, title: str) -> QtWidgets.QFormLayout:
        box = QtWidgets.QGroupBox(title)
        form = QtWidgets.QFormLayout(box)
        form.setRowWrapPolicy(QtWidgets.QFormLayout.RowWrapPolicy.WrapLongRows)
        self._body.addWidget(box)
        return form

    def _clear_form(self, form: QtWidgets.QFormLayout) -> None:
        while form.rowCount():
            form.removeRow(0)

    def refresh(self) -> None:
        self._fill_install()
        self._fill_runtimes()
        self._fill_matanyone()
        self._fill_tools()
        self._fill_log()
        self._fill_prefs_paths()

    def _fill_install(self) -> None:
        form = self._install_box
        self._clear_form(form)
        root = dgpy_paths.dgpy_root()
        cfg = dgpy_config.load()
        form.addRow("dgpy root", _row_open(root))
        form.addRow("state", _row_open(dgpy_paths.state_dir()))
        form.addRow("channel", _mono(cfg.channel))
        form.addRow(
            "auto_update_on_start",
            _mono("true" if cfg.auto_update_on_start else "false"),
        )
        form.addRow("github_repo", _mono(cfg.github_repo))
        kind = dgpy_paths.detect_parent_kind()
        form.addRow("install kind", _mono(kind))
        writable, msg = dgpy_paths.check_writable()
        form.addRow(
            "writable",
            _mono("yes" if writable else f"no — {msg}"),
        )

    def _fill_runtimes(self) -> None:
        form = self._runtimes_box
        self._clear_form(form)
        rt = dgpy_paths.dgpy_runtimes_root()
        form.addRow("dgpy_runtimes", _row_open(rt))
        form.addRow("bin (ffmpeg…)", _row_open(dgpy_paths.runtimes_bin_dir()))
        exists = "exists" if rt.is_dir() else "not created yet"
        form.addRow("status", _mono(exists))

    def _load_matanyone_paths(self):
        apps = str(dgpy_paths.apps_dir() / "matanyone_runtime")
        if apps not in sys.path:
            sys.path.insert(0, apps)
        try:
            import matanyone_runtime_paths as rpaths

            return rpaths
        except Exception as exc:  # noqa: BLE001
            self._logger.debug("matanyone_runtime_paths unavailable: %s", exc)
            return None

    def _fill_matanyone(self) -> None:
        form = self._matanyone_box
        self._clear_form(form)
        rpaths = self._load_matanyone_paths()
        if rpaths is None:
            form.addRow(
                "package",
                _mono("matanyone_runtime not installed (Manager → Install)"),
            )
            return

        root = rpaths.runtime_root()
        form.addRow("runtime root", _row_open(root))
        ready = rpaths.is_ready()
        form.addRow("Runtime READY", _mono("yes" if ready else "no"))
        py = rpaths.resolve_python()
        form.addRow("python", _mono(py or "(missing)"))
        infer = rpaths.inference_script()
        form.addRow(
            "inference",
            _mono(str(infer) if infer else "(missing)"),
        )
        sam2 = rpaths.is_sam2_ready()
        form.addRow("SAM2 READY", _mono("yes" if sam2 else "no"))
        tiny = rpaths.sam2_checkpoint_path(size="tiny")
        form.addRow(
            "SAM2 tiny ckpt",
            _mono(
                f"{tiny} ({'ok' if tiny.is_file() else 'missing'})"
            ),
        )

        btn_row = QtWidgets.QHBoxLayout()
        for label, slot in (
            ("Runtime Setup…", self._on_runtime_setup),
            ("SAM2 Setup…", self._on_sam2_setup),
            ("Remove All…", self._on_runtime_remove),
        ):
            b = QtWidgets.QPushButton(label)
            b.clicked.connect(slot)
            btn_row.addWidget(b)
        btn_row.addStretch(1)
        wrap = QtWidgets.QWidget()
        wrap.setLayout(btn_row)
        form.addRow("actions", wrap)

    def _call_runtime_hook(self, attr: str) -> None:
        apps = str(dgpy_paths.apps_dir() / "matanyone_runtime")
        if apps not in sys.path:
            sys.path.insert(0, apps)
        try:
            import matanyone_runtime_hook as hook
        except Exception as exc:  # noqa: BLE001
            dgpy_gui.error(
                self,
                "DGpy Preferences",
                f"matanyone_runtime hook unavailable:\n{exc}",
            )
            return
        fn = getattr(hook, attr, None)
        if not callable(fn):
            dgpy_gui.error(self, "DGpy Preferences", f"Missing {attr}")
            return
        fn()

    def _on_runtime_setup(self) -> None:
        self._call_runtime_hook("open_runtime_setup")

    def _on_sam2_setup(self) -> None:
        self._call_runtime_hook("open_sam2_setup")

    def _on_runtime_remove(self) -> None:
        self._call_runtime_hook("open_runtime_remove")

    def _fill_tools(self) -> None:
        form = self._tools_box
        self._clear_form(form)
        for title, resolve in (
            ("ffmpeg", dgpy_tools.resolve_ffmpeg),
            ("ffprobe", dgpy_tools.resolve_ffprobe),
        ):
            hit = resolve()
            if hit.found:
                form.addRow(
                    title,
                    _row_open(
                        hit.path,  # type: ignore[arg-type]
                        label=f"{hit.path}  [{hit.source}]",
                    ),
                )
                form.addRow(f"{title} version", _mono(hit.version_line or "(unknown)"))
            else:
                detail = hit.version_line or "not found (env / PATH / dgpy_runtimes/bin)"
                form.addRow(title, _mono(f"missing — {detail}"))
        form.addRow(
            "resolve order",
            _mono(
                f"1) ${dgpy_tools.ENV_FFMPEG}/${dgpy_tools.ENV_FFPROBE}  "
                "2) PATH  3) dgpy_runtimes/bin"
            ),
        )

    def _fill_log(self) -> None:
        form = self._log_box
        self._clear_form(form)
        log_path = dgpy_paths.default_log_path()
        form.addRow("dgpy.log", _row_open(log_path))

    def _fill_prefs_paths(self) -> None:
        form = self._prefs_box
        self._clear_form(form)
        form.addRow("machine", _row_open(dgpy_prefs.machine_prefs_path()))
        form.addRow("user", _row_open(dgpy_prefs.user_prefs_path()))
        form.addRow(
            "note",
            _mono("Paths only for now — editing lands in Phase B."),
        )


def open_preferences() -> None:
    global _WINDOW
    if _WINDOW is not None:
        try:
            if _WINDOW.isVisible():
                _WINDOW.raise_()
                _WINDOW.activateWindow()
                if hasattr(_WINDOW, "refresh"):
                    _WINDOW.refresh()
                return
        except RuntimeError:
            _WINDOW = None
    dlg = PreferencesDialog()
    _WINDOW = dlg
    dlg.show()
    dlg.raise_()
    dlg.activateWindow()
