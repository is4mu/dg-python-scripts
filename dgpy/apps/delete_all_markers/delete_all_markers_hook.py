"""
Flame: DG: Sequence → Delete All Markers.

Media Panel; logic in delete_all_markers_app.
"""

from __future__ import annotations

import os
import sys

_APP_DIR = os.path.dirname(os.path.abspath(__file__))
_DGPY_ROOT = os.path.dirname(os.path.dirname(_APP_DIR))
for _p in (_DGPY_ROOT, _APP_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

__version__ = "1.0.4"

_pending_selection: list | None = None


def _scope_visible(selection) -> bool:
    global _pending_selection
    import delete_all_markers_app as app
    import dgpy_flame_types
    import dgpy_log

    logger = dgpy_log.setup()
    items = dgpy_flame_types.as_list(selection)
    _pending_selection = items
    try:
        visible = app.has_markers(items, logger=logger)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "DG: Sequence Delete All Markers isVisible error pending=%s: %s",
            dgpy_flame_types.summarize(items),
            exc,
        )
        return False
    logger.debug(
        "DG: Sequence Delete All Markers isVisible pending=%s visible=%s",
        dgpy_flame_types.summarize(items),
        visible,
    )
    return visible


def _resolve_execute_selection(selection) -> list:
    global _pending_selection
    import dgpy_flame_types
    import dgpy_log

    logger = dgpy_log.setup()
    execute_items = dgpy_flame_types.as_list(selection)
    pending = _pending_selection
    _pending_selection = None
    if pending:
        if execute_items and dgpy_flame_types.summarize(
            pending
        ) != dgpy_flame_types.summarize(execute_items):
            logger.debug(
                "DG: Sequence Delete All Markers using isVisible context %s "
                "(execute had %s)",
                dgpy_flame_types.summarize(pending),
                dgpy_flame_types.summarize(execute_items),
            )
        return pending
    return execute_items


def _run(selection=None) -> None:
    import delete_all_markers_app as app

    app.delete_all_markers(_resolve_execute_selection(selection))


def get_media_panel_custom_ui_actions():
    import dgpy_menu_layout

    return dgpy_menu_layout.build_media_panel(
        [
            {
                "layout_key": "sequence.delete_all_markers",
                "name": "Delete All Markers",
                "isVisible": _scope_visible,
                "execute": _run,
                "minimumVersion": "2025",
            },
        ]
    )
