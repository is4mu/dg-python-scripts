"""
Flame: DG2: Sequence → Cutout First / Last Frame.

Media Panel; logic in cutout_edge_frame_app.
"""

from __future__ import annotations

import os
import sys

_APP_DIR = os.path.dirname(os.path.abspath(__file__))
_DGPY_ROOT = os.path.dirname(os.path.dirname(_APP_DIR))
for _p in (_DGPY_ROOT, _APP_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

__version__ = "1.0.6"

_pending_selection: list | None = None


def _scope_visible(selection) -> bool:
    global _pending_selection
    import dgpy_flame_types
    import dgpy_log
    import cutout_edge_frame_app as app

    logger = dgpy_log.setup()
    items = dgpy_flame_types.as_list(selection)
    _pending_selection = items
    try:
        targets = app.get_targets(items, logger=logger)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "DG2: Sequence Cutout isVisible error pending=%s: %s",
            dgpy_flame_types.summarize(items),
            exc,
        )
        return False
    visible = bool(targets)
    logger.debug(
        "DG2: Sequence Cutout isVisible pending=%s targets=%s visible=%s",
        dgpy_flame_types.summarize(items),
        len(targets),
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
                "DG2: Sequence Cutout using isVisible context %s "
                "(execute had %s)",
                dgpy_flame_types.summarize(pending),
                dgpy_flame_types.summarize(execute_items),
            )
        return pending
    return execute_items


def _run_first(selection=None) -> None:
    import cutout_edge_frame_app as app

    app.cutout_first_frame(_resolve_execute_selection(selection))


def _run_last(selection=None) -> None:
    import cutout_edge_frame_app as app

    app.cutout_last_frame(_resolve_execute_selection(selection))


def get_media_panel_custom_ui_actions():
    import dgpy_menu_layout

    return dgpy_menu_layout.build_media_panel(
        [
            {
                "layout_key": "sequence.cutout_first",
                "name": "Cutout First Frame",
                "isVisible": _scope_visible,
                "execute": _run_first,
                "minimumVersion": "2025",
            },
            {
                "layout_key": "sequence.cutout_last",
                "name": "Cutout Last Frame",
                "isVisible": _scope_visible,
                "execute": _run_last,
                "minimumVersion": "2025",
            },
        ]
    )
