"""
Flame: DG: Batch → Save Setup.

Media Panel: save setups for selected PyBatch, or all under PyDesktop.
"""

from __future__ import annotations

import os
import sys

_APP_DIR = os.path.dirname(os.path.abspath(__file__))
_DGPY_ROOT = os.path.dirname(os.path.dirname(_APP_DIR))
for _p in (_DGPY_ROOT, _APP_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

__version__ = "1.1.5"

_pending_selection: list | None = None


def _scope_visible(selection) -> bool:
    global _pending_selection
    import dgpy_flame_types
    import dgpy_log

    logger = dgpy_log.setup()
    try:
        items = dgpy_flame_types.as_list(selection)
        _pending_selection = items
        batches = dgpy_flame_types.get_batch_groups(items)
        visible = bool(batches)
    except Exception as exc:  # noqa: BLE001
        logger.warning("DG: Batch Save Setup isVisible error: %s", exc)
        return False
    logger.debug(
        "DG: Batch Save Setup isVisible pending=%s n=%s",
        dgpy_flame_types.summarize(items),
        len(batches),
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
                "DG: Batch Save Setup using isVisible context %s "
                "(execute had %s)",
                dgpy_flame_types.summarize(pending),
                dgpy_flame_types.summarize(execute_items),
            )
        return pending
    return execute_items


def _run(selection=None) -> None:
    import dgpy_flame_types
    import save_batch_setup_app

    items = _resolve_execute_selection(selection)
    batches = dgpy_flame_types.get_batch_groups(items)
    save_batch_setup_app.save_batch_setups(batches)


def get_media_panel_custom_ui_actions():
    import dgpy_menu_layout

    return dgpy_menu_layout.build_media_panel(
        [
            {
                "layout_key": "batch.save_setup",
                "name": "Save Setup",
                "isVisible": _scope_visible,
                "execute": _run,
                "minimumVersion": "2025",
            }
        ]
    )
