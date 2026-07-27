"""
Flame: DG2: Export (ffmpeg write).

Media Panel only (v1). Menu: context root → DG2: Export (hierarchy []).
"""

from __future__ import annotations

import os
import sys

_APP_DIR = os.path.dirname(os.path.abspath(__file__))
_DGPY_ROOT = os.path.dirname(os.path.dirname(_APP_DIR))
_RUNTIME_DIR = os.path.join(_DGPY_ROOT, "apps", "ffmpeg_runtime")
for _p in (_DGPY_ROOT, _APP_DIR, _RUNTIME_DIR):
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
    import ffmpeg_export_selection

    logger = dgpy_log.setup()
    try:
        items = _as_list(selection)
        _pending_selection = items
        visible = ffmpeg_export_selection.has_exportable(items)
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


def _open_export(selection=None):
    import ffmpeg_export_dialog

    items = _resolve_execute_selection(selection)
    try:
        ffmpeg_export_dialog.open_export(items)
    except Exception as exc:  # noqa: BLE001
        import dgpy_gui
        import dgpy_log

        dgpy_log.setup().exception("DG2: Export failed: %s", exc)
        dgpy_gui.warning(None, "DG2: Export", f"Failed to open:\n{exc}")


def get_media_panel_custom_ui_actions():
    import dgpy_menu_layout

    return dgpy_menu_layout.build_media_panel(
        [
            {
                "layout_key": "export.root",
                "name": "DG2: Export",
                "isVisible": _scope_visible,
                "execute": _open_export,
                "minimumVersion": "2025",
            }
        ]
    )
