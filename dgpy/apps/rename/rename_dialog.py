"""DG: Rename dialog — pattern / tokens / replace. PySide6 only."""

from __future__ import annotations

import re
from datetime import datetime

from PySide6 import QtCore, QtWidgets

import dgpy_gui
import dgpy_log

__version__ = "1.2.7"

TOKEN_LIST = ("<name>", "<date>", "<index>")
_DEFAULT_PATTERN = "<name>"
_STATUS_INVALID_REGEX = "Invalid regex — using literal replace"

_WINDOW: QtWidgets.QWidget | None = None

# Process-lifetime only (cleared on Flame restart / Rescan module reload).
_SESSION: dict = {
    "pattern": _DEFAULT_PATTERN,
    "replaces": [("", "")],
}


def _persist_session(pattern: str, replaces: list[tuple[str, str]]) -> None:
    pairs = list(replaces) if replaces else [("", "")]
    _SESSION["pattern"] = pattern if pattern else _DEFAULT_PATTERN
    _SESSION["replaces"] = [(str(a), str(b)) for a, b in pairs]


def _reset_session() -> None:
    _persist_session(_DEFAULT_PATTERN, [("", "")])


def _item_name(item) -> str:
    name = getattr(item, "name", None)
    if name is None:
        return ""
    if hasattr(name, "get_value"):
        try:
            return str(name.get_value())
        except Exception:  # noqa: BLE001
            return str(name)
    return str(name)


def _set_item_name(item, new_name: str) -> None:
    name = getattr(item, "name", None)
    if hasattr(name, "set_value"):
        name.set_value(new_name)
    else:
        item.name = new_name


def _format_date(date_obj: datetime, fmt: str) -> str:
    fmt_map = (
        ("YYYY", "%Y"),
        ("YY", "%y"),
        ("MM", "%m"),
        ("DD", "%d"),
        ("M", "%m"),
        ("D", "%d"),
    )
    python_format = fmt
    for key, value in fmt_map:
        python_format = python_format.replace(key, value)
    try:
        result = date_obj.strftime(python_format)
        if "%-" in python_format:
            result = result.lstrip("0")
        return result
    except Exception:  # noqa: BLE001
        return date_obj.strftime("%Y%m%d")


def _resolve_index_tokens(text: str, index: int) -> str:
    index_pattern = re.compile(r"<index(#+)?(@(\d+)([+-]\d+)?)?>")

    def replace_index(match: re.Match[str]) -> str:
        padding = match.group(1)
        start = int(match.group(3)) if match.group(3) else 1
        increment = int(match.group(4)) if match.group(4) else 1
        value = start + (index - 1) * increment
        return str(value).zfill(len(padding)) if padding else str(value)

    return index_pattern.sub(replace_index, text)


def resolve_tokens(text: str, item, index: int) -> str:
    result = text.replace("<name>", _item_name(item))
    today = datetime.now()
    date_pattern = re.compile(r"<date(@([^>]+))?>")
    while True:
        match = date_pattern.search(result)
        if not match:
            break
        date_format = match.group(2) if match.group(2) else "YYMMDD"
        formatted = _format_date(today, date_format)
        result = result[: match.start()] + formatted + result[match.end() :]
    return _resolve_index_tokens(result, index)


def apply_replaces(
    text: str,
    replace_rows: list[tuple[str, str]],
    item,
    index: int,
) -> tuple[str, bool]:
    """Apply replace rows. Returns (result, used_literal_fallback)."""
    result = text
    used_literal = False
    for from_text, to_raw in replace_rows:
        if not from_text:
            continue
        to_text = resolve_tokens(to_raw, item, index)
        try:
            result = re.sub(from_text, to_text, result)
        except re.error:
            used_literal = True
            result = result.replace(from_text, to_text)
    return result, used_literal


def resolve_pattern(
    item,
    pattern: str,
    replace_rows: list[tuple[str, str]],
    index: int = 1,
) -> tuple[str, bool]:
    result = resolve_tokens(pattern, item, index)
    return apply_replaces(result, replace_rows, item, index)


