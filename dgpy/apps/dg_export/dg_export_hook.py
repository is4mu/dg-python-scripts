"""
Flame: DG2: Export (PyExporter).

Media Panel: DG2: Export → <stem of each presets/*.xml>
"""

from __future__ import annotations

import os
import sys

_APP_DIR = os.path.dirname(os.path.abspath(__file__))
_DGPY_ROOT = os.path.dirname(os.path.dirname(_APP_DIR))
for _p in (_DGPY_ROOT, _APP_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

_pending_selection: list | None = None


def _as_list(selection) -> list:
    if not selection:
        return []
    if isinstance(selection, (list, tuple)):
        return list(selection)
    return [selection]


def _scope_visible(selection) -> bool:
    global _pending_selection
    import dgpy_flame_types
    import dgpy_log
    import dg_export_selection

    logger = dgpy_log.setup()
    try:
        items = _as_list(selection)
        _pending_selection = items
        visible = dg_export_selection.has_exportable(items)
    except Exception as exc:  # noqa: BLE001
        logger.warning("DG2: Export isVisible error: %s", exc)
        return False
    logger.debug(
        "DG2: Export isVisible pending=%s visible=%s",
        dgpy_flame_types.summarize(items),
        visible,
    )
    return visible


def _resolve_execute_selection(selection) -> list:
    global _pending_selection
    import dgpy_flame_types
    import dgpy_log

    logger = dgpy_log.setup()
    execute_items = _as_list(selection)
    pending = _pending_selection
    _pending_selection = None
    if pending:
        if execute_items and dgpy_flame_types.summarize(pending) != dgpy_flame_types.summarize(
            execute_items
        ):
            logger.debug(
                "DG2: Export using isVisible context %s (execute had %s)",
                dgpy_flame_types.summarize(pending),
                dgpy_flame_types.summarize(execute_items),
            )
        return pending
    return execute_items


def _pick_destination():
    from pathlib import Path

    from PySide6 import QtWidgets

    import dg_export_job

    start = dg_export_job.last_destination() or Path.home()
    path = QtWidgets.QFileDialog.getExistingDirectory(
        None,
        "DG Export — Destination",
        str(start),
    )
    if not path:
        return None
    return Path(path)


def _run_preset(preset_id: str, selection=None) -> None:
    import dgpy_gui
    import dgpy_log
    import dg_export_job
    import dg_export_presets
    import dg_export_selection

    logger = dgpy_log.setup()
    preset = dg_export_presets.find_preset(preset_id)
    if preset is None:
        dgpy_gui.warning(
            None,
            "DG Export",
            f"Preset not found: {preset_id}\n\n"
            f"Add XML under:\n{dg_export_presets.package_presets_dir()}",
        )
        return

    items = _resolve_execute_selection(selection)
    sources = dg_export_selection.resolve_export_sources(items, logger=logger)
    if not sources:
        dgpy_gui.warning(None, "DG Export", "No Clip / Sequence found in selection.")
        return

    try:
        dg_export_presets.resolve_preset_xml(preset)
    except RuntimeError as exc:
        dgpy_gui.warning(None, "DG Export", str(exc))
        return

    destination = _pick_destination()
    if destination is None:
        return

    try:
        result = dg_export_job.run_export(
            sources,
            destination=destination,
            preset=preset,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("DG Export failed: %s", exc)
        dgpy_gui.warning(None, "DG Export", f"Export failed:\n{exc}")
        return

    summary = (
        f"{preset.label}\n"
        f"OK: {result.ok}  Failed: {result.failed}  Skipped: {result.skipped}\n"
        f"Destination: {destination}"
    )
    if result.failed:
        detail = "\n".join(result.messages[-8:])
        dgpy_gui.warning(None, "DG Export", f"{summary}\n\n{detail}")
    else:
        from PySide6 import QtWidgets

        QtWidgets.QMessageBox.information(None, "DG Export", summary)


def _make_execute(preset_id: str):
    def _execute(selection=None):
        try:
            _run_preset(preset_id, selection)
        except Exception as exc:  # noqa: BLE001
            import dgpy_gui
            import dgpy_log

            dgpy_log.setup().exception("DG Export menu failed: %s", exc)
            dgpy_gui.warning(None, "DG Export", f"Failed:\n{exc}")

    return _execute


def get_media_panel_custom_ui_actions():
    import dgpy_menu_layout
    import dg_export_presets

    presets = dg_export_presets.list_presets()
    if not presets:
        return []

    meta = dgpy_menu_layout.MEDIA_PANEL_GROUPS["export"]
    actions = []
    for index, preset in enumerate(presets):
        actions.append(
            {
                "name": preset.label,
                "order": index,
                "isVisible": _scope_visible,
                "execute": _make_execute(preset.id),
                "minimumVersion": "2025",
            }
        )
    group = {
        "hierarchy": list(meta.get("hierarchy") or []),
        "order": int(meta.get("order", 55)),
        "actions": actions,
    }
    if meta.get("separator"):
        group["separator"] = meta["separator"]
    return [group]
