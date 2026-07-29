"""
Flame: DG: Sequence → Add Markers for Cutdata / Create Cutdata from Markers.

Media Panel; logic in cutdata_app.
"""

from __future__ import annotations

import os
import sys

_APP_DIR = os.path.dirname(os.path.abspath(__file__))
_DGPY_ROOT = os.path.dirname(os.path.dirname(_APP_DIR))
for _p in (_DGPY_ROOT, _APP_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

__version__ = "1.0.9"

_pending_selection: list | None = None


def _scope_add_visible(selection) -> bool:
    global _pending_selection
    import cutdata_app as app
    import dgpy_flame_types
    import dgpy_log

    logger = dgpy_log.setup()
    items = dgpy_flame_types.as_list(selection)
    _pending_selection = items
    try:
        targets = app.get_targets(items, logger=logger)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "DG: Sequence Add Markers for Cutdata isVisible error "
            "pending=%s: %s",
            dgpy_flame_types.summarize(items),
            exc,
        )
        return False
    visible = bool(targets)
    logger.debug(
        "DG: Sequence Add Markers for Cutdata isVisible pending=%s "
        "targets=%s visible=%s",
        dgpy_flame_types.summarize(items),
        len(targets),
        visible,
    )
    return visible


def _scope_create_visible(selection) -> bool:
    global _pending_selection
    import cutdata_app as app
    import dgpy_flame_types
    import dgpy_log

    logger = dgpy_log.setup()
    items = dgpy_flame_types.as_list(selection)
    _pending_selection = items
    try:
        visible = app.has_create_targets(items, logger=logger)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "DG: Sequence Create Cutdata from Markers isVisible error "
            "pending=%s: %s",
            dgpy_flame_types.summarize(items),
            exc,
        )
        return False
    logger.debug(
        "DG: Sequence Create Cutdata from Markers isVisible pending=%s "
        "visible=%s",
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
                "DG: Sequence Cutdata using isVisible context %s "
                "(execute had %s)",
                dgpy_flame_types.summarize(pending),
                dgpy_flame_types.summarize(execute_items),
            )
        return pending
    return execute_items


def _run_add(selection=None) -> None:
    import cutdata_app as app

    app.add_markers_for_cutdata(_resolve_execute_selection(selection))


def _run_create(selection=None) -> None:
    import cutdata_app as app

    app.create_cutdata_from_markers(_resolve_execute_selection(selection))


def get_media_panel_custom_ui_actions():
    import dgpy_menu_layout

    return dgpy_menu_layout.build_media_panel(
        [
            {
                "layout_key": "sequence.cutdata_add_markers",
                "name": "Add Markers for Cutdata",
                "isVisible": _scope_add_visible,
                "execute": _run_add,
                "minimumVersion": "2025",
            },
            {
                "layout_key": "sequence.cutdata_from_markers",
                "name": "Create Cutdata from Markers",
                "isVisible": _scope_create_visible,
                "execute": _run_create,
                "minimumVersion": "2025",
            },
        ]
    )
