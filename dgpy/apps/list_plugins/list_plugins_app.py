"""Collect OpenFX / Sparks used on the current Desktop; show a list dialog."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from PySide6 import QtCore, QtWidgets

import dgpy_gui
import dgpy_log

__version__ = "1.1.2"

_WINDOW: QtWidgets.QWidget | None = None
_NONE = "(none)"
_SPARK_TL_FALLBACK = "Spark (TL FX)"


def _attr_str(value) -> str:
    """Normalize Flame PyString / str-like attribute to a plain string."""
    if value is None:
        return ""
    if hasattr(value, "get_value"):
        try:
            value = value.get_value()
        except Exception:  # noqa: BLE001
            pass
    text = str(value).strip()
    # Legacy Flame repr sometimes looked like "('Name',)" / "('Name')"
    if len(text) >= 2 and text[0] == "(" and text[-1] == ")":
        inner = text[1:-1].strip()
        if len(inner) >= 2 and inner[0] in "'\"" and inner[-1] == inner[0]:
            return inner[1:-1]
        if inner.endswith(","):
            inner = inner[:-1].strip()
            if len(inner) >= 2 and inner[0] in "'\"" and inner[-1] == inner[0]:
                return inner[1:-1]
        return inner
    if len(text) >= 2 and text[0] in "'\"" and text[-1] == text[0]:
        return text[1:-1]
    return text


def _sparks_display_name(sparks_path) -> str:
    """Old heuristic: last two path parts, drop extension."""
    raw = _attr_str(sparks_path)
    if not raw:
        return ""
    parts = raw.replace("\\", "/").split("/")
    tail = "/".join(parts[-2:]) if len(parts) >= 2 else parts[-1]
    return tail.split(".")[0] if tail else raw


def collect_plugins(desktop) -> tuple[list[str], list[str]]:
    """Scan Desktop timeline FX + batch nodes. Returns sorted unique names."""
    openfx: set[str] = set()
    sparks: set[str] = set()

    for reel_group in getattr(desktop, "reel_groups", None) or []:
        for reel in getattr(reel_group, "reels", None) or []:
            for sequence in getattr(reel, "sequences", None) or []:
                for version in getattr(sequence, "versions", None) or []:
                    for track in getattr(version, "tracks", None) or []:
                        for segment in getattr(track, "segments", None) or []:
                            for effect in getattr(segment, "effects", None) or []:
                                etype = _attr_str(getattr(effect, "type", None))
                                if etype == "OpenFX":
                                    name = _attr_str(
                                        getattr(effect, "plugin_name", None)
                                    )
                                    if name:
                                        openfx.add(name)
                                elif etype == "Spark":
                                    name = _attr_str(
                                        getattr(effect, "plugin_name", None)
                                    ) or _attr_str(
                                        getattr(effect, "name", None)
                                    )
                                    sparks.add(name or _SPARK_TL_FALLBACK)

    for batch_group in getattr(desktop, "batch_groups", None) or []:
        for node in getattr(batch_group, "nodes", None) or []:
            ntype = _attr_str(getattr(node, "type", None)).lower()
            if ntype == "openfx":
                name = _attr_str(getattr(node, "plugin_name", None))
                if name:
                    openfx.add(name)
            elif ntype == "sparks":
                name = _sparks_display_name(getattr(node, "sparks_name", None))
                if name:
                    sparks.add(name)

    return sorted(openfx), sorted(sparks)


def format_report(openfx: list[str], sparks: list[str]) -> str:
    openfx_text = "\n".join(openfx) if openfx else _NONE
    sparks_text = "\n".join(sparks) if sparks else _NONE
    return f"< OpenFX >\n{openfx_text}\n\n< Sparks >\n{sparks_text}"


def _safe_filename_part(text: str) -> str:
    cleaned = re.sub(r"[^\w.\-]+", "_", text.strip(), flags=re.UNICODE)
    cleaned = cleaned.strip("._") or "project"
    return cleaned[:80]


def current_project_name() -> str:
    try:
        import flame

        name = getattr(flame.project.current_project, "name", None)
        text = _attr_str(name)
        if text:
            return text
    except Exception:  # noqa: BLE001
        pass
    return "project"


def default_export_path() -> Path:
    """~/Desktop if present, else home. Filename: {project}_{YYMMDD}_list_plugins.txt"""
    desktop = Path.home() / "Desktop"
    folder = desktop if desktop.is_dir() else Path.home()
    stamp = datetime.now().strftime("%y%m%d")
    name = f"{_safe_filename_part(current_project_name())}_{stamp}_list_plugins.txt"
    return folder / name


class ListPluginsDialog(QtWidgets.QDialog):
    def __init__(self, report: str, parent=None):
        super().__init__(parent)
        self._report = report
        self.setWindowTitle("List Plugins")
        self.setMinimumSize(420, 360)
        self.setWindowFlags(
            self.windowFlags() | QtCore.Qt.WindowType.WindowStaysOnTopHint
        )

        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(8)

        self._view = QtWidgets.QPlainTextEdit()
        self._view.setReadOnly(True)
        self._view.setPlainText(report)
        layout.addWidget(self._view, 1)

        btn_row = QtWidgets.QHBoxLayout()
        export_btn = QtWidgets.QPushButton("Export .txt")
        export_btn.setAutoDefault(False)
        export_btn.setDefault(False)
        export_btn.clicked.connect(self._export_txt)
        btn_row.addWidget(export_btn)
        btn_row.addStretch(1)
        close_btn = QtWidgets.QPushButton("Close")
        close_btn.setDefault(True)
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def _export_txt(self) -> None:
        suggested = str(default_export_path())
        path, _filter = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Export List Plugins",
            suggested,
            "Text (*.txt);;All Files (*)",
        )
        if not path:
            return
        if not path.lower().endswith(".txt"):
            path = path + ".txt"
        try:
            with open(path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(self._report)
                if not self._report.endswith("\n"):
                    fh.write("\n")
        except OSError as exc:
            dgpy_log.setup().exception("List Plugins: export failed: %s", exc)
            dgpy_gui.error(self, "List Plugins", f"Export failed:\n{exc}")
            return
        dgpy_log.setup().info("List Plugins: exported %s", path)
        dgpy_gui.info(self, "List Plugins", f"Exported:\n{path}")


def open_list_plugins() -> None:
    global _WINDOW
    logger = dgpy_log.setup()

    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])

    try:
        import flame

        desktop = flame.batch.parent
    except Exception as exc:  # noqa: BLE001
        logger.exception("List Plugins: cannot resolve Desktop: %s", exc)
        dgpy_gui.error(
            None, "List Plugins", f"Cannot access current Desktop:\n{exc}"
        )
        return

    try:
        openfx, sparks = collect_plugins(desktop)
    except Exception as exc:  # noqa: BLE001
        logger.exception("List Plugins: scan failed: %s", exc)
        dgpy_gui.error(None, "List Plugins", f"Scan failed:\n{exc}")
        return

    report = format_report(openfx, sparks)
    logger.info(
        "List Plugins: OpenFX=%s Sparks=%s", len(openfx), len(sparks)
    )

    if _WINDOW is not None:
        try:
            _WINDOW.close()
        except Exception:  # noqa: BLE001
            pass
        _WINDOW = None

    dialog = ListPluginsDialog(report)
    _WINDOW = dialog
    dialog.show()
