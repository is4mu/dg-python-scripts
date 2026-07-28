"""Save Batch setups to a user-chosen folder (default: <project>/batch/flame)."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from PySide6 import QtWidgets

import dgpy_gui
import dgpy_log
import dgpy_project

__version__ = "1.1.4"


def _batch_name(batch) -> str:
    name = getattr(batch, "name", None)
    if name is not None and hasattr(name, "get_value"):
        try:
            return str(name.get_value())
        except Exception:  # noqa: BLE001
            pass
    if name is not None:
        return str(name)
    return "batch"


def _safe_folder_part(text: str) -> str:
    cleaned = re.sub(r"[^\w.\-]+", "_", text.strip(), flags=re.UNICODE)
    return cleaned.strip("._") or "Desktop"


def save_batch_setups(batches: list) -> None:
    logger = dgpy_log.setup()

    if not batches:
        dgpy_gui.warning(None, "Save Batch Setup", "No batch groups selected.")
        return

    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])

    start = dgpy_project.default_batch_flame_dir()
    if start is None:
        dgpy_gui.error(
            None,
            "Save Batch Setup",
            "Could not resolve the Flame project directory.\n"
            "Tried PyExporter presets path and /opt/Autodesk/project/<name>.",
        )
        return

    chosen = QtWidgets.QFileDialog.getExistingDirectory(
        None,
        "Save Batch Setup — choose parent folder",
        str(start),
    )
    if not chosen:
        logger.info("Save Batch Setup: cancelled")
        return

    parent = Path(chosen)
    desk = _safe_folder_part(dgpy_project.current_desktop_name())
    stamp = datetime.now().strftime("%H%M")
    out_dir = parent / f"{desk}_{stamp}"
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        dgpy_gui.error(
            None,
            "Save Batch Setup",
            f"Cannot create folder:\n{out_dir}\n{exc}",
        )
        return

    logger.info("Save Batch Setup: writing under %s", out_dir)

    ok = 0
    failed = 0
    for batch in batches:
        name = _batch_name(batch)
        dest = out_dir / name
        try:
            batch.save_setup(str(dest))
            ok += 1
            logger.info("Save Batch Setup: saved %s → %s", name, dest)
        except Exception as exc:  # noqa: BLE001
            failed += 1
            logger.warning(
                "Save Batch Setup: failed for %s: %s", name, exc
            )

    logger.info(
        "Save Batch Setup: ok=%s failed=%s dir=%s", ok, failed, out_dir
    )
    if failed and not ok:
        dgpy_gui.error(
            None,
            "Save Batch Setup",
            f"Failed to save all setups ({failed}).\n{out_dir}",
        )
    elif failed:
        dgpy_gui.warning(
            None,
            "Save Batch Setup",
            f"Saved {ok}, failed {failed}.\n{out_dir}",
        )
    else:
        dgpy_gui.info(
            None,
            "Save Batch Setup",
            f"Saved {ok} setup(s) to:\n{out_dir}",
        )
