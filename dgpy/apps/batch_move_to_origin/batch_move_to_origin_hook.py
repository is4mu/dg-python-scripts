"""
Flame: DG: Move to Origin (Batch schematic).

Batch context menu (hierarchy []) + Keyboard Shortcut Editor.
First selected node → (0, 0); others keep relative positions.
"""

from __future__ import annotations

import os
import sys

_APP_DIR = os.path.dirname(os.path.abspath(__file__))
_DGPY_ROOT = os.path.dirname(os.path.dirname(_APP_DIR))
for _p in (_DGPY_ROOT, _APP_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

__version__ = "1.0.0"

_pending_selection: list | None = None


def _scope_visible(selection) -> bool:
    global _pending_selection
    import dgpy_flame_types
    import dgpy_log

    logger = dgpy_log.setup()
    items = dgpy_flame_types.as_list(selection)
    _pending_selection = items
    logger.debug(
        "DG: Move to Origin isVisible pending=%s",
        dgpy_flame_types.summarize(items),
    )
    return True


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
                "DG: Move to Origin using isVisible context %s "
                "(execute had %s)",
                dgpy_flame_types.summarize(pending),
                dgpy_flame_types.summarize(execute_items),
            )
        return pending
    return execute_items


def _run(selection=None) -> None:
    import batch_move_to_origin_app as app

    app.move_selection_to_origin(_resolve_execute_selection(selection))


def get_batch_custom_ui_actions():
    return [
        {
            "hierarchy": [],
            "actions": [
                {
                    "name": "DG: Move to Origin",
                    "order": 40,
                    "execute": _run,
                    "isVisible": _scope_visible,
                    "minimumVersion": "2025",
                }
            ],
        }
    ]
