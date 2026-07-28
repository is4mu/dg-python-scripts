"""DG Export job: Flame PyExporter → destination (folder tree preserved)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import dgpy_paths
from dg_export_presets import ExportPresetDef, resolve_preset_xml
from dg_export_selection import ExportSource

__version__ = "0.1.7"

ProgressCb = Callable[[int, int, str], None]

_MEDIA_EXT = {".mov", ".mxf", ".mp4", ".m4v", ".avi", ".mkv", ".mpg", ".mpeg", ".als"}

_WARN_FLAGS = (
    "warn_on_mixed_colour_space",
    "warn_on_link_unsupported",
    "warn_on_no_media",
    "warn_on_pending_render",
    "warn_on_reimport_unsupported",
    "warn_on_unlinked",
    "warn_on_unrendered",
)


@dataclass
class JobResult:
    ok: int = 0
    failed: int = 0
    skipped: int = 0
    messages: list[str] | None = None

    def __post_init__(self) -> None:
        if self.messages is None:
            self.messages = []


def _config_path() -> Path:
    return dgpy_paths.state_dir() / "dg_export.json"


def load_config() -> dict:
    path = _config_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_config(data: dict) -> None:
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = load_config()
    existing.update(data)
    path.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")


def last_destination() -> Path | None:
    raw = str(load_config().get("last_destination") or "").strip()
    if not raw:
        return None
    path = Path(raw).expanduser()
    return path if path.is_dir() else path.parent if path.parent.is_dir() else None


def _apply_exporter_quiet_flags(exporter) -> None:
    for name in _WARN_FLAGS:
        if hasattr(exporter, name):
            try:
                setattr(exporter, name, False)
            except Exception:  # noqa: BLE001
                pass


class _AutoContinueFlameDialogs:
    """Click Continue on Flame modals that lack a Python suppress flag."""

    _TITLE_HINTS = ("old version", "confirm operation", "export preset")
    _BUTTON_HINTS = ("continue", "continue export", "ok", "yes")

    def __init__(self) -> None:
        self._timer = None

    def start(self) -> None:
        from PySide6 import QtCore, QtWidgets

        app = QtWidgets.QApplication.instance()
        if app is None:
            return

        def tick() -> None:
            for widget in app.topLevelWidgets():
                if not widget.isVisible():
                    continue
                title = (widget.windowTitle() or "").lower()
                if any(h in title for h in self._TITLE_HINTS) or self._looks_like_export_warning(
                    widget
                ):
                    self._click_continue(widget)

        self._timer = QtCore.QTimer()
        self._timer.setInterval(200)
        self._timer.timeout.connect(tick)
        self._timer.start()

    def stop(self) -> None:
        if self._timer is not None:
            self._timer.stop()
            self._timer = None

    @staticmethod
    def _looks_like_export_warning(widget) -> bool:
        from PySide6 import QtWidgets

        texts = [(label.text() or "").lower() for label in widget.findChildren(QtWidgets.QLabel)]
        blob = " ".join(texts)
        return (
            "older version" in blob
            or "colour space" in blob
            or "color space" in blob
            or "export preset" in blob
        )

    @classmethod
    def _click_continue(cls, widget) -> None:
        from PySide6 import QtWidgets

        for btn in widget.findChildren(QtWidgets.QPushButton):
            text = (btn.text() or "").strip().lower().replace("&", "")
            if text in cls._BUTTON_HINTS or text.startswith("continue"):
                if btn.isEnabled() and btn.isVisible():
                    btn.click()
                    return


def _out_dir_for(destination: Path, source: ExportSource) -> Path:
    if source.relative_dir:
        return destination / Path(source.relative_dir)
    return destination


def _dir_has_media(path: Path) -> bool:
    if not path.is_dir():
        return False
    for child in path.iterdir():
        if not child.is_file() or child.name.startswith("."):
            continue
        if child.suffix.lower() in _MEDIA_EXT:
            return True
    return False


def _confirm_overwrite(path: Path, *, label: str) -> str:
    """Return 'overwrite' | 'skip' | 'abort'."""
    from PySide6 import QtWidgets

    box = QtWidgets.QMessageBox()
    box.setIcon(QtWidgets.QMessageBox.Warning)
    box.setWindowTitle("DG Export")
    box.setText(f"Destination already has files:\n{path}\n\nItem: {label}")
    box.setInformativeText("Overwrite / continue export into this folder?")
    overwrite = box.addButton("Overwrite", QtWidgets.QMessageBox.AcceptRole)
    skip = box.addButton("Skip", QtWidgets.QMessageBox.DestructiveRole)
    abort = box.addButton("Cancel", QtWidgets.QMessageBox.RejectRole)
    box.setDefaultButton(skip)
    box.exec()
    clicked = box.clickedButton()
    if clicked is overwrite:
        return "overwrite"
    if clicked is skip:
        return "skip"
    return "abort"


def export_one(
    clip,
    *,
    preset_xml: Path,
    out_dir: Path,
    logger,
) -> None:
    import flame

    out_dir.mkdir(parents=True, exist_ok=True)
    exporter = flame.PyExporter()
    if hasattr(exporter, "foreground"):
        exporter.foreground = True
    if hasattr(exporter, "export_between_marks"):
        exporter.export_between_marks = False
    if hasattr(exporter, "use_top_video_track"):
        exporter.use_top_video_track = True
    _apply_exporter_quiet_flags(exporter)

    logger.info(
        "PyExporter.export sources=%s preset=%s out=%s",
        type(clip).__name__,
        preset_xml,
        out_dir,
    )

    auto = _AutoContinueFlameDialogs()
    auto.start()
    try:
        errors: list[str] = []
        for sources in ([clip], clip):
            try:
                exporter.export(sources, str(preset_xml), str(out_dir))
                return
            except TypeError as exc:
                errors.append(str(exc))
            except Exception as exc:  # noqa: BLE001
                errors.append(str(exc))
                logger.warning("PyExporter.export failed: %s", exc)
        raise RuntimeError(
            "Flame export failed.\n"
            f"Preset: {preset_xml}\n"
            + ("; ".join(errors[:2]) if errors else "Unknown error")
        )
    finally:
        auto.stop()


def run_export(
    sources: list[ExportSource],
    *,
    destination: Path,
    preset: ExportPresetDef,
    progress: ProgressCb | None = None,
) -> JobResult:
    import dgpy_log

    logger = dgpy_log.setup()
    result = JobResult()
    preset_xml = resolve_preset_xml(preset)
    logger.info("DG Export preset=%s xml=%s dest=%s", preset.id, preset_xml, destination)

    enabled = [s for s in sources if s.enabled]
    total = len(enabled)
    if total == 0:
        return result

    destination.mkdir(parents=True, exist_ok=True)
    save_config({"last_destination": str(destination)})

    for index, source in enumerate(enabled, start=1):
        name = source.name
        if progress:
            progress(index - 1, total, f"Exporting {name}…")

        out_dir = _out_dir_for(destination, source)
        if _dir_has_media(out_dir):
            choice = _confirm_overwrite(out_dir, label=source.relative_path_key)
            if choice == "abort":
                result.messages.append("Cancelled")
                break
            if choice == "skip":
                result.skipped += 1
                result.messages.append(f"Skip existing: {out_dir}")
                if progress:
                    progress(index, total, f"Skipped {name}")
                continue

        try:
            export_one(source.item, preset_xml=preset_xml, out_dir=out_dir, logger=logger)
            result.ok += 1
            result.messages.append(f"OK: {out_dir} ({name})")
        except Exception as exc:  # noqa: BLE001
            result.failed += 1
            result.messages.append(f"FAIL {name}: {exc}")
            logger.exception("DG Export failed for %s", name)

        if progress:
            progress(index, total, f"Done {name}")

    return result