class RenameDialog(QtWidgets.QDialog):
    def __init__(self, selection: list, parent=None):
        super().__init__(parent)
        self._selection = list(selection)
        self._replace_rows: list[dict] = []
        self._token_target: QtWidgets.QLineEdit | None = None

        self.setWindowTitle("DG: Rename")
        self.setMinimumWidth(480)
        self.setWindowFlags(
            self.windowFlags() | QtCore.Qt.WindowType.WindowStaysOnTopHint
        )

        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(8)

        layout.addWidget(QtWidgets.QLabel("Filename"))
        self._preview = QtWidgets.QLineEdit()
        self._preview.setReadOnly(True)
        layout.addWidget(self._preview)

        layout.addWidget(QtWidgets.QLabel("Pattern"))
        pattern_row = QtWidgets.QHBoxLayout()
        self._pattern = QtWidgets.QLineEdit(_DEFAULT_PATTERN)
        self._pattern.installEventFilter(self)
        pattern_row.addWidget(self._pattern, 1)
        self._token_combo = QtWidgets.QComboBox()
        self._token_combo.addItem("Add Token…")
        for token in TOKEN_LIST:
            self._token_combo.addItem(token)
        self._token_combo.setMinimumWidth(120)
        self._token_combo.currentIndexChanged.connect(self._insert_token)
        pattern_row.addWidget(self._token_combo)
        layout.addLayout(pattern_row)

        replace_header = QtWidgets.QHBoxLayout()
        replace_header.addWidget(QtWidgets.QLabel("Replace"))
        add_btn = QtWidgets.QPushButton("+")
        add_btn.setFixedWidth(28)
        add_btn.setAutoDefault(False)
        add_btn.setDefault(False)
        add_btn.clicked.connect(lambda: self._add_replace_row())
        replace_header.addWidget(add_btn)
        replace_header.addStretch(1)
        layout.addLayout(replace_header)

        self._replace_host = QtWidgets.QWidget()
        self._replace_container = QtWidgets.QVBoxLayout(self._replace_host)
        self._replace_container.setContentsMargins(0, 0, 0, 0)
        self._replace_container.setSpacing(6)
        layout.addWidget(self._replace_host)

        self._status = QtWidgets.QLabel("")
        self._status.setStyleSheet("color: #C09000;")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)

        apply_row = QtWidgets.QHBoxLayout()
        reset_btn = QtWidgets.QPushButton("Reset")
        reset_btn.setAutoDefault(False)
        reset_btn.setDefault(False)
        reset_btn.clicked.connect(self._reset_defaults)
        apply_row.addWidget(reset_btn)
        apply_row.addStretch(1)
        apply_btn = QtWidgets.QPushButton("Apply")
        apply_btn.setDefault(True)
        apply_btn.setAutoDefault(True)
        apply_btn.clicked.connect(self._apply)
        apply_row.addWidget(apply_btn)
        layout.addLayout(apply_row)
        self._apply_btn = apply_btn

        self._token_target = self._pattern
        self._pattern.textChanged.connect(self._update_preview)

        saved_pattern = _SESSION.get("pattern") or _DEFAULT_PATTERN
        self._pattern.setText(saved_pattern)
        saved_replaces = _SESSION.get("replaces") or [("", "")]
        for from_text, to_text in saved_replaces:
            self._add_replace_row(from_text, to_text)
        self._update_preview()
        self._fit_height()

    def closeEvent(self, event):  # noqa: N802
        self._save_to_session()
        super().closeEvent(event)

    def _save_to_session(self) -> None:
        _persist_session(self._pattern.text(), self._replace_pairs())

    def eventFilter(self, obj, event):  # noqa: N802
        if (
            event.type() == QtCore.QEvent.Type.FocusIn
            and isinstance(obj, QtWidgets.QLineEdit)
            and obj is not self._preview
        ):
            self._token_target = obj
        return super().eventFilter(obj, event)

    def _replace_pairs(self) -> list[tuple[str, str]]:
        return [(r["from"].text(), r["to"].text()) for r in self._replace_rows]

    def _update_preview(self, *_args) -> None:
        if not self._selection:
            self._preview.setText("")
            self._status.setText("")
            return
        pattern = self._pattern.text()
        text, used_literal = resolve_pattern(
            self._selection[0], pattern, self._replace_pairs(), index=1
        )
        self._preview.setText(text)
        self._status.setText(_STATUS_INVALID_REGEX if used_literal else "")

    def _insert_token(self, index: int) -> None:
        if index <= 0 or self._token_target is None:
            return
        token = self._token_combo.currentText()
        cursor = self._token_target.cursorPosition()
        text = self._token_target.text()
        self._token_target.setText(text[:cursor] + token + text[cursor:])
        self._token_target.setCursorPosition(cursor + len(token))
        self._token_target.setFocus()
        self._token_combo.setCurrentIndex(0)

    def _add_replace_row(self, from_text: str = "", to_text: str = "") -> None:
        row_widget = QtWidgets.QWidget()
        row_layout = QtWidgets.QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        replace_from = QtWidgets.QLineEdit(from_text)
        replace_to = QtWidgets.QLineEdit(to_text)
        replace_to.installEventFilter(self)
        remove_btn = QtWidgets.QPushButton("-")
        remove_btn.setFixedWidth(28)
        remove_btn.setAutoDefault(False)
        remove_btn.setDefault(False)
        row_layout.addWidget(replace_from, 1)
        row_layout.addWidget(QtWidgets.QLabel("->"))
        row_layout.addWidget(replace_to, 1)
        row_layout.addWidget(remove_btn)

        row_data = {
            "from": replace_from,
            "to": replace_to,
            "widget": row_widget,
            "remove": remove_btn,
        }
        self._replace_rows.append(row_data)
        self._replace_container.addWidget(row_widget)

        replace_from.textChanged.connect(self._update_preview)
        replace_to.textChanged.connect(self._update_preview)
        remove_btn.clicked.connect(lambda: self._remove_replace_row(row_data))
        self._update_remove_buttons()
        self._update_preview()
        self._fit_height()

    def _remove_replace_row(self, row_data: dict) -> None:
        if row_data not in self._replace_rows or len(self._replace_rows) <= 1:
            return
        self._replace_rows.remove(row_data)
        row_widget = row_data["widget"]
        self._replace_container.removeWidget(row_widget)
        row_widget.deleteLater()
        self._update_remove_buttons()
        self._update_preview()
        self._fit_height()

    def _clear_replace_rows(self) -> None:
        for row in list(self._replace_rows):
            self._replace_container.removeWidget(row["widget"])
            row["widget"].deleteLater()
        self._replace_rows.clear()

    def _reset_defaults(self) -> None:
        """Pattern / Replace / session → initial values."""
        self._pattern.setText(_DEFAULT_PATTERN)
        self._token_target = self._pattern
        self._token_combo.setCurrentIndex(0)
        self._clear_replace_rows()
        self._add_replace_row()
        _reset_session()
        self._update_preview()
        self._fit_height()

    def _update_remove_buttons(self) -> None:
        enable = len(self._replace_rows) > 1
        for row in self._replace_rows:
            row["remove"].setEnabled(enable)

    def _fit_height(self) -> None:
        """Grow/shrink window height to match replace rows; keep width."""
        QtWidgets.QApplication.processEvents(
            QtCore.QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents
        )
        self.layout().activate()
        hint = self.sizeHint()
        width = max(self.width(), self.minimumWidth(), hint.width())
        self.resize(width, hint.height())

    def _apply(self) -> None:
        pattern = self._pattern.text()
        if not pattern:
            return
        self._save_to_session()
        logger = dgpy_log.get_logger()
        ok = 0
        failed = 0
        pairs = self._replace_pairs()
        for i, item in enumerate(self._selection, start=1):
            new_name, _ = resolve_pattern(item, pattern, pairs, index=i)
            try:
                _set_item_name(item, new_name)
                ok += 1
            except Exception as exc:  # noqa: BLE001
                failed += 1
                logger.warning("Rename failed for item %s: %s", i, exc)
        logger.info("Rename: applied to %s item(s) (failed %s)", ok, failed)
        self.accept()


def open_rename(selection=None) -> None:
    global _WINDOW
    logger = dgpy_log.setup()
    items = []
    if selection:
        items = list(selection) if isinstance(selection, (list, tuple)) else [selection]
    if not items:
        dgpy_gui.info(None, "DG: Rename", "Nothing selected.")
        return

    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])

    if _WINDOW is not None:
        try:
            _WINDOW.close()
        except Exception:  # noqa: BLE001
            pass
        _WINDOW = None

    dialog = RenameDialog(items)
    _WINDOW = dialog
    dialog.show()
    names = ", ".join(_item_name(i) for i in items[:5])
    if len(items) > 5:
        names += ", …"
    logger.info(
        "DG: Rename opened (%s item(s)): %s",
        len(items),
        names,
    )
