"""DGpy Preferences — paths / runtime / tools visibility (Phase A)."""

from __future__ import annotations

from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

import dgpy_config
import dgpy_ffmpeg_setup
import dgpy_gui
import dgpy_log
import dgpy_paths
import dgpy_prefs
import dgpy_tools

__version__ = "0.1.11"

_WINDOW: QtWidgets.QWidget | None = None

# Public user manual (always Public repo — not -dev).
MANUAL_INDEX_URL = (
    "https://github.com/is4mu/dg-python-scripts/blob/main/manual/README.md"
)


def open_manual() -> None:
    """Open the Public Markdown manual index in the default browser."""
    ok = QtGui.QDesktopServices.openUrl(QtCore.QUrl(MANUAL_INDEX_URL))
    if not ok:
        dgpy_gui.warning(
            None,
            "DGpy Manual",
            f"Could not open browser.\n{MANUAL_INDEX_URL}",
        )


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
            "Paths and runtime status. User prefs (token, Import/Export) "
            "are under …/flame/dgpy/prefs.json (outside python scan)."
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
        self._tools_box = self._section("Tools")
        self._log_box = self._section("Log")
        self._build_prefs_section()

        row = QtWidgets.QHBoxLayout()
        refresh = QtWidgets.QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        row.addWidget(refresh)
        manual_btn = QtWidgets.QPushButton("Open Manual…")
        manual_btn.clicked.connect(open_manual)
        row.addWidget(manual_btn)
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
                detail = hit.version_line or (
                    "not found (env / dgpy_runtimes/bin / PATH)"
                )
                form.addRow(title, _mono(f"missing — {detail}"))
        form.addRow(
            "resolve order",
            _mono(
                f"1) ${dgpy_tools.ENV_FFMPEG}/${dgpy_tools.ENV_FFPROBE}  "
                "2) dgpy_runtimes/bin  3) PATH"
            ),
        )
        form.addRow(
            "license",
            _mono(
                "FFmpeg (LGPL/GPL) via ffbinaries.com — "
                "https://ffmpeg.org/legal.html"
            ),
        )
        btn_row = QtWidgets.QHBoxLayout()
        install_btn = QtWidgets.QPushButton("Install ffmpeg…")
        install_btn.clicked.connect(self._on_install_ffmpeg)
        btn_row.addWidget(install_btn)
        remove_btn = QtWidgets.QPushButton("Remove bundled…")
        remove_btn.clicked.connect(self._on_remove_ffmpeg)
        btn_row.addWidget(remove_btn)
        btn_row.addStretch(1)
        wrap = QtWidgets.QWidget()
        wrap.setLayout(btn_row)
        form.addRow("actions", wrap)

    def _on_install_ffmpeg(self) -> None:
        force = False
        if dgpy_ffmpeg_setup.bundled_ready():
            if not dgpy_gui.confirm(
                self,
                "DGpy Preferences",
                "Bundled ffmpeg/ffprobe already exist under "
                "dgpy_runtimes/bin.\n\nRe-download and overwrite?",
            ):
                return
            force = True
        lines: list[str] = []

        def _log(msg: str) -> None:
            lines.append(msg)
            self._logger.info("%s", msg)
            QtWidgets.QApplication.processEvents()

        try:
            dest = dgpy_ffmpeg_setup.install_ffmpeg_tools(force=force, log=_log)
        except Exception as exc:  # noqa: BLE001
            dgpy_gui.error(
                self,
                "DGpy Preferences",
                "ffmpeg install failed:\n"
                + "\n".join(lines[-8:] + [str(exc)]),
            )
            return
        dgpy_gui.info(
            self,
            "DGpy Preferences",
            f"Installed under:\n{dest}\n\n" + "\n".join(lines[-6:]),
        )
        self.refresh()

    def _on_remove_ffmpeg(self) -> None:
        if not dgpy_gui.confirm(
            self,
            "DGpy Preferences",
            "Remove bundled ffmpeg/ffprobe from dgpy_runtimes/bin?\n"
            "(PATH / env tools are not touched.)",
        ):
            return
        lines: list[str] = []

        def _log(msg: str) -> None:
            lines.append(msg)
            self._logger.info("%s", msg)

        try:
            dgpy_ffmpeg_setup.remove_ffmpeg_tools(log=_log)
        except Exception as exc:  # noqa: BLE001
            dgpy_gui.error(
                self, "DGpy Preferences", f"Remove failed:\n{exc}"
            )
            return
        dgpy_gui.info(
            self,
            "DGpy Preferences",
            "\n".join(lines) or "Nothing removed.",
        )
        self.refresh()

    def _fill_log(self) -> None:
        form = self._log_box
        self._clear_form(form)
        log_path = dgpy_paths.default_log_path()
        form.addRow("dgpy.log", _row_open(log_path))

    def _fill_prefs_paths(self) -> None:
        self._prefs_path_label.setText(str(dgpy_prefs.user_prefs_path()))
        prefs = dgpy_prefs.load()
        # Env wins for HTTP; still show prefs file value in the editor.
        self._token_edit.setText(prefs.github_token)
        self._token_status.setText(dgpy_prefs.token_status_label())

    def _build_prefs_section(self) -> None:
        box = QtWidgets.QGroupBox("User prefs")
        form = QtWidgets.QFormLayout(box)

        self._prefs_path_host = QtWidgets.QWidget()
        path_row = QtWidgets.QHBoxLayout(self._prefs_path_host)
        path_row.setContentsMargins(0, 0, 0, 0)
        path_lab = _mono(str(dgpy_prefs.user_prefs_path()))
        self._prefs_path_label = path_lab
        path_row.addWidget(path_lab, 1)
        open_btn = QtWidgets.QPushButton("Open")
        open_btn.setFixedWidth(64)
        open_btn.clicked.connect(
            lambda: _open_path(dgpy_prefs.user_prefs_path())
        )
        path_row.addWidget(open_btn)
        form.addRow("prefs.json", self._prefs_path_host)

        token_wrap = QtWidgets.QWidget()
        token_col = QtWidgets.QVBoxLayout(token_wrap)
        token_col.setContentsMargins(0, 0, 0, 0)
        token_row = QtWidgets.QHBoxLayout()
        self._token_edit = QtWidgets.QLineEdit()
        self._token_edit.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        self._token_edit.setPlaceholderText(
            "GitHub PAT (Contents: Read on -dev)"
        )
        token_row.addWidget(self._token_edit, 1)
        self._token_show = QtWidgets.QCheckBox("Show")
        self._token_show.toggled.connect(self._on_token_show)
        token_row.addWidget(self._token_show)
        token_col.addLayout(token_row)
        self._token_status = _mono(dgpy_prefs.token_status_label())
        token_col.addWidget(self._token_status)
        form.addRow("GitHub token", token_wrap)

        btn_row = QtWidgets.QHBoxLayout()
        save_btn = QtWidgets.QPushButton("Save token")
        save_btn.clicked.connect(self._on_save_token)
        btn_row.addWidget(save_btn)
        export_btn = QtWidgets.QPushButton("Export…")
        export_btn.clicked.connect(self._on_export_prefs)
        btn_row.addWidget(export_btn)
        import_btn = QtWidgets.QPushButton("Import…")
        import_btn.clicked.connect(self._on_import_prefs)
        btn_row.addWidget(import_btn)
        btn_row.addStretch(1)
        btn_host = QtWidgets.QWidget()
        btn_host.setLayout(btn_row)
        form.addRow("actions", btn_host)

        form.addRow(
            "note",
            _mono(
                f"Env ${dgpy_prefs.ENV_GITHUB_TOKEN} overrides prefs for HTTP. "
                "channel=dev in Script Manager needs a token. "
                "Export includes the token — handle the file carefully."
            ),
        )
        self._body.addWidget(box)

    def _on_token_show(self, checked: bool) -> None:
        mode = (
            QtWidgets.QLineEdit.EchoMode.Normal
            if checked
            else QtWidgets.QLineEdit.EchoMode.Password
        )
        self._token_edit.setEchoMode(mode)

    def _on_save_token(self) -> None:
        prefs = dgpy_prefs.load()
        prefs.github_token = self._token_edit.text().strip()
        path = dgpy_prefs.save(prefs)
        self._token_status.setText(dgpy_prefs.token_status_label())
        self._logger.info("Saved user prefs → %s", path)
        dgpy_gui.info(
            self,
            "DGpy Preferences",
            f"Saved.\n{path}\n\nToken: {dgpy_prefs.token_status_label()}",
        )

    def _on_export_prefs(self) -> None:
        if not dgpy_gui.confirm(
            self,
            "DGpy Preferences",
            "Export copies prefs.json including the GitHub token.\n"
            "Do not put the file on a shared drive.\n\nContinue?",
        ):
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Export prefs.json",
            str(Path.home() / "dgpy-prefs.json"),
            "JSON (*.json)",
        )
        if not path:
            return
        try:
            dgpy_prefs.export_prefs(Path(path))
        except OSError as exc:
            dgpy_gui.error(self, "DGpy Preferences", f"Export failed:\n{exc}")
            return
        dgpy_gui.info(self, "DGpy Preferences", f"Exported to:\n{path}")

    def _on_import_prefs(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Import prefs.json",
            str(Path.home()),
            "JSON (*.json)",
        )
        if not path:
            return
        if not dgpy_gui.confirm(
            self,
            "DGpy Preferences",
            f"Replace current prefs.json with:\n{path}\n\nContinue?",
        ):
            return
        try:
            dgpy_prefs.import_prefs(Path(path))
        except (OSError, ValueError) as exc:
            dgpy_gui.error(self, "DGpy Preferences", f"Import failed:\n{exc}")
            return
        self._fill_prefs_paths()
        dgpy_gui.info(
            self,
            "DGpy Preferences",
            f"Imported.\n{dgpy_prefs.user_prefs_path()}\n"
            f"Token: {dgpy_prefs.token_status_label()}",
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
